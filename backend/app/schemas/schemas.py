"""
Định nghĩa toàn bộ Pydantic v2 Schemas cho Request / Response của Backend.
Khớp 100% với đặc tả trong `MQTT_SPEC.md`, `WEB_DASHBOARD_SPEC.md` và `TONG_QUAN_DU_AN_SMART_HOME_IOT.md`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


# =====================================================================
# 1. AUTHENTICATION & USERS
# =====================================================================
class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64, examples=["admin"])
    password: str = Field(..., min_length=1, max_length=128, examples=["admin123"])


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    full_name: str
    role: str
    is_active: bool
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


class UserCreateRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=4, max_length=128)
    full_name: str = Field(default="")
    role: str = Field(default="USER", description="ADMIN | USER | GUEST")


class UserUpdateRequest(BaseModel):
    full_name: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None


# =====================================================================
# 2. MQTT CLUSTER COMMAND SCHEMAS (Khớp với WEB_DASHBOARD_SPEC.md)
# =====================================================================
class Cluster1CommandRequest(BaseModel):
    mode: str = Field(default="MANUAL", description="AUTO hoặc MANUAL")
    light: Optional[bool] = Field(default=None, description="True = Bật đèn Cụm 1 (GPIO26), False = Tắt")
    buzzer: Optional[bool] = Field(default=None, description="True = Bật còi Cụm 1 (GPIO25), False = Tắt")


class Cluster2CommandRequest(BaseModel):
    mode: str = Field(default="MANUAL", description="AUTO hoặc MANUAL")
    light: Optional[bool] = Field(default=None, description="True = Bật đèn Cụm 2 (GPIO2), False = Tắt")
    fan: Optional[bool] = Field(default=None, description="True = Bật quạt Cụm 2 (GPIO5), False = Tắt")


class CamDoorCommandRequest(BaseModel):
    identity: str = Field(default="KNOWN", description="KNOWN, UNKNOWN hoặc NO_FACE")
    authorized: bool = Field(
        default=True, description="True = Mở cửa Servo SG90 (90°), False = Giữ khóa (0°)"
    )
    person_name: str = Field(default="Admin")
    confidence: float = Field(default=0.99, ge=0.0, le=1.0)
    event_id: Optional[str] = None
    close: bool = Field(default=False, description="True = đóng cửa theo lệnh thủ công từ Web")


# =====================================================================
# 3. GENERAL DEVICE CONTROL SCHEMAS (Khớp với TONG_QUAN_DU_AN_SMART_HOME_IOT.md)
# =====================================================================
class DeviceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    cluster_id: str
    name: str
    device_type: str
    gpio_pin: int
    state: str
    mode: str
    online: bool
    updated_at: datetime


class DeviceControlRequest(BaseModel):
    """
    Hỗ trợ cả điều khiển từng thiết bị đơn lẻ (`device_id`: `light_1`, `buzzer_1`, `light_2`, `fan_1`, `door_servo_1`)
    hoặc điều khiển theo cụm (`esp32_cluster1`, `esp32_cluster2`, `esp32_cam_01`).
    """

    device_id: str = Field(
        ...,
        description="ID thiết bị (light_1, buzzer_1, light_2, fan_1, door_servo_1) hoặc ID cụm (esp32_cluster1, esp32_cluster2, esp32_cam_01)",
        examples=["fan_1"],
    )
    state: Optional[str] = Field(
        default=None,
        description="ON / OFF / OPEN / LOCKED",
        examples=["ON"],
    )
    mode: str = Field(
        default="MANUAL",
        description="AUTO hoặc MANUAL",
        examples=["MANUAL"],
    )
    outputs: Optional[Dict[str, bool]] = Field(
        default=None,
        description="Tùy chọn điều khiển gộp nhiều đầu ra cùng lúc",
    )


class DeviceHistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    command_id: str
    cluster_id: str
    device_id: str
    action: str
    state: str
    mode: str
    triggered_by: str
    ack_received: bool
    success: bool
    error: Optional[str] = None
    created_at: datetime


# =====================================================================
# 4. SENSORS SCHEMAS
# =====================================================================
class SensorHistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    cluster_id: str
    temperature_c: Optional[float] = None
    humidity_pct: Optional[float] = None
    light_adc: Optional[int] = None
    light_lux: Optional[float] = None
    is_dark: Optional[bool] = None
    pir: Optional[bool] = None
    light_state: Optional[bool] = None
    fan_state: Optional[bool] = None
    buzzer_state: Optional[bool] = None
    created_at: datetime


# =====================================================================
# 5. RECOGNITION & AI SECURITY SCHEMAS
# =====================================================================
class RecognitionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_id: str
    command_id: Optional[str] = None
    device_id: str
    identity: str
    person_name: str
    confidence: float
    authorized: bool
    door_action: str
    door_state: str
    servo_angle_deg: int
    image_url: Optional[str] = None
    created_at: datetime


# =====================================================================
# 6. AUTOMATION RULES SCHEMAS
# =====================================================================
class AutomationRuleOut(BaseModel):
    id: int
    code: str
    name: str
    cluster_id: str
    description: str
    is_enabled: bool
    config: Dict[str, Any]
    updated_at: datetime


class AutomationRuleCreateRequest(BaseModel):
    code: Optional[str] = None
    name: str = Field(..., min_length=3, max_length=160)
    cluster_id: str = Field(default="esp32_cluster2")
    description: str = Field(default="")
    is_enabled: bool = Field(default=True)
    config: Dict[str, Any] = Field(default_factory=dict)


class AutomationRuleUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_enabled: Optional[bool] = None
    config: Optional[Dict[str, Any]] = None


# =====================================================================
# 7. ALERTS & SETTINGS SCHEMAS
# =====================================================================
class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    alert_type: str
    severity: str
    cluster_id: str
    title: str
    message: str
    is_read: bool
    telegram_sent: bool
    image_url: Optional[str] = None
    created_at: datetime


class SettingsUpdateRequest(BaseModel):
    temp_threshold_c: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    humidity_threshold_pct: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    light_adc_threshold: Optional[int] = Field(default=None, ge=0, le=4095)
    pir_hold_seconds: Optional[int] = Field(default=None, ge=1, le=300)
    face_match_threshold: Optional[float] = Field(default=None, ge=0.1, le=0.99)
    door_open_seconds: Optional[int] = Field(default=None, ge=1, le=60)
    security_armed: Optional[bool] = None
    telegram_enabled: Optional[bool] = None
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None


class TelegramTestRequest(BaseModel):
    message: str = Field(
        default="🔔 [Smart Home IoT AI] Tin nhắn kiểm tra kết nối từ hệ thống Backend thành công!"
    )
    bot_token: Optional[str] = None
    chat_id: Optional[str] = None
