"""
Điểm khởi đầu chính của hệ thống Backend Smart Home IoT AI (`app/main.py`).
Tự động:
1. Khởi tạo Cơ sở dữ liệu SQLite (`data/smarthome.db`) & tạo dữ liệu mẫu ban đầu (Admin/User/Guest, 5 thiết bị, 4 kịch bản tự động).
2. Khởi chạy `EmbeddedMqttBroker` ở cổng `1883` (nếu chưa có Mosquitto chạy sẵn).
3. Khởi chạy `SmartHomeMqttService` kết nối Paho-MQTT lắng nghe 13 topics từ 3 cụm ESP32.
4. Cung cấp toàn bộ REST API (`/api/*`), Swagger UI (`/docs`) và WebSocket thời gian thực (`/ws/dashboard`).
5. Tự động phục vụ giao diện React (`../frontend/dist`) trên cùng cổng `8000` nếu thư mục build tồn tại.
"""

from __future__ import annotations

import asyncio
import logging
import socket
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.api import (
    alerts_settings,
    auth,
    automation,
    devices,
    mqtt_routes,
    security_ai,
    sensors,
)
from app.core.config import settings
from app.core.database import db_session
from app.models.models import init_db_and_seed
from app.services.broker import EmbeddedMqttBroker
from app.services.face_recognition import is_owner_face_enrolled
from app.services.mqtt_service import mqtt_service
from app.websocket.manager import ws_manager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("smarthome_backend")


def _is_port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        return s.connect_ex((host, port)) == 0


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Khởi tạo Database & Seed dữ liệu mặc định
    with db_session() as db:
        init_db_and_seed(db)
    logger.info("Đã khởi tạo SQLite Database & dữ liệu mặc định thành công.")

    # 2. Gắn asyncio loop cho WebSocket Manager để thread MQTT có thể broadcast
    ws_manager.set_event_loop(asyncio.get_running_loop())

    # 3. Tự động bật Embedded MQTT Broker ở cổng 1883 nếu chưa có Mosquitto/Docker
    embedded_broker: Optional[EmbeddedMqttBroker] = None
    if (
        settings.ENABLE_EMBEDDED_BROKER
        and mqtt_service.broker_host in ("127.0.0.1", "localhost", "0.0.0.0")
        and not _is_port_in_use("127.0.0.1", mqtt_service.broker_port)
    ):
        embedded_broker = EmbeddedMqttBroker(
            host="0.0.0.0",
            port=mqtt_service.broker_port,
            username=settings.MQTT_USERNAME,
            password=settings.MQTT_PASSWORD,
        )
        await embedded_broker.start()

    # 4. Bắt đầu Paho-MQTT Subscriber/Publisher
    mqtt_service.start()

    yield

    # Dọn dẹp khi tắt server
    mqtt_service.stop()
    if embedded_broker is not None:
        await embedded_broker.stop()


app = FastAPI(
    title=settings.APP_NAME,
    description=(
        "Hệ thống Backend Nhà Thông Minh IoT tích hợp AI nhận diện khuôn mặt mở cửa Servo SG90.\n\n"
        "- **Tài khoản mặc định:** `admin` / `admin123` (ADMIN), `user` / `user123` (USER), `guest` / `guest123` (GUEST)\n"
        "- **WebSocket thời gian thực:** `ws://localhost:8000/ws/dashboard`"
    ),
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Đăng ký toàn bộ API Routers
app.include_router(auth.router)
app.include_router(mqtt_routes.router)
app.include_router(sensors.router)
app.include_router(devices.router)
app.include_router(security_ai.router)
app.include_router(automation.router)
app.include_router(alerts_settings.router)


@app.get("/api/health", tags=["0. System & WebSocket"], summary="Kiểm tra trạng thái hoạt động của Backend")
def health_check() -> Dict[str, Any]:
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "mqtt_connected": mqtt_service.connected,
        "mqtt_broker": f"{mqtt_service.broker_host}:{mqtt_service.broker_port}",
        "owner_face_enrolled": is_owner_face_enrolled(),
        "websocket_clients": len(ws_manager.active_connections),
    }


@app.websocket("/ws/dashboard")
async def dashboard_websocket(websocket: WebSocket) -> None:
    """
    Kênh WebSocket thời gian thực cho Frontend React Dashboard.
    Ngay khi kết nối, server gửi bản tin `INITIAL_STATE` chứa toàn bộ trạng thái 3 cụm ESP32.
    Mỗi khi có dữ liệu cảm biến, chuyển động PIR, nhận diện khuôn mặt hoặc cảnh báo mới,
    server tự động đẩy sự kiện xuống client.
    """
    await ws_manager.connect(websocket)
    try:
        await websocket.send_json(
            {
                "event": "INITIAL_STATE",
                "data": {
                    "mqtt_connected": mqtt_service.connected,
                    "owner_face_enrolled": is_owner_face_enrolled(),
                    "nodes": mqtt_service.get_snapshot(),
                },
            }
        )
        while True:
            msg = await websocket.receive_text()
            if msg.strip().lower() == "ping":
                await websocket.send_json({"event": "PONG", "data": "ok"})
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception:
        ws_manager.disconnect(websocket)


# =====================================================================
# PHỤC VỤ GỘP CHUNG FRONTEND BUILD (NẾU CÓ `../frontend/dist`)
# =====================================================================
if (
    settings.SERVE_FRONTEND_DIST
    and settings.FRONTEND_DIST_DIR.exists()
    and (settings.FRONTEND_DIST_DIR / "index.html").exists()
):
    assets_dir = settings.FRONTEND_DIST_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="frontend_assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        candidate = settings.FRONTEND_DIST_DIR / full_path
        if full_path and candidate.exists() and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(settings.FRONTEND_DIST_DIR / "index.html")

else:
    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def root_landing() -> str:
        return """
        <!doctype html>
        <html lang="vi">
        <head>
            <meta charset="utf-8" />
            <title>Smart Home IoT AI - Backend Server</title>
            <style>
                body { font-family: system-ui, -apple-system, sans-serif; max-width: 780px; margin: 40px auto; padding: 0 20px; color: #1e293b; line-height: 1.6; }
                .card { border: 1px solid #e2e8f0; border-radius: 12px; padding: 24px; background: #f8fafc; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
                h1 { margin-top: 0; color: #0f172a; }
                a.btn { display: inline-block; padding: 10px 18px; margin-right: 10px; border-radius: 8px; text-decoration: none; font-weight: 600; background: #2563eb; color: white; }
                a.btn-sec { background: #475569; }
                code { background: #e2e8f0; padding: 2px 6px; border-radius: 4px; }
            </style>
        </head>
        <body>
            <div class="card">
                <h1>🏠 Smart Home IoT AI — Backend Server đang hoạt động!</h1>
                <p>Hệ thống Backend (FastAPI + SQLite + Embedded MQTT Broker + OpenCV Face Recognition + WebSocket) đã sẵn sàng.</p>
                <p>
                    <a class="btn" href="/docs">📖 Mở Swagger UI (/docs)</a>
                    <a class="btn btn-sec" href="/api/mqtt/state">📡 Xem trạng thái 3 cụm ESP32 (/api/mqtt/state)</a>
                    <a class="btn btn-sec" href="/api/health">🩺 Health Check (/api/health)</a>
                </p>
                <hr style="border:0;border-top:1px solid #cbd5e1;margin:20px 0;" />
                <p><strong>Tài khoản mặc định:</strong> <code>admin / admin123</code> (ADMIN), <code>user / user123</code> (USER), <code>guest / guest123</code> (GUEST)</p>
                <p><strong>Gộp chung Frontend khi Demo:</strong> Sau khi chạy <code>npm run build</code> trong thư mục <code>frontend/</code>, Backend sẽ tự động phục vụ giao diện Web trực tiếp tại địa chỉ này.</p>
            </div>
        </body>
        </html>
        """
