"""
Server mẫu tích hợp sẵn MQTT + Nhận diện khuôn mặt chủ nhà (dành cho Thành viên 1 & Thành viên 2).
Chạy lệnh:
    uvicorn server_mqtt_sample:app --host 0.0.0.0 --port 8000 --reload
Mở trình duyệt tại:
    http://localhost:8000/docs
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional
import logging
import os
import socket
import time

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from broker import EmbeddedMqttBroker
from mqtt_handler import SmartHomeMqttService

logger = logging.getLogger("server_mqtt_sample")

BASE_DIR = Path(__file__).resolve().parent
OWNER_DIR = BASE_DIR / "owner_faces"
CAPTURE_DIR = BASE_DIR / "captured_events"
OWNER_DIR.mkdir(parents=True, exist_ok=True)
CAPTURE_DIR.mkdir(parents=True, exist_ok=True)

OWNER_FACE_PATH = OWNER_DIR / "owner.jpg"

# Khởi tạo dịch vụ MQTT dùng chung
mqtt_service = SmartHomeMqttService(
    broker_host=os.getenv("MQTT_HOST", "127.0.0.1"),
    broker_port=int(os.getenv("MQTT_PORT", "1883")),
    username=os.getenv("MQTT_USERNAME", ""),
    password=os.getenv("MQTT_PASSWORD", ""),
)

# Lưu lịch sử tạm thời trên RAM để kiểm tra nhanh (Thành viên 2 sẽ thay bằng SQLite/SQLAlchemy)
event_logs: List[Dict[str, Any]] = []


def _append_log(event_type: str, data: Any) -> None:
    event_logs.append(
        {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "type": event_type,
            "data": data,
        }
    )
    if len(event_logs) > 200:
        del event_logs[0 : len(event_logs) - 200]


# Gắn các callback mẫu (Thành viên 2 chỉ cần thay nội dung các hàm này bằng lệnh lưu Database)
mqtt_service.on_motion_event = lambda payload: _append_log("MOTION_EVENT", payload)
mqtt_service.on_cluster1_sensor = lambda payload: _append_log("CLUSTER1_SENSOR", payload)
mqtt_service.on_cluster2_sensor = lambda payload: _append_log("CLUSTER2_SENSOR", payload)
mqtt_service.on_device_ack = lambda dev_id, payload: _append_log(f"ACK_{dev_id}", payload)
mqtt_service.on_recognition_event = lambda payload: _append_log("RECOGNITION_EVENT", payload)


# =====================================================================
# HÀM NHẬN DIỆN KHUÔN MẶT CHỦ NHÀ (ĐÃ ĐƯỢC LƯU SẴN TRONG owner_faces/owner.jpg)
# =====================================================================
def match_owner_face(image_bytes: bytes) -> tuple[str, str, float]:
    """
    So khớp ảnh chụp từ ESP32-CAM với ảnh mặt chủ nhà đã lưu sẵn (`owner_faces/owner.jpg`).
    Trả về tuple: (identity, person_name, confidence)
      - identity = "KNOWN"   (khớp mặt chủ nhà -> quay Servo SG90 mở cửa)
      - identity = "UNKNOWN" (có mặt nhưng không khớp chủ nhà -> giữ khóa SG90)
      - identity = "NO_FACE" (không phát hiện khuôn mặt trong ảnh -> giữ khóa SG90)
    """
    if not image_bytes or len(image_bytes) < 100:
        return ("NO_FACE", "none", 0.0)

    # Nếu chưa lưu ảnh mẫu chủ nhà, báo UNKNOWN để không mở cửa nhầm
    if not OWNER_FACE_PATH.exists():
        logger.warning(
            "Chưa có ảnh mẫu chủ nhà tại %s! Hãy bấm 'Lưu mặt chủ nhà (Enroll)' trên trang ESP32-CAM.",
            OWNER_FACE_PATH,
        )
        return ("UNKNOWN", "unknown", 0.0)

    try:
        import cv2
        import numpy as np

        np_arr = np.frombuffer(image_bytes, np.uint8)
        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        owner_img = cv2.imread(str(OWNER_FACE_PATH), cv2.IMREAD_COLOR)
        if frame is None or owner_img is None:
            return ("NO_FACE", "none", 0.0)

        gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray_owner = cv2.cvtColor(owner_img, cv2.COLOR_BGR2GRAY)

        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        face_cascade = cv2.CascadeClassifier(cascade_path)

        faces_frame = face_cascade.detectMultiScale(
            gray_frame, scaleFactor=1.1, minNeighbors=5, minSize=(48, 48)
        )
        if len(faces_frame) == 0:
            return ("NO_FACE", "none", 0.0)

        # Lấy khuôn mặt lớn nhất trong ảnh chụp
        x, y, w, h = sorted(faces_frame, key=lambda b: b[2] * b[3], reverse=True)[0]
        face_roi = cv2.resize(gray_frame[y : y + h, x : x + w], (128, 128))
        face_roi = cv2.equalizeHist(face_roi)

        # Cắt khuôn mặt chủ nhà trong ảnh mẫu (hoặc dùng toàn ảnh nếu ảnh mẫu đã cắt sẵn)
        faces_owner = face_cascade.detectMultiScale(
            gray_owner, scaleFactor=1.1, minNeighbors=5, minSize=(48, 48)
        )
        if len(faces_owner) > 0:
            ox, oy, ow, oh = sorted(faces_owner, key=lambda b: b[2] * b[3], reverse=True)[0]
            owner_roi = cv2.resize(gray_owner[oy : oy + oh, ox : ox + ow], (128, 128))
        else:
            owner_roi = cv2.resize(gray_owner, (128, 128))
        owner_roi = cv2.equalizeHist(owner_roi)

        # Kết hợp độ tương đồng Histogram + Template Matching chuẩn hóa
        hist1 = cv2.calcHist([face_roi], [0], None, [64], [0, 256])
        hist2 = cv2.calcHist([owner_roi], [0], None, [64], [0, 256])
        cv2.normalize(hist1, hist1)
        cv2.normalize(hist2, hist2)
        hist_score = float(cv2.compareHist(hist1, hist2, cv2.HISTCMP_CORREL))

        tmpl_res = cv2.matchTemplate(face_roi, owner_roi, cv2.TM_CCOEFF_NORMED)
        tmpl_score = float(tmpl_res[0][0])

        confidence = max(0.0, min(1.0, 0.5 * max(0.0, hist_score) + 0.5 * max(0.0, tmpl_score)))
        threshold = float(os.getenv("FACE_MATCH_THRESHOLD", "0.65"))

        if confidence >= threshold:
            return ("KNOWN", "Chu_Nha", confidence)
        return ("UNKNOWN", "unknown", confidence)

    except ImportError:
        logger.warning(
            "Chưa cài đặt opencv-python; sử dụng so khớp byte cơ bản hoặc biến môi trường MOCK_IDENTITY."
        )
        mock_identity = os.getenv("MOCK_IDENTITY", "").upper()
        if mock_identity == "KNOWN":
            return ("KNOWN", "Chu_Nha", 0.95)
        if mock_identity == "NO_FACE":
            return ("NO_FACE", "none", 0.0)
        if image_bytes == OWNER_FACE_PATH.read_bytes():
            return ("KNOWN", "Chu_Nha", 1.0)
        return ("UNKNOWN", "unknown", 0.40)


def _is_port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


# =====================================================================
# KHỞI TẠO FASTAPI APP & SCHEMAS
# =====================================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    embedded_broker: Optional[EmbeddedMqttBroker] = None
    # Nếu chưa bật Docker hay Mosquitto ở cổng 1883, tự động bật MQTT Broker tích hợp sẵn
    if mqtt_service.broker_host in ("127.0.0.1", "localhost", "0.0.0.0") and not _is_port_in_use(
        "127.0.0.1", mqtt_service.broker_port
    ):
        logger.info(
            "Không tìm thấy Mosquitto/Docker ở cổng %d -> Tự động khởi chạy EmbeddedMqttBroker...",
            mqtt_service.broker_port,
        )
        embedded_broker = EmbeddedMqttBroker(host="0.0.0.0", port=mqtt_service.broker_port)
        await embedded_broker.start()

    mqtt_service.start()
    yield
    mqtt_service.stop()
    if embedded_broker is not None:
        await embedded_broker.stop()


app = FastAPI(
    title="Smart Home IoT - MQTT & AI Recognition Sample Server",
    description="Server mẫu giao tiếp MQTT với 3 cụm ESP32 để Thành viên 2 phát triển Backend",
    version="1.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class Cluster1CommandRequest(BaseModel):
    mode: str = Field(default="MANUAL", description="AUTO hoặc MANUAL")
    light: Optional[bool] = Field(default=None, description="True = Bật đèn, False = Tắt đèn")
    buzzer: Optional[bool] = Field(default=None, description="True = Bật còi, False = Tắt còi")


class Cluster2CommandRequest(BaseModel):
    mode: str = Field(default="MANUAL", description="AUTO hoặc MANUAL")
    light: Optional[bool] = Field(default=None, description="True = Bật đèn, False = Tắt đèn")
    fan: Optional[bool] = Field(default=None, description="True = Bật quạt, False = Tắt quạt")


class CamDoorCommandRequest(BaseModel):
    identity: str = Field(default="KNOWN", description="KNOWN, UNKNOWN hoặc NO_FACE")
    authorized: bool = Field(default=True, description="True = Mở cửa SG90 (90°), False = Giữ khóa (0°)")
    person_name: str = Field(default="Chu_Nha")
    confidence: float = Field(default=0.95)
    event_id: Optional[str] = None


# =====================================================================
# ENDPOINTS GIAO TIẾP VỚI 3 CỤM ESP32
# =====================================================================
@app.get("/api/mqtt/state", summary="Xem trạng thái thời gian thực của cả 3 cụm ESP32")
def get_mqtt_state() -> Dict[str, Any]:
    return {
        "mqtt_connected": mqtt_service.connected,
        "broker": f"{mqtt_service.broker_host}:{mqtt_service.broker_port}",
        "owner_face_enrolled": OWNER_FACE_PATH.exists(),
        "nodes": mqtt_service.get_snapshot(),
    }


@app.get("/api/mqtt/logs", summary="Xem lịch sử các bản tin MQTT gần nhất")
def get_mqtt_logs() -> Dict[str, Any]:
    return {"count": len(event_logs), "items": list(reversed(event_logs[-50:]))}


@app.post("/api/mqtt/cluster1/control", summary="Điều khiển Cụm ESP 1 (Đèn + Còi + AUTO/MANUAL)")
def control_cluster1(req: Cluster1CommandRequest) -> Dict[str, Any]:
    if req.mode not in ("AUTO", "MANUAL"):
        raise HTTPException(status_code=400, detail="mode phải là AUTO hoặc MANUAL")
    sent = mqtt_service.control_cluster1(mode=req.mode, light=req.light, buzzer=req.buzzer)
    return {"status": "published", "command": sent}


@app.post("/api/mqtt/cluster2/control", summary="Điều khiển Cụm ESP 2 (Đèn + Quạt + AUTO/MANUAL)")
def control_cluster2(req: Cluster2CommandRequest) -> Dict[str, Any]:
    if req.mode not in ("AUTO", "MANUAL"):
        raise HTTPException(status_code=400, detail="mode phải là AUTO hoặc MANUAL")
    sent = mqtt_service.control_cluster2(mode=req.mode, light=req.light, fan=req.fan)
    return {"status": "published", "command": sent}


@app.post("/api/mqtt/cam/door", summary="Test gửi lệnh mở/khóa cửa Servo SG90 xuống ESP32-CAM")
def control_cam_door(req: CamDoorCommandRequest) -> Dict[str, Any]:
    sent = mqtt_service.send_door_access_decision(
        identity=req.identity,
        authorized=req.authorized,
        person_name=req.person_name,
        confidence=req.confidence,
        event_id=req.event_id,
    )
    return {"status": "published", "command": sent}


@app.post("/api/mqtt/cam/capture", summary="Yêu cầu ESP32-CAM chụp ảnh ngay qua MQTT")
def trigger_cam_capture() -> Dict[str, Any]:
    sent = mqtt_service.request_camera_capture()
    return {"status": "published", "command": sent}


@app.post(
    "/api/security/recognize",
    summary="Endpoint nhận ảnh JPEG từ ESP32-CAM, đối chiếu mặt chủ nhà và điều khiển cửa SG90",
)
async def recognize_from_esp32_cam(
    request: Request,
    x_device_id: str = Header(default="esp32_cam_01"),
    x_event_id: str = Header(default=""),
    x_mode: str = Header(default="RECOGNIZE"),
    x_person_name: str = Header(default="Chu_Nha"),
) -> Dict[str, Any]:
    image_bytes = await request.body()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Body ảnh JPEG rỗng")

    event_id = x_event_id or f"cam_evt_{int(time.time() * 1000)}"

    # Nếu ESP32-CAM gửi kèm header X-Mode: ENROLL_OWNER -> Lưu làm ảnh mẫu mặt chủ nhà
    if x_mode.upper() == "ENROLL_OWNER":
        OWNER_FACE_PATH.write_bytes(image_bytes)
        logger.info("Đã lưu ảnh mẫu khuôn mặt chủ nhà tại %s (%d bytes)", OWNER_FACE_PATH, len(image_bytes))
        _append_log("OWNER_ENROLLED", {"event_id": event_id, "bytes": len(image_bytes)})
        return {
            "status": "enrolled",
            "event_id": event_id,
            "person_name": x_person_name,
            "saved_path": str(OWNER_FACE_PATH),
        }

    # Lưu ảnh sự kiện để đối chiếu/audit
    capture_file = CAPTURE_DIR / f"{event_id}.jpg"
    capture_file.write_bytes(image_bytes)

    # Đối chiếu với mặt chủ nhà đã lưu sẵn
    identity, person_name, confidence = match_owner_face(image_bytes)
    authorized = identity == "KNOWN"

    # Gửi lệnh MQTT xuống ESP32-CAM:
    # - Nếu khớp mặt chủ nhà (KNOWN): action="OPEN" -> Servo SG90 quay 90 độ mở cửa
    # - Nếu không khớp (UNKNOWN / NO_FACE): action="KEEP_LOCKED" -> Servo SG90 giữ nguyên 0 độ
    command_payload = mqtt_service.send_door_access_decision(
        identity=identity,
        authorized=authorized,
        person_name=person_name,
        confidence=confidence,
        event_id=event_id,
    )

    _append_log("FACE_RECOGNITION_DECISION", command_payload)
    return command_payload


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server_mqtt_sample:app", host="0.0.0.0", port=8000, reload=False)

