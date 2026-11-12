"""
Script khởi chạy nhanh hệ thống Backend Smart Home IoT AI.
Chỉ cần chạy:
    python run.py
Sẽ tự động bật:
- MQTT Broker ở cổng 1883 (nếu chưa có Mosquitto)
- FastAPI Backend + WebSocket Server ở cổng 8000
"""

from __future__ import annotations

import uvicorn

from app.core.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=False,
    )
