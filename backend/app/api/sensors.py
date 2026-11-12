"""
API Cảm biến (`/api/sensors/latest` và `/api/sensors/history`).
Phục vụ 4 thẻ thông số thời gian thực trên Dashboard và biểu đồ Recharts trên trang `/history`.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.models import SensorHistory
from app.schemas.schemas import SensorHistoryOut
from app.services.mqtt_service import mqtt_service

router = APIRouter(tags=["3. Sensors & Charts"])


@router.get(
    "/api/sensors/latest",
    summary="Lấy thông số cảm biến mới nhất (Nhiệt độ, Độ ẩm, Ánh sáng ADC/Lux, PIR, Cửa)",
)
def get_latest_sensors(db: Session = Depends(get_db)) -> Dict[str, Any]:
    snap = mqtt_service.get_snapshot()
    c1 = snap["esp32_cluster1"]
    c2 = snap["esp32_cluster2"]
    cam = snap["esp32_cam_01"]

    # Nếu Cụm 2 chưa gửi bản tin MQTT nào từ lúc bật server, lấy bản ghi gần nhất từ Database
    if c2["temperature_c"] is None:
        last_c2 = (
            db.query(SensorHistory)
            .filter(SensorHistory.cluster_id == "esp32_cluster2")
            .order_by(SensorHistory.id.desc())
            .first()
        )
        if last_c2:
            c2["temperature_c"] = last_c2.temperature_c
            c2["humidity_pct"] = last_c2.humidity_pct
            c2["light_adc"] = last_c2.light_adc
            c2["light_lux"] = last_c2.light_lux
            c2["is_dark"] = last_c2.is_dark

    return {
        "mqtt_connected": mqtt_service.connected,
        "summary": {
            "temperature_c": c2["temperature_c"],
            "humidity_pct": c2["humidity_pct"],
            "light_adc": c2["light_adc"],
            "light_lux": c2["light_lux"],
            "is_dark": c2["is_dark"],
            "pir_motion": c1["pir"],
            "door_state": cam["door_state"],
            "servo_angle_deg": cam["servo_angle_deg"],
        },
        "nodes": snap,
    }


@router.get(
    "/api/sensors/history",
    response_model=List[SensorHistoryOut],
    summary="Lịch sử cảm biến phục vụ vẽ biểu đồ Recharts (LineChart / AreaChart)",
)
def get_sensors_history(
    cluster_id: Optional[str] = Query(
        default="esp32_cluster2",
        description="Lọc theo cụm (esp32_cluster2 hoặc esp32_cluster1, bỏ trống để lấy tất cả)",
    ),
    minutes: Optional[int] = Query(
        default=None,
        ge=1,
        le=10080,
        description="Chỉ lấy dữ liệu trong N phút gần nhất",
    ),
    limit: int = Query(default=60, ge=1, le=500, description="Số điểm dữ liệu tối đa"),
    db: Session = Depends(get_db),
) -> Any:
    query = db.query(SensorHistory)
    if cluster_id and cluster_id.lower() != "all":
        query = query.filter(SensorHistory.cluster_id == cluster_id)
    if minutes is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        query = query.filter(SensorHistory.created_at >= cutoff)

    rows = query.order_by(SensorHistory.id.desc()).limit(limit).all()
    # Đảo ngược lại theo thứ tự thời gian tăng dần để Recharts vẽ từ trái sang phải
    return list(reversed(rows))
