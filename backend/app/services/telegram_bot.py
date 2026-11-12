"""
Dịch vụ gửi thông báo & cảnh báo an ninh qua Telegram Bot API.
Hỗ trợ:
- Gửi tin nhắn văn bản định dạng Markdown/HTML (`sendMessage`)
- Gửi kèm ảnh chụp từ ESP32-CAM khi phát hiện người lạ hoặc chuyển động (`sendPhoto`)
- Đọc cấu hình động từ bảng `SystemSetting` hoặc biến môi trường `.env`.
"""

from __future__ import annotations

import logging
import threading
import uuid
from pathlib import Path
from typing import Optional, Tuple
from urllib import parse, request

from app.core.config import settings
from app.core.database import db_session
from app.models.models import SystemSetting

logger = logging.getLogger("telegram_bot")


class TelegramBotService:
    def _get_credentials(
        self,
        override_token: Optional[str] = None,
        override_chat_id: Optional[str] = None,
    ) -> Tuple[bool, str, str]:
        """Lấy cấu hình Telegram mới nhất từ Database (hoặc fallback về `.env`)."""
        enabled = settings.TELEGRAM_ENABLED
        token = settings.TELEGRAM_BOT_TOKEN
        chat_id = settings.TELEGRAM_CHAT_ID

        try:
            with db_session() as db:
                rows = {
                    r.key: r.value
                    for r in db.query(SystemSetting)
                    .filter(
                        SystemSetting.key.in_(
                            ["telegram_enabled", "telegram_bot_token", "telegram_chat_id"]
                        )
                    )
                    .all()
                }
                if "telegram_enabled" in rows:
                    enabled = rows["telegram_enabled"].lower() in ("true", "1", "yes")
                if rows.get("telegram_bot_token"):
                    token = rows["telegram_bot_token"]
                if rows.get("telegram_chat_id"):
                    chat_id = rows["telegram_chat_id"]
        except Exception as exc:
            logger.debug("Không đọc được cấu hình Telegram từ DB: %s", exc)

        if override_token is not None:
            token = override_token
        if override_chat_id is not None:
            chat_id = override_chat_id

        return enabled, token.strip(), chat_id.strip()

    def send_message_sync(
        self,
        text: str,
        bot_token: Optional[str] = None,
        chat_id: Optional[str] = None,
        force: bool = False,
        image_path: Optional[Path] = None,
    ) -> Tuple[bool, str]:
        """Gửi tin nhắn Telegram đồng bộ (an toàn khi gọi từ thread hoặc test endpoint)."""
        enabled, token, cid = self._get_credentials(bot_token, chat_id)
        if not force and not enabled:
            return False, "Cảnh báo Telegram đang tắt (telegram_enabled=false)"
        if not token or not cid:
            return False, "Chưa cấu hình TELEGRAM_BOT_TOKEN hoặc TELEGRAM_CHAT_ID"

        try:
            image_path = Path(image_path) if image_path and Path(image_path).exists() else None
            if image_path:
                # Gửi ảnh + caption qua Telegram sendPhoto (multipart/form-data)
                boundary = f"----smarthome{uuid.uuid4().hex}"
                caption = text[:1000]
                fields = [("chat_id", cid), ("caption", caption), ("parse_mode", "HTML")]
                body = b""
                for name, value in fields:
                    body += (
                        f"--{boundary}\r\n"
                        f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
                        f"{value}\r\n"
                    ).encode("utf-8")
                body += (
                    f"--{boundary}\r\n"
                    'Content-Disposition: form-data; name="photo"; filename="alert.jpg"\r\n'
                    "Content-Type: image/jpeg\r\n\r\n"
                ).encode("utf-8")
                body += image_path.read_bytes() + f"\r\n--{boundary}--\r\n".encode("utf-8")
                url = f"https://api.telegram.org/bot{token}/sendPhoto"
                req = request.Request(
                    url,
                    data=body,
                    method="POST",
                    headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
                )
            else:
                url = f"https://api.telegram.org/bot{token}/sendMessage"
                data = parse.urlencode(
                    {
                        "chat_id": cid,
                        "text": text,
                        "parse_mode": "HTML",
                    }
                ).encode("utf-8")
                req = request.Request(url, data=data, method="POST")

            with request.urlopen(req, timeout=15) as resp:
                if 200 <= resp.status < 300:
                    logger.info("[Telegram] Đã gửi cảnh báo thành công tới chat_id=%s", cid)
                    return True, "Đã gửi tin nhắn Telegram thành công"
                return False, f"Telegram trả về mã HTTP {resp.status}"
        except Exception as exc:
            logger.warning("[Telegram] Lỗi khi gửi tin nhắn: %s", exc)
            return False, f"Lỗi kết nối Telegram API: {exc}"

    def send_alert_background(
        self,
        title: str,
        message: str,
        severity: str = "WARNING",
        image_path: Optional[Path] = None,
    ) -> None:
        """Gửi cảnh báo Telegram trong một luồng nền để không làm chậm MQTT hoặc HTTP response."""
        icon = "🚨" if severity == "CRITICAL" else ("⚠️" if severity == "WARNING" else "ℹ️")
        formatted = f"{icon} <b>{title}</b>\n{message}"

        def _worker() -> None:
            self.send_message_sync(formatted, image_path=image_path)

        t = threading.Thread(target=_worker, daemon=True)
        t.start()


telegram_service = TelegramBotService()
