"""
Module giao tiếp MQTT chuẩn cho dự án Smart Home IoT.
- Do Thành viên 1 xây dựng sẵn, khớp 100% với firmware của 3 cụm:
  1. esp32_cluster1 (PIR chuyển động + Đèn + Còi)
  2. esp32_cluster2 (DHT22 Nhiệt độ/Độ ẩm + Ánh sáng LDR/BH1750 + Đèn + Quạt)
  3. esp32_cam_01 (Camera nhận diện chủ nhà + Động cơ Servo SG90 mở cửa)
- Thành viên 2 (Backend) chỉ cần import `SmartHomeMqttService` vào FastAPI
  và gắn thêm hàm lưu Database vào các callback hooks.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from typing import Any, Callable, Dict, Optional

import paho.mqtt.client as mqtt

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("mqtt_handler")


# =====================================================================
# DANH SÁCH MQTT TOPICS ĐÃ THỐNG NHẤT VỚI FIRMWARE
# =====================================================================
TOPIC_SECURITY_MOTION = "smarthome/security/motion"
TOPIC_SECURITY_RECOGNITION = "smarthome/security/recognition"

TOPIC_SENSOR_CLUSTER1 = "smarthome/sensor/cluster1"
TOPIC_COMMAND_CLUSTER1 = "smarthome/device/cluster1/command"
TOPIC_ACK_CLUSTER1 = "smarthome/device/cluster1/ack"
TOPIC_STATUS_CLUSTER1 = "smarthome/device/cluster1/status"
TOPIC_SYSTEM_CLUSTER1 = "smarthome/system/cluster1/status"

TOPIC_SENSOR_CLUSTER2 = "smarthome/sensor/cluster2"
TOPIC_COMMAND_CLUSTER2 = "smarthome/device/cluster2/command"
TOPIC_ACK_CLUSTER2 = "smarthome/device/cluster2/ack"
TOPIC_STATUS_CLUSTER2 = "smarthome/device/cluster2/status"
TOPIC_SYSTEM_CLUSTER2 = "smarthome/system/cluster2/status"

TOPIC_CAM_COMMAND = "smarthome/security/access/esp32_cam_01/command"
TOPIC_CAM_ACK = "smarthome/security/access/esp32_cam_01/ack"
TOPIC_STATUS_CAM = "smarthome/device/esp32_cam_01/status"
TOPIC_SYSTEM_CAM = "smarthome/system/esp32_cam_01/status"

SUBSCRIBE_TOPICS = [
    (TOPIC_SECURITY_MOTION, 1),
    (TOPIC_SECURITY_RECOGNITION, 1),
    (TOPIC_SENSOR_CLUSTER1, 1),
    (TOPIC_ACK_CLUSTER1, 1),
    (TOPIC_STATUS_CLUSTER1, 1),
    (TOPIC_SYSTEM_CLUSTER1, 1),
    (TOPIC_SENSOR_CLUSTER2, 1),
    (TOPIC_ACK_CLUSTER2, 1),
    (TOPIC_STATUS_CLUSTER2, 1),
    (TOPIC_SYSTEM_CLUSTER2, 1),
    (TOPIC_CAM_ACK, 1),
    (TOPIC_STATUS_CAM, 1),
    (TOPIC_SYSTEM_CAM, 1),
]


class SmartHomeMqttService:
    """
    Lớp quản lý kết nối MQTT, nhận dữ liệu từ 3 cụm ESP32 và gửi lệnh điều khiển.
    Thành viên 2 có thể truyền các callback (on_sensor_data, on_motion_event, ...)
    để lưu dữ liệu vào SQLite / SQLAlchemy.
    """

    def __init__(
        self,
        broker_host: str = os.getenv("MQTT_HOST", "127.0.0.1"),
        broker_port: int = int(os.getenv("MQTT_PORT", "1883")),
        username: str = os.getenv("MQTT_USERNAME", ""),
        password: str = os.getenv("MQTT_PASSWORD", ""),
        client_id: str = f"smarthome_backend_{uuid.uuid4().hex[:6]}",
    ) -> None:
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.username = username
        self.password = password
        self.client_id = client_id

        self._lock = threading.Lock()
        self.connected = False

        # Bộ nhớ lưu trạng thái mới nhất của toàn hệ thống (dùng cho Dashboard nhanh)
        self.latest_state: Dict[str, Any] = {
            "esp32_cluster1": {
                "online": False,
                "mode": "AUTO",
                "pir": False,
                "outputs": {"light": False, "buzzer": False},
                "last_motion_event": None,
                "last_ack": None,
                "updated_at": None,
            },
            "esp32_cluster2": {
                "online": False,
                "mode": "AUTO",
                "temperature_c": None,
                "humidity_pct": None,
                "light_adc": None,
                "light_lux": None,
                "is_dark": None,
                "outputs": {"light": False, "fan": False},
                "last_ack": None,
                "updated_at": None,
            },
            "esp32_cam_01": {
                "online": False,
                "camera_ready": False,
                "door_state": "LOCKED",
                "servo_angle_deg": 0,
                "last_identity": "NONE",
                "last_person_name": None,
                "last_recognition": None,
                "last_ack": None,
                "updated_at": None,
            },
        }

        # Callback hooks để Thành viên 2 gắn logic lưu Database / gửi Telegram
        self.on_motion_event: Optional[Callable[[Dict[str, Any]], None]] = None
        self.on_cluster1_sensor: Optional[Callable[[Dict[str, Any]], None]] = None
        self.on_cluster2_sensor: Optional[Callable[[Dict[str, Any]], None]] = None
        self.on_device_status: Optional[Callable[[str, Dict[str, Any]], None]] = None
        self.on_device_ack: Optional[Callable[[str, Dict[str, Any]], None]] = None
        self.on_recognition_event: Optional[Callable[[Dict[str, Any]], None]] = None

        # Khởi tạo Paho-MQTT Client (tương thích cả paho-mqtt v1.x và v2.x)
        if hasattr(mqtt, "CallbackAPIVersion"):
            self.client = mqtt.Client(
                mqtt.CallbackAPIVersion.VERSION1, client_id=self.client_id
            )
        else:
            self.client = mqtt.Client(client_id=self.client_id)

        if self.username:
            self.client.username_pw_set(self.username, self.password)

        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message

    # -----------------------------------------------------------------
    # VÒNG ĐỜI KẾT NỐI MQTT
    # -----------------------------------------------------------------
    def start(self) -> None:
        """Kết nối tới Mosquitto Broker và chạy luồng lắng nghe nền."""
        try:
            logger.info(
                "Đang kết nối tới MQTT Broker tại %s:%d...",
                self.broker_host,
                self.broker_port,
            )
            self.client.connect_async(self.broker_host, self.broker_port, keepalive=30)
            self.client.loop_start()
        except Exception as exc:
            logger.error("Không thể khởi động kết nối MQTT: %s", exc)

    def stop(self) -> None:
        """Dừng luồng MQTT và ngắt kết nối."""
        try:
            self.client.loop_stop()
            self.client.disconnect()
        except Exception as exc:
            logger.warning("Lỗi khi đóng kết nối MQTT: %s", exc)

    def _on_connect(self, client: mqtt.Client, userdata: Any, flags: Any, rc: int) -> None:
        if rc == 0:
            self.connected = True
            logger.info("Đã kết nối MQTT Broker thành công (rc=0). Đang subscribe topics...")
            client.subscribe(SUBSCRIBE_TOPICS)
        else:
            self.connected = False
            logger.error("Kết nối MQTT thất bại, mã lỗi rc=%d", rc)

    def _on_disconnect(self, client: mqtt.Client, userdata: Any, rc: int) -> None:
        self.connected = False
        logger.warning("Mất kết nối MQTT Broker (rc=%d). Paho sẽ tự động kết nối lại...", rc)

    # -----------------------------------------------------------------
    # XỬ LÝ BẢN TIN NHẬN ĐƯỢC TỪ 3 CỤM ESP32
    # -----------------------------------------------------------------
    def _on_message(self, client: mqtt.Client, userdata: Any, msg: mqtt.MQTTMessage) -> None:
        topic = msg.topic
        raw_payload = msg.payload.decode("utf-8", errors="replace")

        try:
            data = json.loads(raw_payload)
        except json.JSONDecodeError:
            logger.warning("Bản tin không phải JSON hợp lệ trên topic %s: %s", topic, raw_payload)
            return

        now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        logger.info("[MQTT RX] %s -> %s", topic, raw_payload)

        with self._lock:
            # 1. Sự kiện chuyển động từ Cụm 1
            if topic == TOPIC_SECURITY_MOTION:
                c1 = self.latest_state["esp32_cluster1"]
                c1["pir"] = bool(data.get("pir", True))
                c1["last_motion_event"] = data
                c1["updated_at"] = now_iso
                if self.on_motion_event:
                    self.on_motion_event(data)

            # 2. Bản tin cảm biến Cụm 1 (MOTION_DETECTED / MOTION_CLEARED)
            elif topic == TOPIC_SENSOR_CLUSTER1:
                c1 = self.latest_state["esp32_cluster1"]
                c1["pir"] = bool(data.get("pir", False))
                if isinstance(data.get("outputs"), dict):
                    c1["outputs"].update(data["outputs"])
                c1["updated_at"] = now_iso
                if self.on_cluster1_sensor:
                    self.on_cluster1_sensor(data)

            # 3. Trạng thái thiết bị Cụm 1
            elif topic == TOPIC_STATUS_CLUSTER1:
                c1 = self.latest_state["esp32_cluster1"]
                c1["online"] = bool(data.get("online", True))
                c1["mode"] = data.get("mode", c1["mode"])
                if "pir" in data:
                    c1["pir"] = bool(data["pir"])
                if isinstance(data.get("outputs"), dict):
                    c1["outputs"].update(data["outputs"])
                c1["updated_at"] = now_iso
                if self.on_device_status:
                    self.on_device_status("esp32_cluster1", data)

            # 4. ACK lệnh điều khiển Cụm 1
            elif topic == TOPIC_ACK_CLUSTER1:
                c1 = self.latest_state["esp32_cluster1"]
                c1["last_ack"] = data
                c1["mode"] = data.get("mode", c1["mode"])
                if isinstance(data.get("outputs"), dict):
                    c1["outputs"].update(data["outputs"])
                c1["updated_at"] = now_iso
                if self.on_device_ack:
                    self.on_device_ack("esp32_cluster1", data)

            # 5. Online/Offline Cụm 1
            elif topic == TOPIC_SYSTEM_CLUSTER1:
                self.latest_state["esp32_cluster1"]["online"] = bool(data.get("online", False))
                self.latest_state["esp32_cluster1"]["updated_at"] = now_iso

            # 6. Dữ liệu cảm biến Cụm 2 (Nhiệt độ, Độ ẩm, Ánh sáng LDR/BH1750, Trạng thái đèn/quạt)
            elif topic == TOPIC_SENSOR_CLUSTER2:
                c2 = self.latest_state["esp32_cluster2"]
                c2["online"] = True
                c2["mode"] = data.get("mode", c2["mode"])
                c2["temperature_c"] = data.get("temperature_c")
                c2["humidity_pct"] = data.get("humidity_pct")
                c2["light_adc"] = data.get("light_adc")
                c2["light_lux"] = data.get("light_lux")
                c2["is_dark"] = data.get("is_dark")
                if isinstance(data.get("outputs"), dict):
                    c2["outputs"].update(data["outputs"])
                c2["updated_at"] = now_iso
                if self.on_cluster2_sensor:
                    self.on_cluster2_sensor(data)

            # 7. Trạng thái thiết bị Cụm 2
            elif topic == TOPIC_STATUS_CLUSTER2:
                c2 = self.latest_state["esp32_cluster2"]
                c2["online"] = bool(data.get("online", True))
                c2["mode"] = data.get("mode", c2["mode"])
                if isinstance(data.get("outputs"), dict):
                    c2["outputs"].update(data["outputs"])
                c2["updated_at"] = now_iso
                if self.on_device_status:
                    self.on_device_status("esp32_cluster2", data)

            # 8. ACK lệnh điều khiển Cụm 2
            elif topic == TOPIC_ACK_CLUSTER2:
                c2 = self.latest_state["esp32_cluster2"]
                c2["last_ack"] = data
                c2["mode"] = data.get("mode", c2["mode"])
                if isinstance(data.get("outputs"), dict):
                    c2["outputs"].update(data["outputs"])
                c2["updated_at"] = now_iso
                if self.on_device_ack:
                    self.on_device_ack("esp32_cluster2", data)

            # 9. Online/Offline Cụm 2
            elif topic == TOPIC_SYSTEM_CLUSTER2:
                self.latest_state["esp32_cluster2"]["online"] = bool(data.get("online", False))
                self.latest_state["esp32_cluster2"]["updated_at"] = now_iso

            # 10. Sự kiện kết quả nhận diện từ ESP32-CAM
            elif topic == TOPIC_SECURITY_RECOGNITION:
                cam = self.latest_state["esp32_cam_01"]
                cam["last_recognition"] = data
                cam["last_identity"] = data.get("identity", cam["last_identity"])
                cam["last_person_name"] = data.get("person_name", cam["last_person_name"])
                cam["door_state"] = data.get("door_state", cam["door_state"])
                cam["updated_at"] = now_iso
                if self.on_recognition_event:
                    self.on_recognition_event(data)

            # 11. Trạng thái ESP32-CAM & Cửa Servo SG90
            elif topic == TOPIC_STATUS_CAM:
                cam = self.latest_state["esp32_cam_01"]
                cam["online"] = bool(data.get("online", True))
                cam["camera_ready"] = bool(data.get("camera_ready", True))
                cam["door_state"] = data.get("door_state", cam["door_state"])
                cam["servo_angle_deg"] = data.get("servo_angle_deg", cam["servo_angle_deg"])
                cam["last_identity"] = data.get("last_identity", cam["last_identity"])
                cam["last_person_name"] = data.get("last_person_name", cam["last_person_name"])
                cam["updated_at"] = now_iso
                if self.on_device_status:
                    self.on_device_status("esp32_cam_01", data)

            # 12. ACK mở/khóa cửa từ ESP32-CAM
            elif topic == TOPIC_CAM_ACK:
                cam = self.latest_state["esp32_cam_01"]
                cam["last_ack"] = data
                cam["door_state"] = data.get("door_state", cam["door_state"])
                cam["servo_angle_deg"] = data.get("servo_angle_deg", cam["servo_angle_deg"])
                cam["updated_at"] = now_iso
                if self.on_device_ack:
                    self.on_device_ack("esp32_cam_01", data)

            # 13. Online/Offline ESP32-CAM
            elif topic == TOPIC_SYSTEM_CAM:
                self.latest_state["esp32_cam_01"]["online"] = bool(data.get("online", False))
                self.latest_state["esp32_cam_01"]["updated_at"] = now_iso

    # -----------------------------------------------------------------
    # CÁC HÀM GỬI LỆNH ĐIỀU KHIỂN TỪ BACKEND XUỐNG 3 CỤM ESP32
    # -----------------------------------------------------------------
    def publish_json(self, topic: str, payload: Dict[str, Any], qos: int = 1, retain: bool = False) -> bool:
        """Hàm tiện ích đóng gói JSON và publish qua MQTT."""
        raw = json.dumps(payload, ensure_ascii=False)
        info = self.client.publish(topic, raw, qos=qos, retain=retain)
        logger.info("[MQTT TX] %s -> %s (rc=%s)", topic, raw, info.rc)
        return info.rc == mqtt.MQTT_ERR_SUCCESS

    def control_cluster1(
        self,
        mode: str = "MANUAL",
        light: Optional[bool] = None,
        buzzer: Optional[bool] = None,
        command_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Gửi lệnh điều khiển Cụm 1 (Đèn + Còi + Chế độ AUTO/MANUAL).
        """
        cmd_id = command_id or f"cmd_c1_{uuid.uuid4().hex[:8]}"
        payload: Dict[str, Any] = {
            "schema_version": 1,
            "command_id": cmd_id,
            "device_id": "esp32_cluster1",
            "mode": mode,
        }
        outputs: Dict[str, bool] = {}
        if light is not None:
            outputs["light"] = bool(light)
        if buzzer is not None:
            outputs["buzzer"] = bool(buzzer)
        if outputs:
            payload["outputs"] = outputs

        self.publish_json(TOPIC_COMMAND_CLUSTER1, payload, qos=1, retain=False)
        return payload

    def control_cluster2(
        self,
        mode: str = "MANUAL",
        light: Optional[bool] = None,
        fan: Optional[bool] = None,
        command_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Gửi lệnh điều khiển Cụm 2 (Đèn + Quạt + Chế độ AUTO/MANUAL).
        """
        cmd_id = command_id or f"cmd_c2_{uuid.uuid4().hex[:8]}"
        payload: Dict[str, Any] = {
            "schema_version": 1,
            "command_id": cmd_id,
            "device_id": "esp32_cluster2",
            "mode": mode,
        }
        outputs: Dict[str, bool] = {}
        if light is not None:
            outputs["light"] = bool(light)
        if fan is not None:
            outputs["fan"] = bool(fan)
        if outputs:
            payload["outputs"] = outputs

        self.publish_json(TOPIC_COMMAND_CLUSTER2, payload, qos=1, retain=False)
        return payload

    def send_door_access_decision(
        self,
        identity: str,
        authorized: bool,
        person_name: str = "unknown",
        confidence: float = 0.0,
        event_id: Optional[str] = None,
        command_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Gửi quyết định nhận diện khuôn mặt xuống ESP32-CAM để điều khiển Servo SG90:
        - Nếu khớp mặt chủ nhà (`identity == "KNOWN"` và `authorized == True`):
          Gửi `action = "OPEN"` -> ESP32-CAM quay Servo SG90 lên 90° mở cửa trong 5s.
        - Nếu không khớp (`UNKNOWN` hoặc `NO_FACE` hoặc `authorized == False`):
          Gửi `action = "KEEP_LOCKED"` -> ESP32-CAM giữ nguyên Servo SG90 ở 0° (không quay).
        """
        cmd_id = command_id or f"access_{uuid.uuid4().hex[:8]}"
        evt_id = event_id or f"evt_{uuid.uuid4().hex[:8]}"
        is_owner = (identity == "KNOWN") and bool(authorized)
        action = "OPEN" if is_owner else "KEEP_LOCKED"

        payload: Dict[str, Any] = {
            "schema_version": 1,
            "command_id": cmd_id,
            "event_id": evt_id,
            "device_id": "esp32_cam_01",
            "identity": identity,
            "person_name": person_name if is_owner else "unknown",
            "confidence": round(float(confidence), 3),
            "authorized": is_owner,
            "action": action,
        }
        self.publish_json(TOPIC_CAM_COMMAND, payload, qos=1, retain=False)
        return payload

    def request_camera_capture(self, event_id: Optional[str] = None) -> Dict[str, Any]:
        """Yêu cầu ESP32-CAM chụp ảnh và gửi về Backend ngay lập tức."""
        cmd_id = f"capture_cmd_{uuid.uuid4().hex[:8]}"
        evt_id = event_id or f"manual_capture_{uuid.uuid4().hex[:8]}"
        payload = {
            "schema_version": 1,
            "command_id": cmd_id,
            "event_id": evt_id,
            "device_id": "esp32_cam_01",
            "action": "CAPTURE",
        }
        self.publish_json(TOPIC_CAM_COMMAND, payload, qos=1, retain=False)
        return payload

    def get_snapshot(self) -> Dict[str, Any]:
        """Lấy bản sao trạng thái mới nhất của cả 3 cụm ESP32."""
        with self._lock:
            return json.loads(json.dumps(self.latest_state))
