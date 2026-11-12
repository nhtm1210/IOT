"""
Các Endpoint MQTT trực tiếp khớp 100% với Bảng 6 trong `WEB_DASHBOARD_SPEC.md` và `server_mqtt_sample.py`:
- `GET  /api/mqtt/state`
- `GET  /api/mqtt/logs`
- `POST /api/mqtt/cluster1/control`
- `POST /api/mqtt/cluster2/control`
- `POST /api/mqtt/cam/door`
- `POST /api/mqtt/cam/capture`
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.security import require_operator
from app.schemas.schemas import (
    CamDoorCommandRequest,
    Cluster1CommandRequest,
    Cluster2CommandRequest,
)
from app.services.face_recognition import is_owner_face_enrolled
from app.services.mqtt_service import mqtt_service

router = APIRouter(tags=["2. MQTT & 3 Clusters Control"])


@router.get(
    "/api/mqtt/state",
    summary="Xem trạng thái thời gian thực của cả 3 cụm ESP32 (Khớp SystemSnapshotResponse)",
)
def get_mqtt_state() -> Dict[str, Any]:
    return {
        "mqtt_connected": mqtt_service.connected,
        "broker": f"{mqtt_service.broker_host}:{mqtt_service.broker_port}",
        "owner_face_enrolled": is_owner_face_enrolled(),
        "nodes": mqtt_service.get_snapshot(),
    }


@router.get(
    "/api/mqtt/logs",
    summary="Xem lịch sử các bản tin MQTT gần nhất",
)
def get_mqtt_logs(limit: int = Query(default=50, ge=1, le=250)) -> Dict[str, Any]:
    items = mqtt_service.get_recent_logs(limit=limit)
    return {"count": len(items), "items": items}


@router.post(
    "/api/mqtt/cluster1/control",
    summary="Điều khiển Cụm ESP 1 (Đèn GPIO26 + Còi GPIO25 + Chế độ AUTO/MANUAL)",
)
def control_cluster1(
    req: Cluster1CommandRequest,
    user=Depends(require_operator),
) -> Dict[str, Any]:
    mode = req.mode.upper()
    if mode not in ("AUTO", "MANUAL"):
        raise HTTPException(status_code=400, detail="mode phải là AUTO hoặc MANUAL")
    actor = user.username if user else "WEB_USER"
    sent = mqtt_service.control_cluster1(
        mode=mode,
        light=req.light,
        buzzer=req.buzzer,
        triggered_by=actor,
    )
    return {"status": "published", "command": sent, "node": mqtt_service.get_snapshot()["esp32_cluster1"]}


@router.post(
    "/api/mqtt/cluster2/control",
    summary="Điều khiển Cụm ESP 2 (Đèn GPIO2 + Quạt GPIO5 + Chế độ AUTO/MANUAL)",
)
def control_cluster2(
    req: Cluster2CommandRequest,
    user=Depends(require_operator),
) -> Dict[str, Any]:
    mode = req.mode.upper()
    if mode not in ("AUTO", "MANUAL"):
        raise HTTPException(status_code=400, detail="mode phải là AUTO hoặc MANUAL")
    actor = user.username if user else "WEB_USER"
    sent = mqtt_service.control_cluster2(
        mode=mode,
        light=req.light,
        fan=req.fan,
        triggered_by=actor,
    )
    return {"status": "published", "command": sent, "node": mqtt_service.get_snapshot()["esp32_cluster2"]}


@router.post(
    "/api/mqtt/cam/door",
    summary="Điều khiển đóng/mở cửa Servo SG90 (90° / 0°) xuống ESP32-CAM",
)
def control_cam_door(
    req: CamDoorCommandRequest,
    user=Depends(require_operator),
) -> Dict[str, Any]:
    actor = user.username if user else "WEB_ADMIN"
    sent = mqtt_service.send_door_access_decision(
        identity=req.identity.upper(),
        authorized=req.authorized,
        person_name=req.person_name,
        confidence=req.confidence,
        event_id=req.event_id,
        triggered_by=actor,
    )
    return {"status": "published", "command": sent, "node": mqtt_service.get_snapshot()["esp32_cam_01"]}


@router.post(
    "/api/mqtt/cam/capture",
    summary="Yêu cầu ESP32-CAM chụp ảnh ngay qua MQTT",
)
def trigger_cam_capture(user=Depends(require_operator)) -> Dict[str, Any]:
    sent = mqtt_service.request_camera_capture()
    return {"status": "published", "command": sent}
