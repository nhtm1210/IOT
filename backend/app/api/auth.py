"""
API Xác thực & Quản lý người dùng (`/api/auth/*` và `/api/users/*`).
- Hỗ trợ đăng nhập bằng JSON body (`{"username": "...", "password": "..."}`) hoặc Form-UrlEncoded.
- Hỗ trợ JWT Bearer Token & Phân quyền RBAC (`ADMIN`, `USER`, `GUEST`).
- Tích hợp Rate Limiting chống dò mật khẩu (Brute-force).
"""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import (
    create_access_token,
    get_current_user,
    get_password_hash,
    rate_limiter,
    require_admin,
    verify_password,
)
from app.models.models import User
from app.schemas.schemas import (
    TokenResponse,
    UserCreateRequest,
    UserOut,
    UserUpdateRequest,
)

router = APIRouter(tags=["1. Auth & Users"])


@router.post(
    "/api/auth/login",
    response_model=TokenResponse,
    summary="Đăng nhập nhận JWT Token (Hỗ trợ cả JSON và Form Data)",
)
async def login(request: Request, db: Session = Depends(get_db)) -> Any:
    client_ip = request.client.host if request.client else "unknown"
    rate_limiter.check(f"login:{client_ip}", max_requests=20, window_seconds=60)

    content_type = request.headers.get("content-type", "").lower()
    username = ""
    password = ""

    if "application/json" in content_type:
        body = await request.json()
        username = str(body.get("username", "")).strip()
        password = str(body.get("password", ""))
    else:
        try:
            form = await request.form()
            username = str(form.get("username", "")).strip()
            password = str(form.get("password", ""))
        except Exception:
            body = await request.json()
            username = str(body.get("username", "")).strip()
            password = str(body.get("password", ""))

    if not username or not password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vui lòng nhập đầy đủ username và password",
        )

    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tên đăng nhập hoặc mật khẩu không chính xác",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tài khoản này đã bị khóa",
        )

    access_token = create_access_token(
        subject=user.username,
        role=user.role,
        user_id=user.id,
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "user": user,
    }


@router.get(
    "/api/auth/me",
    response_model=UserOut,
    summary="Lấy thông tin tài khoản hiện tại từ JWT Token",
)
def get_me(current_user: User = Depends(get_current_user)) -> Any:
    return current_user


@router.get(
    "/api/users",
    response_model=List[UserOut],
    summary="Danh sách tài khoản người dùng (Yêu cầu quyền ADMIN)",
)
def list_users(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> Any:
    return db.query(User).order_by(User.id.asc()).all()


@router.post(
    "/api/users",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    summary="Tạo tài khoản người dùng mới (Yêu cầu quyền ADMIN)",
)
def create_user(
    req: UserCreateRequest,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> Any:
    role = req.role.upper()
    if role not in ("ADMIN", "USER", "GUEST"):
        raise HTTPException(status_code=400, detail="Role phải là ADMIN, USER hoặc GUEST")

    existing = db.query(User).filter(User.username == req.username).first()
    if existing:
        raise HTTPException(status_code=409, detail="Username đã tồn tại")

    new_user = User(
        username=req.username.strip(),
        hashed_password=get_password_hash(req.password),
        full_name=req.full_name,
        role=role,
        is_active=True,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


@router.put(
    "/api/users/{user_id}",
    response_model=UserOut,
    summary="Cập nhật thông tin / quyền / mật khẩu người dùng (ADMIN)",
)
def update_user(
    user_id: int,
    req: UserUpdateRequest,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> Any:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")

    if req.full_name is not None:
        user.full_name = req.full_name
    if req.role is not None:
        role = req.role.upper()
        if role not in ("ADMIN", "USER", "GUEST"):
            raise HTTPException(status_code=400, detail="Role phải là ADMIN, USER hoặc GUEST")
        user.role = role
    if req.is_active is not None:
        user.is_active = req.is_active
    if req.password:
        user.hashed_password = get_password_hash(req.password)

    db.commit()
    db.refresh(user)
    return user


@router.delete(
    "/api/users/{user_id}",
    summary="Xóa tài khoản người dùng (ADMIN)",
)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> Dict[str, Any]:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")
    if user.id == admin.id or user.username == "admin":
        raise HTTPException(status_code=400, detail="Không thể xóa tài khoản Admin gốc")

    db.delete(user)
    db.commit()
    return {"status": "deleted", "user_id": user_id}
