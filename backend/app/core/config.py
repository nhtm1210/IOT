"""
Cấu hình trung tâm cho hệ thống Backend Smart Home IoT AI.
Tự động nạp biến môi trường từ file `backend/.env` (nếu có).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List


def _load_dotenv(env_path: Path) -> None:
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        os.environ.setdefault(key, val)


BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
PROJECT_ROOT = BACKEND_DIR.parent
_load_dotenv(BACKEND_DIR / ".env")

DATA_DIR = BACKEND_DIR / "data"
OWNER_FACES_DIR = DATA_DIR / "owner_faces"
CAPTURED_EVENTS_DIR = DATA_DIR / "captured_events"

DATA_DIR.mkdir(parents=True, exist_ok=True)
OWNER_FACES_DIR.mkdir(parents=True, exist_ok=True)
CAPTURED_EVENTS_DIR.mkdir(parents=True, exist_ok=True)


class Settings:
    APP_NAME: str = os.getenv("APP_NAME", "Smart Home IoT AI Backend")
    APP_VERSION: str = os.getenv("APP_VERSION", "1.1.0")
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    DEBUG: bool = os.getenv("DEBUG", "true").lower() in ("1", "true", "yes")

    # JWT & Bảo mật
    JWT_SECRET_KEY: str = os.getenv(
        "JWT_SECRET_KEY", "smarthome_iot_super_secret_key_change_in_production_2026"
    )
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))
    DEVICE_API_KEY: str = os.getenv("DEVICE_API_KEY", "")

    # Database
    DEFAULT_SQLITE_URL = f"sqlite:///{(DATA_DIR / 'smarthome.db').as_posix()}"
    DATABASE_URL: str = os.getenv("DATABASE_URL", DEFAULT_SQLITE_URL)
    if DATABASE_URL.startswith("sqlite:///./"):
        rel_path = DATABASE_URL.replace("sqlite:///./", "", 1)
        DATABASE_URL = f"sqlite:///{(BACKEND_DIR / rel_path).resolve().as_posix()}"

    # MQTT Broker
    MQTT_HOST: str = os.getenv("MQTT_HOST", "127.0.0.1")
    MQTT_PORT: int = int(os.getenv("MQTT_PORT", "1883"))
    MQTT_USERNAME: str = os.getenv("MQTT_USERNAME", "")
    MQTT_PASSWORD: str = os.getenv("MQTT_PASSWORD", "")
    ENABLE_EMBEDDED_BROKER: bool = os.getenv("ENABLE_EMBEDDED_BROKER", "true").lower() in (
        "1",
        "true",
        "yes",
    )

    # AI Face Recognition
    FACE_MATCH_THRESHOLD: float = float(os.getenv("FACE_MATCH_THRESHOLD", "0.65"))
    OWNER_FACE_PATH: Path = OWNER_FACES_DIR / "owner.jpg"

    # Telegram Bot
    TELEGRAM_ENABLED: bool = os.getenv("TELEGRAM_ENABLED", "false").lower() in (
        "1",
        "true",
        "yes",
    )
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")

    # Phục vụ gộp chung Frontend build (nếu có)
    SERVE_FRONTEND_DIST: bool = os.getenv("SERVE_FRONTEND_DIST", "true").lower() in (
        "1",
        "true",
        "yes",
    )
    FRONTEND_DIST_DIR: Path = (
        BACKEND_DIR / os.getenv("FRONTEND_DIST_DIR", "../frontend/dist")
    ).resolve()

    CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "*",
    ]


settings = Settings()
