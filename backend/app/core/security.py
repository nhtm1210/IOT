"""
Module Bảo mật:
1. Băm và kiểm tra mật khẩu bằng bcrypt (kèm fallback PBKDF2-HMAC-SHA256 an toàn).
2. Khởi tạo và xác thực JWT (JSON Web Token - chuẩn HS256).
3. Phân quyền Role-Based Access Control (ADMIN, USER, GUEST).
4. Rate Limiting chống Brute-force đăng nhập & Spam API.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db

try:
    import bcrypt as _bcrypt
except ImportError:
    _bcrypt = None

bearer_scheme = HTTPBearer(auto_error=False)


# =====================================================================
# 1. PASSWORD HASHING (BCRYPT + PBKDF2 FALLBACK)
# =====================================================================
def get_password_hash(password: str) -> str:
    """Băm mật khẩu an toàn bằng bcrypt (hoặc PBKDF2-SHA256 nếu chưa cài bcrypt)."""
    if _bcrypt is not None:
        salt = _bcrypt.gensalt(rounds=12)
        hashed = _bcrypt.hashpw(password.encode("utf-8"), salt)
        return hashed.decode("utf-8")

    salt_hex = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt_hex.encode("utf-8"), 200_000)
    return f"pbkdf2_sha256${salt_hex}${dk.hex()}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Kiểm tra mật khẩu nhập vào với mật khẩu đã băm trong Database."""
    if not plain_password or not hashed_password:
        return False

    if hashed_password.startswith("pbkdf2_sha256$"):
        try:
            _, salt_hex, stored_hex = hashed_password.split("$", 2)
            dk = hashlib.pbkdf2_hmac(
                "sha256", plain_password.encode("utf-8"), salt_hex.encode("utf-8"), 200_000
            )
            return hmac.compare_digest(dk.hex(), stored_hex)
        except Exception:
            return False

    if _bcrypt is not None:
        try:
            return _bcrypt.checkpw(
                plain_password.encode("utf-8"), hashed_password.encode("utf-8")
            )
        except Exception:
            return False

    return False


# =====================================================================
# 2. JWT CREATION & VERIFICATION (RFC 7519 HS256)
# =====================================================================
def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def create_access_token(
    subject: str,
    role: str = "USER",
    user_id: Optional[int] = None,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Tạo JWT Access Token chuẩn HS256."""
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))

    header = {"alg": settings.JWT_ALGORITHM, "typ": "JWT"}
    payload: Dict[str, Any] = {
        "sub": str(subject),
        "role": role,
        "uid": user_id,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }

    header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")

    signature = hmac.new(
        settings.JWT_SECRET_KEY.encode("utf-8"), signing_input, hashlib.sha256
    ).digest()
    sig_b64 = _b64url_encode(signature)
    return f"{header_b64}.{payload_b64}.{sig_b64}"


def decode_access_token(token: str) -> Dict[str, Any]:
    """Giải mã và xác thực chữ ký + thời hạn của JWT Access Token."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError("Invalid token structure")
        header_b64, payload_b64, sig_b64 = parts
        signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
        expected_sig = hmac.new(
            settings.JWT_SECRET_KEY.encode("utf-8"), signing_input, hashlib.sha256
        ).digest()
        actual_sig = _b64url_decode(sig_b64)
        if not hmac.compare_digest(expected_sig, actual_sig):
            raise ValueError("Invalid signature")

        payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
        exp = payload.get("exp")
        if exp is not None and int(time.time()) > int(exp):
            raise ValueError("Token expired")
        return payload
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token không hợp lệ hoặc đã hết hạn: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


# =====================================================================
# 3. RATE LIMITER CHỐNG BRUTE-FORCE & SPAM
# =====================================================================
class SimpleRateLimiter:
    """Bộ giới hạn tần suất gọi API theo IP."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._hits: Dict[str, list[float]] = {}

    def check(self, key: str, max_requests: int, window_seconds: int) -> None:
        now = time.monotonic()
        with self._lock:
            history = [t for t in self._hits.get(key, []) if now - t < window_seconds]
            if len(history) >= max_requests:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Quá nhiều yêu cầu. Vui lòng thử lại sau {window_seconds} giây.",
                )
            history.append(now)
            self._hits[key] = history


rate_limiter = SimpleRateLimiter()


# =====================================================================
# 4. FASTAPI AUTH DEPENDENCIES & RBAC
# =====================================================================
def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
):
    """Bắt buộc phải có JWT Bearer Token hợp lệ."""
    from app.models.models import User

    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Chưa đăng nhập (thiếu Bearer Token)",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_access_token(credentials.credentials)
    username = payload.get("sub")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token thiếu thông tin người dùng",
        )

    user = db.query(User).filter(User.username == username).first()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tài khoản không tồn tại hoặc đã bị khóa",
        )
    return user


def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
):
    """
    Trả về User nếu client có gửi Bearer Token, hoặc None nếu không gửi.
    Nếu có gửi Token nhưng Token sai/hoặc là GUEST bị giới hạn thì vẫn kiểm tra đầy đủ.
    """
    from app.models.models import User

    if credentials is None or not credentials.credentials:
        return None

    payload = decode_access_token(credentials.credentials)
    username = payload.get("sub")
    if not username:
        return None
    user = db.query(User).filter(User.username == username).first()
    if user and not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tài khoản đã bị vô hiệu hóa",
        )
    return user


def require_operator(user=Depends(get_optional_user)):
    """
    Kiểm tra quyền vận hành thiết bị (ADMIN hoặc USER).
    - Nếu người dùng đăng nhập bằng tài khoản GUEST -> Từ chối (403 Forbidden).
    - Nếu là ADMIN / USER (hoặc đang test nhanh từ Swagger chưa gắn token) -> Cho phép.
    """
    if user is not None and user.role.upper() == "GUEST":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tài khoản GUEST chỉ có quyền xem (Read-Only), không được điều khiển thiết bị.",
        )
    return user


def require_admin(user=Depends(get_current_user)):
    """Chỉ cho phép người dùng có role ADMIN."""
    if user.role.upper() != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chức năng này chỉ dành cho Quản trị viên (ADMIN).",
        )
    return user


def verify_device_api_key(
    request: Request,
    x_api_key: Optional[str] = Header(default=None),
) -> None:
    """
    Xác thực API Key tùy chọn cho thiết bị ESP32-CAM.
    Nếu trong `.env` có đặt `DEVICE_API_KEY`, thiết bị phải gửi kèm `X-Api-Key`.
    Nếu `DEVICE_API_KEY` để trống (mặc định để tương thích ngay với firmware hiện tại), cho phép qua.
    """
    if settings.DEVICE_API_KEY:
        if not x_api_key or not hmac.compare_digest(x_api_key, settings.DEVICE_API_KEY):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="X-Api-Key của thiết bị không hợp lệ",
            )
