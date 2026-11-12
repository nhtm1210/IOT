"""
Bộ máy Tự động hóa & Cảnh báo thông minh (Automation & Alert Engine).
Tuân thủ nghiêm ngặt quy tắc an toàn trong `TONG_QUAN_DU_AN_SMART_HOME_IOT.md`:
1. Chế độ `AUTO` tuyệt đối KHÔNG tự ý ghi đè khi cụm thiết bị đang ở chế độ `MANUAL`.
2. Phân biệt rõ `KNOWN` (Chủ nhà), `UNKNOWN` (Có khuôn mặt nhưng không khớp mẫu chủ nhà) và `NO_FACE` (Không có khuôn mặt trong khung hình).
3. Chống spam cảnh báo bằng cơ chế Cooldown theo từng loại sự kiện.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.models.models import Alert, AutomationRule, SystemSetting
from app.services.telegram_bot import telegram_service
from app.websocket.manager import ws_manager

logger = logging.getLogger("automation_engine")


class AutomationEngine:
    def __init__(self) -> None:
        self._last_alert_ts: Dict[str, float] = {}
        self.alert_cooldown_sec: float = 30.0

    def _can_emit_alert(self, key: str, cooldown_sec: Optional[float] = None) -> bool:
        now = time.monotonic()
        cd = cooldown_sec if cooldown_sec is not None else self.alert_cooldown_sec
        last = self._last_alert_ts.get(key, 0.0)
        if now - last < cd:
            return False
        self._last_alert_ts[key] = now
        return True

    @staticmethod
    def _is_security_armed(db: Session) -> bool:
        row = db.query(SystemSetting).filter(SystemSetting.key == "security_armed").first()
        if not row:
            return True
        return row.value.lower() in ("true", "1", "yes")

    @staticmethod
    def _is_rule_enabled(db: Session, code: str) -> tuple[bool, Dict[str, Any]]:
        rule = db.query(AutomationRule).filter(AutomationRule.code == code).first()
        if not rule:
            return True, {}
        return rule.is_enabled, rule.get_config()

    def create_and_broadcast_alert(
        self,
        db: Session,
        alert_type: str,
        severity: str,
        cluster_id: str,
        title: str,
        message: str,
        image_url: Optional[str] = None,
        send_telegram: bool = True,
    ) -> Alert:
        alert = Alert(
            alert_type=alert_type,
            severity=severity,
            cluster_id=cluster_id,
            title=title,
            message=message,
            is_read=False,
            telegram_sent=False,
            image_url=image_url,
        )
        db.add(alert)
        db.flush()

        alert_dict = {
            "id": alert.id,
            "alert_type": alert.alert_type,
            "severity": alert.severity,
            "cluster_id": alert.cluster_id,
            "title": alert.title,
            "message": alert.message,
            "is_read": alert.is_read,
            "image_url": alert.image_url,
            "created_at": alert.created_at.isoformat() if alert.created_at else None,
        }
        ws_manager.broadcast_threadsafe("NEW_ALERT", alert_dict)

        if send_telegram and self._is_security_armed(db):
            telegram_service.send_alert_background(
                title=title,
                message=message,
                severity=severity,
            )
            alert.telegram_sent = True

        return alert

    def evaluate_motion_event(self, db: Session, payload: Dict[str, Any]) -> None:
        """Xử lý khi Cụm 1 phát hiện chuyển động PIR."""
        pir = bool(payload.get("pir", False))
        if not pir:
            return

        enabled, _ = self._is_rule_enabled(db, "RULE_C1_PIR_ALARM")
        if not enabled:
            return

        if not self._can_emit_alert("motion_cluster1", cooldown_sec=15.0):
            return

        outputs = payload.get("outputs") or {}
        light_on = outputs.get("light", True)
        buzzer_on = outputs.get("buzzer", True)
        self.create_and_broadcast_alert(
            db=db,
            alert_type="MOTION_DETECTED",
            severity="WARNING",
            cluster_id="esp32_cluster1",
            title="Phát hiện chuyển động tại Cụm ESP 1",
            message=(
                f"Cảm biến PIR (GPIO27) ghi nhận chuyển động. "
                f"Trạng thái phản ứng: Đèn={'BẬT' if light_on else 'TẮT'}, "
                f"Còi={'KÊU' if buzzer_on else 'TẮT'}."
            ),
            send_telegram=True,
        )

    def evaluate_cluster2_sensor(self, db: Session, payload: Dict[str, Any]) -> None:
        """
        Đánh giá dữ liệu cảm biến Cụm 2 (Nhiệt độ, Độ ẩm, Ánh sáng).
        Quy tắc an toàn: Nếu Cụm 2 đang ở chế độ `MANUAL`, không tự ý ghi đè thiết bị.
        """
        temp = payload.get("temperature_c")
        hum = payload.get("humidity_pct")
        mode = payload.get("mode", "AUTO")
        outputs = payload.get("outputs") or {}

        enabled, cfg = self._is_rule_enabled(db, "RULE_C2_TEMP_HUM_FAN")
        if not enabled:
            return

        temp_threshold = float(cfg.get("temp_threshold_c", 30.0))
        hum_threshold = float(cfg.get("humidity_max_pct", 40.0))

        if temp is not None and hum is not None:
            if float(temp) >= temp_threshold and float(hum) <= hum_threshold:
                if self._can_emit_alert("high_temp_low_hum_c2", cooldown_sec=60.0):
                    fan_status = "Đang BẬT (AUTO)" if outputs.get("fan") else f"Đang TẮT (Chế độ {mode})"
                    self.create_and_broadcast_alert(
                        db=db,
                        alert_type="ENVIRONMENT_THRESHOLD",
                        severity="INFO" if mode == "AUTO" else "WARNING",
                        cluster_id="esp32_cluster2",
                        title="Nhiệt độ cao & Độ ẩm thấp tại Cụm ESP 2",
                        message=(
                            f"Nhiệt độ đạt {temp}°C (>= {temp_threshold}°C) và Độ ẩm {hum}% (<= {hum_threshold}%). "
                            f"Trạng thái Quạt: {fan_status}."
                        ),
                        send_telegram=False,
                    )

    def evaluate_face_recognition(
        self,
        db: Session,
        identity: str,
        person_name: str,
        confidence: float,
        authorized: bool,
        image_url: Optional[str] = None,
    ) -> None:
        """
        Đánh giá kết quả nhận diện khuôn mặt từ ESP32-CAM:
        - `KNOWN`: Khớp chủ nhà -> mở cửa SG90 (90°).
        - `UNKNOWN`: Có khuôn mặt nhưng không khớp chủ nhà -> cảnh báo an ninh, giữ khóa cửa (0°).
        - `NO_FACE`: Không thấy khuôn mặt trong ảnh -> giữ khóa cửa (0°), không báo động giả là người lạ.
        """
        enabled, cfg = self._is_rule_enabled(db, "RULE_CAM_FACE_DOOR")
        if not enabled:
            return

        if identity == "KNOWN" and authorized:
            if self._can_emit_alert("owner_door_open", cooldown_sec=10.0):
                self.create_and_broadcast_alert(
                    db=db,
                    alert_type="DOOR_OPENED_OWNER",
                    severity="INFO",
                    cluster_id="esp32_cam_01",
                    title="Chủ nhà đã mở cửa (Servo SG90 -> 90°)",
                    message=(
                        f"Nhận diện khớp khuôn mặt chủ nhà ({person_name}) với độ tin cậy "
                        f"{confidence * 100:.1f}%. Động cơ Servo SG90 đã quay 90° mở cửa trong 5 giây."
                    ),
                    image_url=image_url,
                    send_telegram=False,
                )
        elif identity == "UNKNOWN" and cfg.get("alert_on_unknown", True):
            if self._can_emit_alert("unknown_face_cam", cooldown_sec=10.0):
                self.create_and_broadcast_alert(
                    db=db,
                    alert_type="STRANGER_DETECTED",
                    severity="CRITICAL",
                    cluster_id="esp32_cam_01",
                    title="CẢNH BÁO: Phát hiện khuôn mặt không khớp chủ nhà!",
                    message=(
                        f"Camera trước cửa phát hiện khuôn mặt chưa xác định (UNKNOWN, độ tương đồng "
                        f"{confidence * 100:.1f}% < ngưỡng cho phép). Cửa Servo SG90 được giữ KHÓA (0°)."
                    ),
                    image_url=image_url,
                    send_telegram=True,
                )


automation_engine = AutomationEngine()
