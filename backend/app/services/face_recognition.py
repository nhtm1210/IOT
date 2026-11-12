"""
Module Nhận diện khuôn mặt chủ nhà (AI Face Recognition Service) cho ESP32-CAM.
Kịch bản chuẩn theo `MQTT_SPEC.md`:
- So khớp ảnh JPEG chụp từ ESP32-CAM với mẫu mặt chủ nhà đã lưu tại `data/owner_faces/owner.jpg`.
- Phân biệt rõ 3 trạng thái:
  1. `KNOWN`   : Khớp khuôn mặt chủ nhà (confidence >= threshold) -> Quay Servo SG90 góc 90° mở cửa 5s.
  2. `UNKNOWN` : Có mặt nhưng không khớp chủ nhà -> Giữ khóa Servo SG90 ở góc 0°.
  3. `NO_FACE` : Không phát hiện khuôn mặt trong khung hình -> Giữ khóa Servo SG90 ở góc 0°.
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Tuple

from app.core.config import PROJECT_ROOT, settings
from app.core.database import db_session
from app.models.models import SystemSetting

logger = logging.getLogger("face_recognition")


def _sync_legacy_owner_face() -> None:
    """Đồng bộ ảnh chủ nhà từ `mqtt-sample/owner_faces/owner.jpg` sang `backend/data/owner_faces/owner.jpg` nếu có."""
    legacy_path = PROJECT_ROOT / "mqtt-sample" / "owner_faces" / "owner.jpg"
    if not settings.OWNER_FACE_PATH.exists() and legacy_path.exists():
        try:
            shutil.copyfile(legacy_path, settings.OWNER_FACE_PATH)
        except Exception:
            pass


def get_face_threshold() -> float:
    """Đọc ngưỡng độ tin cậy nhận diện từ bảng SystemSetting (mặc định 0.65)."""
    try:
        with db_session() as db:
            row = (
                db.query(SystemSetting)
                .filter(SystemSetting.key == "face_match_threshold")
                .first()
            )
            if row and row.value:
                return float(row.value)
    except Exception:
        pass
    return float(os.getenv("FACE_MATCH_THRESHOLD", str(settings.FACE_MATCH_THRESHOLD)))


def is_owner_face_enrolled() -> bool:
    _sync_legacy_owner_face()
    return settings.OWNER_FACE_PATH.exists() and settings.OWNER_FACE_PATH.stat().st_size > 100


def save_owner_face(image_bytes: bytes) -> Path:
    """Lưu ảnh mẫu mặt chủ nhà vào `data/owner_faces/owner.jpg`."""
    settings.OWNER_FACE_PATH.parent.mkdir(parents=True, exist_ok=True)
    settings.OWNER_FACE_PATH.write_bytes(image_bytes)
    # Đồng bộ sang thư mục mqtt-sample nếu tồn tại
    legacy_dir = PROJECT_ROOT / "mqtt-sample" / "owner_faces"
    if legacy_dir.exists():
        try:
            (legacy_dir / "owner.jpg").write_bytes(image_bytes)
        except Exception:
            pass
    return settings.OWNER_FACE_PATH


def match_owner_face(image_bytes: bytes) -> Tuple[str, str, float]:
    """
    So khớp ảnh JPEG gửi lên từ ESP32-CAM với mẫu khuôn mặt chủ nhà đã lưu sẵn.
    Trả về: `(identity, person_name, confidence)`
      - `identity` thuộc `{"KNOWN", "UNKNOWN", "NO_FACE"}`
    """
    _sync_legacy_owner_face()

    if not image_bytes or len(image_bytes) < 64:
        return ("NO_FACE", "none", 0.0)

    # Hỗ trợ biến môi trường MOCK_IDENTITY khi chạy kiểm thử tự động
    mock_identity = os.getenv("MOCK_IDENTITY", "").upper()
    if mock_identity == "KNOWN":
        return ("KNOWN", "Chu_Nha", 0.94)
    if mock_identity == "UNKNOWN":
        return ("UNKNOWN", "unknown", 0.38)
    if mock_identity == "NO_FACE":
        return ("NO_FACE", "none", 0.0)

    if not settings.OWNER_FACE_PATH.exists():
        logger.warning(
            "Chưa có ảnh mẫu mặt chủ nhà tại %s! Trả về UNKNOWN để giữ khóa cửa an toàn.",
            settings.OWNER_FACE_PATH,
        )
        return ("UNKNOWN", "unknown", 0.0)

    threshold = get_face_threshold()

    # Nếu ảnh gửi lên trùng khớp byte 100% với ảnh mẫu chủ nhà (ví dụ khi test bằng simulator/cùng file ảnh)
    try:
        owner_bytes = settings.OWNER_FACE_PATH.read_bytes()
        if image_bytes == owner_bytes:
            return ("KNOWN", "Chu_Nha", 0.98)
    except Exception:
        owner_bytes = b""

    try:
        import cv2
        import numpy as np

        np_arr = np.frombuffer(image_bytes, np.uint8)
        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        owner_img = cv2.imread(str(settings.OWNER_FACE_PATH), cv2.IMREAD_COLOR)
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

        if confidence >= threshold:
            return ("KNOWN", "Chu_Nha", round(confidence, 3))
        return ("UNKNOWN", "unknown", round(confidence, 3))

    except ImportError:
        logger.warning("Chưa cài đặt opencv-python; sử dụng chế độ so khớp dữ liệu ảnh cơ bản.")
        if image_bytes == owner_bytes:
            return ("KNOWN", "Chu_Nha", 0.96)
        return ("UNKNOWN", "unknown", 0.42)
