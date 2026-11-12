"""
Quản lý kết nối WebSocket thời gian thực cho Web Dashboard (`/ws/dashboard`).
Hỗ trợ phát sóng (broadcast) an toàn từ cả luồng `asyncio` của FastAPI lẫn luồng nền của Paho-MQTT.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional

from fastapi import WebSocket

logger = logging.getLogger("ws_manager")


class WebSocketConnectionManager:
    def __init__(self) -> None:
        self.active_connections: List[WebSocket] = []
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def set_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info("WebSocket client đã kết nối. Tổng số client: %d", len(self.active_connections))

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info("WebSocket client đã ngắt kết nối. Còn lại: %d", len(self.active_connections))

    async def broadcast(self, event_type: str, data: Any) -> None:
        if not self.active_connections:
            return
        message = json.dumps(
            {
                "event": event_type,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "data": data,
            },
            ensure_ascii=False,
            default=str,
        )
        stale: List[WebSocket] = []
        for connection in list(self.active_connections):
            try:
                await connection.send_text(message)
            except Exception:
                stale.append(connection)
        for conn in stale:
            self.disconnect(conn)

    def broadcast_threadsafe(self, event_type: str, data: Any) -> None:
        """Gọi từ luồng nền (như Paho-MQTT callback) để đẩy sự kiện tới mọi trình duyệt đang mở."""
        if not self.active_connections or self._loop is None:
            return
        try:
            if self._loop.is_running():
                asyncio.run_coroutine_threadsafe(self.broadcast(event_type, data), self._loop)
        except Exception as exc:
            logger.debug("Không thể broadcast WebSocket từ thread: %s", exc)


ws_manager = WebSocketConnectionManager()
