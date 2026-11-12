"""
API Quản lý & Điều khiển thiết bị (`/api/devices`, `/api/devices/control`, `/api/devices/history`).
Hỗ trợ cả điều khiển theo từng thiết bị đơn lẻ (`light_1`, `buzzer_1`, `light_2`, `fan_1`, `door_servo_1`)
lẫn điều khiển gộp theo cụm (`esp32_cluster1`, `esp32_cluster2`, `esp32_cam_01`).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_operator
from app.models.models import Device, DeviceHistory
from app.schemas.schemas import DeviceControlRequest, DeviceHistoryOut, DeviceOut
from app.services.mqtt_service import mqtt_service

router = APIRouter(tags=["4. Devices & Control History"])


@router.get(
    "/api/devices",
    summary="Danh sách thiết bị đầu ra & trạng thái 3 cụm ESP32",
)
def list_devices(db: Session = Depends(get_db)) -> Dict[str, Any]:
    devices = db.query(Device).order_by(Device.cluster_id.asc(), Device.id.asc()).all()
    return {
        "mqtt_connected": mqtt_service.connected,
        "devices": [DeviceOut.model_validate(d).model_dump() for d in devices],
        "nodes": mqtt_service.get_snapshot(),
    }


@router.post(
    "/api/devices/control",
    summary="Gửi lệnh điều khiển thiết bị hoặc chuyển chế độ AUTO/MANUAL",
)
def control_device(
    req: DeviceControlRequest,
    user=Depends(require_operator),
) -> Dict[str, Any]:
    mode = req.mode.upper()
    if mode not in ("AUTO", "MANUAL"):
        raise HTTPException(status_code=400, detail="mode phải là AUTO hoặc MANUAL")

    target = req.device_id.strip()
    state_upper = (req.state or "").upper()
    is_on: Optional[bool] = None
    if state_upper in ("ON", "OPEN", "TRUE", "1"):
        is_on = True
    elif state_upper in ("OFF", "LOCKED", "CLOSE", "FALSE", "0"):
        is_on = False

    actor = user.username if user else "WEB_USER"

    # 1. Thiết bị thuộc Cụm 1 (esp32_cluster1, light_1, buzzer_1)
    if target in ("esp32_cluster1", "light_1", "buzzer_1"):
        light_val: Optional[bool] = None
        buzzer_val: Optional[bool] = None
        if req.outputs:
            light_val = req.outputs.get("light")
            buzzer_val = req.outputs.get("buzzer")
        elif target == "light_1":
            light_val = is_on
        elif target == "buzzer_1":
            buzzer_val = is_on
        elif is_on is not None:
            light_val = is_on
            buzzer_val = is_on

        sent = mqtt_service.control_cluster1(
            mode=mode,
            light=light_val,
            buzzer=buzzer_val,
            triggered_by=actor,
        )
        return {
            "status": "published",
            "cluster_id": "esp32_cluster1",
            "command": sent,
            "node": mqtt_service.get_snapshot()["esp32_cluster1"],
        }

    # 2. Thiết bị thuộc Cụm 2 (esp32_cluster2, light_2, fan_1)
    if target in ("esp32_cluster2", "light_2", "fan_1"):
        light_val = None
        fan_val = None
        if req.outputs:
            light_val = req.outputs.get("light")
            fan_val = req.outputs.get("fan")
        elif target == "light_2":
            light_val = is_on
        elif target == "fan_1":
            fan_val = is_on
        elif is_on is not None:
            light_val = is_on
            fan_val = is_on

        sent = mqtt_service.control_cluster2(
            mode=mode,
            light=light_val,
            fan=fan_val,
            triggered_by=actor,
        )
        return {
            "status": "published",
            "cluster_id": "esp32_cluster2",
            "command": sent,
            "node": mqtt_service.get_snapshot()["esp32_cluster2"],
        }

    # 3. Thiết bị cửa Servo SG90 trên ESP32-CAM (esp32_cam_01, door_servo_1)
    if target in ("esp32_cam_01", "door_servo_1"):
        open_door = bool(is_on) if is_on is not None else True
        sent = mqtt_service.send_door_access_decision(
            identity="KNOWN" if open_door else "UNKNOWN",
            authorized=open_door,
            person_name=actor,
            confidence=1.0 if open_door else 0.0,
            triggered_by=actor,
        )
        return {
            "status": "published",
            "cluster_id": "esp32_cam_01",
            "command": sent,
            "node": mqtt_service.get_snapshot()["esp32_cam_01"],
        }

    raise HTTPException(
        status_code=404,
        detail=(
            f"Không tìm thấy thiết bị '{target}'. "
            "Hỗ trợ: light_1, buzzer_1, light_2, fan_1, door_servo_1, esp32_cluster1, esp32_cluster2, esp32_cam_01."
        ),
    )


@router.get(
    "/api/devices/history",
    response_model=List[DeviceHistoryOut],
    summary="Lịch sử điều khiển thiết bị & xác nhận ACK",
)
def get_device_history(
    cluster_id: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> Any:
    query = db.query(DeviceHistory)
    if cluster_id:
        query = query.filter(DeviceHistory.cluster_id == cluster_id)
    return query.order_by(DeviceHistory.id.desc()).limit(limit).all()
