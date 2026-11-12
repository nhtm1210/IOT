"""
Định nghĩa toàn bộ các bảng Cơ sở dữ liệu SQLAlchemy 2.0 cho hệ thống Smart Home IoT AI.
Bao gồm:
1. User: Tài khoản người dùng & Phân quyền (ADMIN, USER, GUEST)
2. Device: Danh sách thiết bị đầu ra trên 3 cụm ESP32
3. SensorHistory: Lịch sử thông số nhiệt độ, độ ẩm, ánh sáng, chuyển động PIR
4. DeviceHistory: Nhật ký lệnh điều khiển & phản hồi ACK từ ESP32
5. RecognitionHistory: Nhật ký nhận diện khuôn mặt & đóng/mở cửa Servo SG90
6. AutomationRule: Các kịch bản tự động hóa
7. Alert: Cảnh báo an ninh & môi trường
8. SystemSetting: Cấu hình hệ thống & ngưỡng tự động
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.config import settings
from app.core.database import Base, engine
from app.core.security import get_password_hash


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(120), default="")
    role: Mapped[str] = mapped_column(String(20), default="USER")  # ADMIN | USER | GUEST
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # light_1, buzzer_1, light_2, fan_1, door_servo_1
    cluster_id: Mapped[str] = mapped_column(String(64), index=True)  # esp32_cluster1, esp32_cluster2, esp32_cam_01
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    device_type: Mapped[str] = mapped_column(String(40), nullable=False)  # LIGHT, BUZZER, FAN, SERVO
    gpio_pin: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(20), default="OFF")  # ON / OFF / OPEN / LOCKED
    mode: Mapped[str] = mapped_column(String(20), default="AUTO")  # AUTO / MANUAL
    online: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class SensorHistory(Base):
    __tablename__ = "sensor_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    cluster_id: Mapped[str] = mapped_column(String(64), index=True)
    temperature_c: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    humidity_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    light_adc: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    light_lux: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_dark: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    pir: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    light_state: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    fan_state: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    buzzer_state: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )


class DeviceHistory(Base):
    __tablename__ = "device_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    command_id: Mapped[str] = mapped_column(String(64), index=True)
    cluster_id: Mapped[str] = mapped_column(String(64), index=True)
    device_id: Mapped[str] = mapped_column(String(64), index=True)
    action: Mapped[str] = mapped_column(String(64))  # SET_OUTPUT, SET_MODE, DOOR_CONTROL, ACK
    state: Mapped[str] = mapped_column(String(64))  # ON, OFF, OPEN, LOCKED, AUTO, MANUAL
    mode: Mapped[str] = mapped_column(String(20), default="MANUAL")
    triggered_by: Mapped[str] = mapped_column(String(40), default="WEB_USER")  # WEB_USER, AUTO, PIR, FACE_AI
    ack_received: Mapped[bool] = mapped_column(Boolean, default=False)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    error: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    payload_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )


class RecognitionHistory(Base):
    __tablename__ = "recognition_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    event_id: Mapped[str] = mapped_column(String(64), index=True)
    command_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    device_id: Mapped[str] = mapped_column(String(64), default="esp32_cam_01")
    identity: Mapped[str] = mapped_column(String(20), index=True)  # KNOWN | UNKNOWN | NO_FACE
    person_name: Mapped[str] = mapped_column(String(80), default="unknown")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    authorized: Mapped[bool] = mapped_column(Boolean, default=False)
    door_action: Mapped[str] = mapped_column(String(30), default="KEEP_LOCKED")  # OPEN | KEEP_LOCKED
    door_state: Mapped[str] = mapped_column(String(20), default="LOCKED")  # OPEN | LOCKED
    servo_angle_deg: Mapped[int] = mapped_column(Integer, default=0)  # 0 hoặc 90
    image_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )


class AutomationRule(Base):
    __tablename__ = "automation_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    cluster_id: Mapped[str] = mapped_column(String(64), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    config_json: Mapped[str] = mapped_column(Text, default="{}")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    def get_config(self) -> Dict[str, Any]:
        try:
            return json.loads(self.config_json or "{}")
        except Exception:
            return {}


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    alert_type: Mapped[str] = mapped_column(String(50), index=True)  # MOTION_DETECTED, STRANGER_DETECTED, HIGH_TEMP...
    severity: Mapped[str] = mapped_column(String(20), default="WARNING")  # INFO | WARNING | CRITICAL
    cluster_id: Mapped[str] = mapped_column(String(64), default="system")
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    telegram_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    image_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )


class SystemSetting(Base):
    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(String(255), default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


# =====================================================================
# KHỞI TẠO BẢNG & DỮ LIỆU MẪU BAN ĐẦU (SEEDING)
# =====================================================================
def init_db_and_seed(db: Session) -> None:
    """Tạo toàn bộ bảng và chèn dữ liệu mặc định nếu Database mới khởi tạo."""
    Base.metadata.create_all(bind=engine)

    # 1. Seed Users (admin, user, guest)
    if db.query(User).count() == 0:
        default_users = [
            User(
                username="admin",
                hashed_password=get_password_hash("admin123"),
                full_name="Quản trị viên (Chủ nhà)",
                role="ADMIN",
                is_active=True,
            ),
            User(
                username="user",
                hashed_password=get_password_hash("user123"),
                full_name="Thành viên gia đình",
                role="USER",
                is_active=True,
            ),
            User(
                username="guest",
                hashed_password=get_password_hash("guest123"),
                full_name="Khách (Chỉ xem)",
                role="GUEST",
                is_active=True,
            ),
        ]
        db.add_all(default_users)

    # 2. Seed 5 thiết bị đầu ra trên 3 cụm ESP32 đúng sơ đồ chân pins.h
    if db.query(Device).count() == 0:
        default_devices = [
            Device(
                id="light_1",
                cluster_id="esp32_cluster1",
                name="Đèn Cảnh Báo Cụm 1 (PIR)",
                device_type="LIGHT",
                gpio_pin=26,
                state="OFF",
                mode="AUTO",
                online=False,
            ),
            Device(
                id="buzzer_1",
                cluster_id="esp32_cluster1",
                name="Còi Báo Động Cụm 1 (Buzzer)",
                device_type="BUZZER",
                gpio_pin=25,
                state="OFF",
                mode="AUTO",
                online=False,
            ),
            Device(
                id="light_2",
                cluster_id="esp32_cluster2",
                name="Đèn Chiếu Sáng Phòng (Cụm 2)",
                device_type="LIGHT",
                gpio_pin=2,
                state="OFF",
                mode="AUTO",
                online=False,
            ),
            Device(
                id="fan_1",
                cluster_id="esp32_cluster2",
                name="Quạt Làm Mát Phòng (MOSFET Cụm 2)",
                device_type="FAN",
                gpio_pin=5,
                state="OFF",
                mode="AUTO",
                online=False,
            ),
            Device(
                id="door_servo_1",
                cluster_id="esp32_cam_01",
                name="Khóa Cửa Thông Minh (Servo SG90)",
                device_type="SERVO",
                gpio_pin=13,
                state="LOCKED",
                mode="AUTO",
                online=False,
            ),
        ]
        db.add_all(default_devices)

    # 3. Seed 4 kịch bản tự động hóa khớp với WEB_DASHBOARD_SPEC.md
    if db.query(AutomationRule).count() == 0:
        default_rules = [
            AutomationRule(
                code="RULE_C1_PIR_ALARM",
                name="Kịch bản Cụm ESP 1 — Phát hiện chuyển động bật Còi & Đèn",
                cluster_id="esp32_cluster1",
                description=(
                    "Khi cảm biến PIR (GPIO27) phát hiện có người chuyển động, lập tức bật Đèn LED (GPIO26) "
                    "và Còi Buzzer (GPIO25) trong 5 giây sau lần chuyển động cuối cùng rồi tự tắt."
                ),
                is_enabled=True,
                config_json=json.dumps(
                    {
                        "hold_seconds": 5,
                        "turn_on_light": True,
                        "turn_on_buzzer": True,
                        "trigger_camera_capture": True,
                    },
                    ensure_ascii=False,
                ),
            ),
            AutomationRule(
                code="RULE_C2_TEMP_HUM_FAN",
                name="Kịch bản Cụm ESP 2 — Nhiệt độ cao & Độ ẩm thấp bật Quạt",
                cluster_id="esp32_cluster2",
                description=(
                    "Khi Nhiệt độ >= 30.0°C VÀ Độ ẩm <= 40.0% thì tự động bật Quạt (GPIO5); "
                    "nếu không thỏa điều kiện sẽ tự động tắt Quạt."
                ),
                is_enabled=True,
                config_json=json.dumps(
                    {
                        "temp_threshold_c": 30.0,
                        "humidity_max_pct": 40.0,
                        "target_device": "fan_1",
                    },
                    ensure_ascii=False,
                ),
            ),
            AutomationRule(
                code="RULE_C2_LIGHT_LDR",
                name="Kịch bản Cụm ESP 2 — Cảm biến ánh sáng tự động bật/tắt Đèn",
                cluster_id="esp32_cluster2",
                description=(
                    "Khi trời tối (LDR ADC < 2000) sẽ tự động bật Đèn (GPIO2); "
                    "khi trời sáng (LDR ADC >= 2000) sẽ tự động tắt Đèn."
                ),
                is_enabled=True,
                config_json=json.dumps(
                    {
                        "light_adc_threshold": 2000,
                        "light_lux_threshold": 50.0,
                        "target_device": "light_2",
                    },
                    ensure_ascii=False,
                ),
            ),
            AutomationRule(
                code="RULE_CAM_FACE_DOOR",
                name="Kịch bản ESP32-CAM — Nhận diện mặt chủ nhà mở cửa Servo SG90",
                cluster_id="esp32_cam_01",
                description=(
                    "Khi ảnh chụp khớp với khuôn mặt chủ nhà đã lưu sẵn (Confidence >= 65%), "
                    "quay động cơ Servo SG90 góc 90° mở cửa trong 5 giây rồi đóng về 0°; "
                    "nếu không khớp thì giữ nguyên ở góc 0° (khóa cửa)."
                ),
                is_enabled=True,
                config_json=json.dumps(
                    {
                        "confidence_threshold": 0.65,
                        "open_angle_deg": 90,
                        "locked_angle_deg": 0,
                        "open_duration_sec": 5,
                        "alert_on_unknown": True,
                    },
                    ensure_ascii=False,
                ),
            ),
        ]
        db.add_all(default_rules)

    # 4. Seed System Settings
    if db.query(SystemSetting).count() == 0:
        default_settings = [
            SystemSetting(
                key="temp_threshold_c",
                value="30.0",
                description="Ngưỡng nhiệt độ (°C) kích hoạt quạt Cụm 2",
            ),
            SystemSetting(
                key="humidity_threshold_pct",
                value="40.0",
                description="Ngưỡng độ ẩm tối đa (%) kết hợp nhiệt độ cao để bật quạt Cụm 2",
            ),
            SystemSetting(
                key="light_adc_threshold",
                value="2000",
                description="Ngưỡng ADC ánh sáng phân biệt Trời tối (< 2000) và Trời sáng (>= 2000)",
            ),
            SystemSetting(
                key="pir_hold_seconds",
                value="5",
                description="Thời gian duy trì đèn & còi Cụm 1 sau khi hết chuyển động (giây)",
            ),
            SystemSetting(
                key="face_match_threshold",
                value=str(settings.FACE_MATCH_THRESHOLD),
                description="Ngưỡng độ tin cậy nhận diện mặt chủ nhà (0.0 - 1.0)",
            ),
            SystemSetting(
                key="door_open_seconds",
                value="5",
                description="Thời gian mở cửa Servo SG90 (90°) trước khi tự đóng về 0° (giây)",
            ),
            SystemSetting(
                key="security_armed",
                value="true",
                description="Bật/tắt chế độ cảnh báo an ninh (gửi thông báo khi có chuyển động/người lạ)",
            ),
            SystemSetting(
                key="telegram_enabled",
                value="true" if settings.TELEGRAM_ENABLED else "false",
                description="Bật/tắt gửi cảnh báo qua Telegram Bot",
            ),
            SystemSetting(
                key="telegram_bot_token",
                value=settings.TELEGRAM_BOT_TOKEN,
                description="Telegram Bot Token",
            ),
            SystemSetting(
                key="telegram_chat_id",
                value=settings.TELEGRAM_CHAT_ID,
                description="Telegram Chat ID nhận cảnh báo",
            ),
        ]
        db.add_all(default_settings)

    # 5. Seed dữ liệu cảm biến mẫu ban đầu để biểu đồ Recharts của Frontend có dữ liệu hiển thị ngay
    if db.query(SensorHistory).count() == 0:
        now = utc_now()
        sample_points = [
            (28.4, 52.0, 2500, 210.0, False, False, False),
            (29.1, 46.5, 2200, 140.0, False, False, False),
            (30.2, 39.5, 1800, 35.0, True, True, True),
            (31.0, 37.8, 1550, 22.0, True, True, True),
            (31.5, 36.2, 1400, 18.0, True, True, True),
            (29.6, 44.0, 2350, 185.0, False, False, False),
        ]
        for idx, (temp, hum, adc, lux, dark, light_on, fan_on) in enumerate(sample_points):
            ts = now - timedelta(minutes=(len(sample_points) - idx) * 2)
            db.add(
                SensorHistory(
                    cluster_id="esp32_cluster2",
                    temperature_c=temp,
                    humidity_pct=hum,
                    light_adc=adc,
                    light_lux=lux,
                    is_dark=dark,
                    pir=False,
                    light_state=light_on,
                    fan_state=fan_on,
                    buzzer_state=False,
                    created_at=ts,
                )
            )

    db.commit()
