"""
API An ninh Camera AI & Kiểm soát cửa Servo SG90 (`/api/security/*` và `/api/recognitions`).
Hỗ trợ:
1. `POST /api/security/recognize`: Nhận ảnh JPEG từ ESP32-CAM (raw bytes) hoặc từ Web (multipart/form-data),
   đối chiếu với mẫu khuôn mặt chủ nhà, gửi lệnh MQTT quay Servo SG90 mở cửa (90°) nếu khớp (`KNOWN`)
   hoặc giữ khóa (0°) nếu không khớp (`UNKNOWN` / `NO_FACE`).
2. `POST /api/security/enroll`: Lưu mẫu khuôn mặt chủ nhà (`owner.jpg`) từ Web hoặc ESP32-CAM.
3. `GET  /api/security/owner-face`: Xem ảnh mẫu mặt chủ nhà hiện tại.
4. `GET  /api/security/images/{filename}`: Xem ảnh chụp sự kiện lịch sử nhận diện.
5. `GET  /api/recognitions`: Danh sách lịch sử nhận diện khuôn mặt & đóng/mở cửa.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import CAPTURED_EVENTS_DIR, settings
from app.core.database import db_session, get_db
from app.core.security import rate_limiter, require_operator, verify_device_api_key
from app.models.models import RecognitionHistory
from app.schemas.schemas import RecognitionOut
from app.services.face_recognition import (
    get_face_threshold,
    is_owner_face_enrolled,
    match_owner_face,
    save_owner_face,
)
from app.services.automation import automation_engine
from app.services.mqtt_service import mqtt_service
from app.websocket.manager import ws_manager

logger = logging.getLogger("security_ai_api")

router = APIRouter(tags=["5. AI Face Recognition & Smart Door"])


async def _extract_image_bytes(request: Request) -> bytes:
    """Hỗ trợ đọc ảnh JPEG từ cả raw body (`image/jpeg` của ESP32-CAM) lẫn `multipart/form-data` của Web."""
    content_type = request.headers.get("content-type", "").lower()
    if "multipart/form-data" in content_type:
        form = await request.form()
        upload = form.get("file") or form.get("image")
        if upload is not None and hasattr(upload, "read"):
            return await upload.read()
    return await request.body()


def _sanitize_event_id(raw_id: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_\-]", "_", raw_id.strip())
    return cleaned[:64] if cleaned else f"cam_evt_{int(time.time() * 1000)}"


@router.post(
    "/api/security/recognize",
    summary="Nhận ảnh JPEG từ ESP32-CAM (hoặc Web), nhận diện mặt chủ nhà & điều khiển cửa Servo SG90",
)
async def recognize_from_esp32_cam(
    request: Request,
    x_device_id: str = Header(default="esp32_cam_01"),
    x_event_id: str = Header(default=""),
    x_mode: str = Header(default="RECOGNIZE"),
    x_person_name: str = Header(default="Chu_Nha"),
    _auth: None = Depends(verify_device_api_key),
) -> Dict[str, Any]:
    client_ip = request.client.host if request.client else "esp32_cam"
    rate_limiter.check(f"recognize:{client_ip}", max_requests=30, window_seconds=60)

    image_bytes = await _extract_image_bytes(request)
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Body ảnh JPEG rỗng")

    event_id = _sanitize_event_id(x_event_id or f"cam_evt_{int(time.time() * 1000)}")

    # Trường hợp 1: Lưu mẫu mặt chủ nhà (Enroll)
    if x_mode.upper() == "ENROLL_OWNER":
        saved_path = save_owner_face(image_bytes)
        logger.info("Đã lưu ảnh mẫu khuôn mặt chủ nhà tại %s (%d bytes)", saved_path, len(image_bytes))
        ws_manager.broadcast_threadsafe(
            "OWNER_ENROLLED",
            {
                "event_id": event_id,
                "person_name": x_person_name,
                "owner_face_url": "/api/security/owner-face",
            },
        )
        return {
            "status": "enrolled",
            "event_id": event_id,
            "person_name": x_person_name,
            "owner_face_url": "/api/security/owner-face",
            "bytes": len(image_bytes),
        }

    # Trường hợp 2: Lưu ảnh sự kiện và đối chiếu với mẫu mặt chủ nhà
    filename = f"{event_id}.jpg"
    capture_file = CAPTURED_EVENTS_DIR / filename
    capture_file.write_bytes(image_bytes)
    image_url = f"/api/security/images/{filename}"

    identity, person_name, confidence = match_owner_face(image_bytes)
    authorized = identity == "KNOWN"

    command_payload = mqtt_service.send_door_access_decision(
        identity=identity,
        authorized=authorized,
        person_name=person_name,
        confidence=confidence,
        event_id=event_id,
        image_url=image_url,
        triggered_by="FACE_AI",
    )
    if event_id.startswith("motion_"):
        with db_session() as db:
            automation_engine.create_and_broadcast_alert(
                db=db,
                alert_type="MOTION_CAPTURE",
                severity="WARNING" if identity != "UNKNOWN" else "CRITICAL",
                cluster_id="esp32_cluster1",
                title="Phát hiện chuyển động - ảnh từ ESP32-CAM",
                message=(
                    f"Camera đã chụp ảnh sau sự kiện PIR. Kết quả AI: {identity}"
                    + (f" ({person_name}, {confidence * 100:.1f}%)." if person_name != "none" else ".")
                ),
                image_url=image_url,
                send_telegram=True,
            )
    command_payload["threshold"] = get_face_threshold()
    command_payload["servo_angle_deg"] = 90 if authorized else 0
    return command_payload


@router.post(
    "/api/security/enroll",
    summary="Upload / Lưu mẫu khuôn mặt chủ nhà từ giao diện Web (multipart/form-data hoặc raw JPEG)",
)
async def enroll_owner_from_web(
    request: Request,
    person_name: str = Query(default="Chu_Nha"),
    _user=Depends(require_operator),
) -> Dict[str, Any]:
    image_bytes = await _extract_image_bytes(request)
    if not image_bytes or len(image_bytes) < 64:
        raise HTTPException(
            status_code=400,
            detail="Vui lòng gửi file ảnh JPEG/PNG hợp lệ (field 'file' hoặc raw image body).",
        )

    saved_path = save_owner_face(image_bytes)
    event_id = f"enroll_{int(time.time() * 1000)}"
    ws_manager.broadcast_threadsafe(
        "OWNER_ENROLLED",
        {
            "event_id": event_id,
            "person_name": person_name,
            "owner_face_url": "/api/security/owner-face",
        },
    )
    return {
        "status": "enrolled",
        "event_id": event_id,
        "person_name": person_name,
        "owner_face_enrolled": True,
        "owner_face_url": "/api/security/owner-face",
        "saved_bytes": len(image_bytes),
        "saved_path": str(saved_path.name),
    }


@router.get(
    "/api/security/owner-face",
    summary="Lấy hình ảnh mẫu khuôn mặt chủ nhà đang lưu trên hệ thống",
)
def get_owner_face_image() -> Any:
    if not is_owner_face_enrolled():
        raise HTTPException(
            status_code=404,
            detail="Chưa lưu mẫu khuôn mặt chủ nhà (owner.jpg).",
        )
    return FileResponse(settings.OWNER_FACE_PATH, media_type="image/jpeg")


@router.get(
    "/api/security/images/{filename}",
    summary="Lấy hình ảnh chụp từ ESP32-CAM theo tên file sự kiện",
)
def get_captured_event_image(filename: str) -> Any:
    safe_name = re.sub(r"[^a-zA-Z0-9_\-\.]", "", filename)
    img_path = CAPTURED_EVENTS_DIR / safe_name
    if not img_path.exists() or not img_path.is_file():
        raise HTTPException(status_code=404, detail="Không tìm thấy ảnh sự kiện")
    return FileResponse(img_path, media_type="image/jpeg")


@router.get(
    "/api/recognitions",
    response_model=List[RecognitionOut],
    summary="Lịch sử nhận diện khuôn mặt & đóng/mở cửa Servo SG90",
)
def list_recognitions(
    identity: Optional[str] = Query(
        default=None, description="Lọc theo KNOWN, UNKNOWN hoặc NO_FACE"
    ),
    limit: int = Query(default=30, ge=1, le=200),
    db: Session = Depends(get_db),
) -> Any:
    query = db.query(RecognitionHistory)
    if identity:
        query = query.filter(RecognitionHistory.identity == identity.upper())
    return query.order_by(RecognitionHistory.id.desc()).limit(limit).all()
