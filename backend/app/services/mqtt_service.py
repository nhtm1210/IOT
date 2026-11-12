"""
Dịch vụ MQTT Trung tâm (`SmartHomeMqttService`) kết nối:
- 3 cụm phần cứng ESP32 (`esp32_cluster1`, `esp32_cluster2`, `esp32_cam_01`)
- Cơ sở dữ liệu SQLite / SQLAlchemy (`SensorHistory`, `Device`, `DeviceHistory`, `RecognitionHistory`, `Alert`)
- Bộ máy Tự động hóa (`AutomationEngine`) & Cảnh báo Telegram (`TelegramBotService`)
- Kênh truyền thời gian thực WebSocket (`ws_manager`) cho Web Dashboard.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import paho.mqtt.client as mqtt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import db_session
from app.models.models import (
    Device,
    DeviceHistory,
    RecognitionHistory,
    SensorHistory,
)
from app.services.automation import automation_engine
from app.websocket.manager import ws_manager

logger = logging.getLogger("mqtt_service")

# =====================================================================
# DANH SÁCH 16 MQTT TOPICS CHUẨN THEO MQTT_SPEC.md
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
    def __init__(
        self,
        broker_host: str = settings.MQTT_HOST,
        broker_port: int = settings.MQTT_PORT,
        username: str = settings.MQTT_USERNAME,
        password: str = settings.MQTT_PASSWORD,
        client_id: str = f"smarthome_backend_{uuid.uuid4().hex[:6]}",
    ) -> None:
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.username = username
        self.password = password
        self.client_id = client_id

        self._lock = threading.Lock()
        self.connected = False
        self.event_logs: List[Dict[str, Any]] = []
        self._recent_commands: Dict[str, float] = {}

        # Bộ nhớ lưu trạng thái thời gian thực của 3 cụm ESP32 (khớp 100% với WEB_DASHBOARD_SPEC.md)
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
                "last_confidence": 0.0,
                "last_image_url": None,
                "last_recognition": None,
                "last_ack": None,
                "updated_at": None,
            },
        }

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

    def append_log(self, event_type: str, topic: str, data: Any) -> None:
        entry = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "type": event_type,
            "topic": topic,
            "data": data,
        }
        with self._lock:
            self.event_logs.append(entry)
            if len(self.event_logs) > 250:
                del self.event_logs[0 : len(self.event_logs) - 250]

    def get_recent_logs(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            return list(reversed(self.event_logs[-limit:]))

    def get_snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return json.loads(json.dumps(self.latest_state))

    # -----------------------------------------------------------------
    # VÒNG ĐỜI KẾT NỐI MQTT
    # -----------------------------------------------------------------
    def start(self) -> None:
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
        try:
            self.client.loop_stop()
            self.client.disconnect()
        except Exception as exc:
            logger.warning("Lỗi khi đóng kết nối MQTT: %s", exc)

    def _on_connect(self, client: mqtt.Client, userdata: Any, flags: Any, rc: int) -> None:
        if rc == 0:
            self.connected = True
            logger.info("Đã kết nối MQTT Broker thành công (rc=0). Đang subscribe 13 topics...")
            client.subscribe(SUBSCRIBE_TOPICS)
            ws_manager.broadcast_threadsafe("MQTT_STATUS", {"connected": True})
        else:
            self.connected = False
            logger.error("Kết nối MQTT thất bại, mã lỗi rc=%d", rc)

    def _on_disconnect(self, client: mqtt.Client, userdata: Any, rc: int) -> None:
        self.connected = False
        logger.warning("Mất kết nối MQTT Broker (rc=%d). Đang tự động kết nối lại...", rc)
        ws_manager.broadcast_threadsafe("MQTT_STATUS", {"connected": False})

    # -----------------------------------------------------------------
    # ĐỒNG BỘ TRẠNG THÁI VÀO DATABASE SQLITE
    # -----------------------------------------------------------------
    @staticmethod
    def _sync_device_row(
        db: Session,
        device_id: str,
        state: Optional[str] = None,
        mode: Optional[str] = None,
        online: Optional[bool] = None,
    ) -> None:
        dev = db.query(Device).filter(Device.id == device_id).first()
        if not dev:
            return
        if state is not None:
            dev.state = state
        if mode is not None:
            dev.mode = mode
        if online is not None:
            dev.online = online
        dev.updated_at = datetime.now(timezone.utc)

    @staticmethod
    def _record_device_ack(
        db: Session, cluster_id: str, data: Dict[str, Any]
    ) -> None:
        cmd_id = str(data.get("command_id", ""))
        success = bool(data.get("success", True))
        error = data.get("error")

        if cmd_id:
            existing = (
                db.query(DeviceHistory)
                .filter(DeviceHistory.command_id == cmd_id)
                .order_by(DeviceHistory.id.desc())
                .first()
            )
            if existing:
                existing.ack_received = True
                existing.success = success
                existing.error = error
                return

        outputs = data.get("outputs") or {}
        door_state = data.get("door_state")
        state_str = door_state if door_state else json.dumps(outputs)
        db.add(
            DeviceHistory(
                command_id=cmd_id or f"ack_{uuid.uuid4().hex[:8]}",
                cluster_id=cluster_id,
                device_id=str(data.get("device_id", cluster_id)),
                action="ACK",
                state=state_str,
                mode=str(data.get("mode", "AUTO")),
                triggered_by="DEVICE_ACK",
                ack_received=True,
                success=success,
                error=error,
                payload_json=json.dumps(data, ensure_ascii=False),
            )
        )

    # -----------------------------------------------------------------
    # XỬ LÝ BẢN TIN MQTT TỪ 3 CỤM ESP32
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
        self.append_log("MQTT_RX", topic, data)

        with self._lock:
            # 1. Sự kiện chuyển động PIR từ Cụm 1
            if topic == TOPIC_SECURITY_MOTION:
                c1 = self.latest_state["esp32_cluster1"]
                c1["online"] = True
                c1["pir"] = bool(data.get("pir", True))
                if isinstance(data.get("outputs"), dict):
                    c1["outputs"].update(data["outputs"])
                c1["last_motion_event"] = data
                c1["updated_at"] = now_iso

            # 2. Bản tin cảm biến Cụm 1 (MOTION_DETECTED / MOTION_CLEARED)
            elif topic == TOPIC_SENSOR_CLUSTER1:
                c1 = self.latest_state["esp32_cluster1"]
                c1["online"] = True
                c1["pir"] = bool(data.get("pir", False))
                if isinstance(data.get("outputs"), dict):
                    c1["outputs"].update(data["outputs"])
                c1["updated_at"] = now_iso

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

            # 4. ACK lệnh điều khiển Cụm 1
            elif topic == TOPIC_ACK_CLUSTER1:
                c1 = self.latest_state["esp32_cluster1"]
                c1["online"] = True
                c1["last_ack"] = data
                c1["mode"] = data.get("mode", c1["mode"])
                if isinstance(data.get("outputs"), dict):
                    c1["outputs"].update(data["outputs"])
                c1["updated_at"] = now_iso

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

            # 7. Trạng thái thiết bị Cụm 2
            elif topic == TOPIC_STATUS_CLUSTER2:
                c2 = self.latest_state["esp32_cluster2"]
                c2["online"] = bool(data.get("online", True))
                c2["mode"] = data.get("mode", c2["mode"])
                if isinstance(data.get("outputs"), dict):
                    c2["outputs"].update(data["outputs"])
                c2["updated_at"] = now_iso

            # 8. ACK lệnh điều khiển Cụm 2
            elif topic == TOPIC_ACK_CLUSTER2:
                c2 = self.latest_state["esp32_cluster2"]
                c2["online"] = True
                c2["last_ack"] = data
                c2["mode"] = data.get("mode", c2["mode"])
                if isinstance(data.get("outputs"), dict):
                    c2["outputs"].update(data["outputs"])
                c2["updated_at"] = now_iso

            # 9. Online/Offline Cụm 2
            elif topic == TOPIC_SYSTEM_CLUSTER2:
                self.latest_state["esp32_cluster2"]["online"] = bool(data.get("online", False))
                self.latest_state["esp32_cluster2"]["updated_at"] = now_iso

            # 10. Sự kiện kết quả nhận diện từ ESP32-CAM
            elif topic == TOPIC_SECURITY_RECOGNITION:
                cam = self.latest_state["esp32_cam_01"]
                cam["online"] = True
                cam["last_recognition"] = data
                cam["last_identity"] = data.get("identity", cam["last_identity"])
                cam["last_person_name"] = data.get("person_name", cam["last_person_name"])
                if "confidence" in data:
                    cam["last_confidence"] = float(data.get("confidence") or 0.0)
                cam["door_state"] = data.get("door_state", cam["door_state"])
                cam["servo_angle_deg"] = 90 if cam["door_state"] == "OPEN" else 0
                cam["updated_at"] = now_iso

            # 11. Trạng thái ESP32-CAM & Cửa Servo SG90
            elif topic == TOPIC_STATUS_CAM:
                cam = self.latest_state["esp32_cam_01"]
                cam["online"] = bool(data.get("online", True))
                cam["camera_ready"] = bool(data.get("camera_ready", True))
                cam["door_state"] = data.get("door_state", cam["door_state"])
                cam["servo_angle_deg"] = int(data.get("servo_angle_deg", cam["servo_angle_deg"]))
                cam["last_identity"] = data.get("last_identity", cam["last_identity"])
                cam["last_person_name"] = data.get("last_person_name", cam["last_person_name"])
                cam["updated_at"] = now_iso

            # 12. ACK mở/khóa cửa từ ESP32-CAM
            elif topic == TOPIC_CAM_ACK:
                cam = self.latest_state["esp32_cam_01"]
                cam["online"] = True
                cam["last_ack"] = data
                cam["door_state"] = data.get("door_state", cam["door_state"])
                cam["servo_angle_deg"] = int(data.get("servo_angle_deg", cam["servo_angle_deg"]))
                cam["updated_at"] = now_iso

            # 13. Online/Offline ESP32-CAM
            elif topic == TOPIC_SYSTEM_CAM:
                self.latest_state["esp32_cam_01"]["online"] = bool(data.get("online", False))
                self.latest_state["esp32_cam_01"]["updated_at"] = now_iso

        # Lưu vào Database & kích hoạt Automation Engine
        try:
            self._persist_mqtt_message(topic, data)
        except Exception as exc:
            logger.error("Lỗi khi lưu bản tin MQTT (%s) vào DB: %s", topic, exc)

        # Phát sóng trạng thái mới qua WebSocket cho tất cả trình duyệt đang mở Dashboard
        ws_manager.broadcast_threadsafe(
            "MQTT_MESSAGE",
            {
                "topic": topic,
                "payload": data,
                "nodes": self.get_snapshot(),
            },
        )

    def _persist_mqtt_message(self, topic: str, data: Dict[str, Any]) -> None:
        with db_session() as db:
            if topic == TOPIC_SECURITY_MOTION:
                automation_engine.evaluate_motion_event(db, data)

            elif topic == TOPIC_SENSOR_CLUSTER1:
                outputs = data.get("outputs") or {}
                light_on = bool(outputs.get("light", False))
                buzzer_on = bool(outputs.get("buzzer", False))
                pir_val = bool(data.get("pir", False))

                db.add(
                    SensorHistory(
                        cluster_id="esp32_cluster1",
                        pir=pir_val,
                        light_state=light_on,
                        buzzer_state=buzzer_on,
                    )
                )
                self._sync_device_row(
                    db, "light_1", state="ON" if light_on else "OFF", online=True
                )
                self._sync_device_row(
                    db, "buzzer_1", state="ON" if buzzer_on else "OFF", online=True
                )

            elif topic == TOPIC_STATUS_CLUSTER1:
                outputs = data.get("outputs") or {}
                mode = data.get("mode", "AUTO")
                online = bool(data.get("online", True))
                self._sync_device_row(
                    db,
                    "light_1",
                    state="ON" if outputs.get("light") else "OFF",
                    mode=mode,
                    online=online,
                )
                self._sync_device_row(
                    db,
                    "buzzer_1",
                    state="ON" if outputs.get("buzzer") else "OFF",
                    mode=mode,
                    online=online,
                )

            elif topic == TOPIC_ACK_CLUSTER1:
                outputs = data.get("outputs") or {}
                mode = data.get("mode", "MANUAL")
                self._sync_device_row(
                    db,
                    "light_1",
                    state="ON" if outputs.get("light") else "OFF",
                    mode=mode,
                    online=True,
                )
                self._sync_device_row(
                    db,
                    "buzzer_1",
                    state="ON" if outputs.get("buzzer") else "OFF",
                    mode=mode,
                    online=True,
                )
                self._record_device_ack(db, "esp32_cluster1", data)

            elif topic == TOPIC_SYSTEM_CLUSTER1:
                online = bool(data.get("online", False))
                self._sync_device_row(db, "light_1", online=online)
                self._sync_device_row(db, "buzzer_1", online=online)

            elif topic == TOPIC_SENSOR_CLUSTER2:
                outputs = data.get("outputs") or {}
                light_on = bool(outputs.get("light", False))
                fan_on = bool(outputs.get("fan", False))
                mode = data.get("mode", "AUTO")

                db.add(
                    SensorHistory(
                        cluster_id="esp32_cluster2",
                        temperature_c=data.get("temperature_c"),
                        humidity_pct=data.get("humidity_pct"),
                        light_adc=data.get("light_adc"),
                        light_lux=data.get("light_lux"),
                        is_dark=data.get("is_dark"),
                        light_state=light_on,
                        fan_state=fan_on,
                    )
                )
                self._sync_device_row(
                    db, "light_2", state="ON" if light_on else "OFF", mode=mode, online=True
                )
                self._sync_device_row(
                    db, "fan_1", state="ON" if fan_on else "OFF", mode=mode, online=True
                )
                automation_engine.evaluate_cluster2_sensor(db, data)

            elif topic == TOPIC_STATUS_CLUSTER2:
                outputs = data.get("outputs") or {}
                mode = data.get("mode", "AUTO")
                online = bool(data.get("online", True))
                self._sync_device_row(
                    db,
                    "light_2",
                    state="ON" if outputs.get("light") else "OFF",
                    mode=mode,
                    online=online,
                )
                self._sync_device_row(
                    db,
                    "fan_1",
                    state="ON" if outputs.get("fan") else "OFF",
                    mode=mode,
                    online=online,
                )

            elif topic == TOPIC_ACK_CLUSTER2:
                outputs = data.get("outputs") or {}
                mode = data.get("mode", "MANUAL")
                self._sync_device_row(
                    db,
                    "light_2",
                    state="ON" if outputs.get("light") else "OFF",
                    mode=mode,
                    online=True,
                )
                self._sync_device_row(
                    db,
                    "fan_1",
                    state="ON" if outputs.get("fan") else "OFF",
                    mode=mode,
                    online=True,
                )
                self._record_device_ack(db, "esp32_cluster2", data)

            elif topic == TOPIC_SYSTEM_CLUSTER2:
                online = bool(data.get("online", False))
                self._sync_device_row(db, "light_2", online=online)
                self._sync_device_row(db, "fan_1", online=online)

            elif topic == TOPIC_SECURITY_RECOGNITION:
                evt_id = str(data.get("event_id", f"evt_{uuid.uuid4().hex[:8]}"))
                existing = (
                    db.query(RecognitionHistory)
                    .filter(RecognitionHistory.event_id == evt_id)
                    .first()
                )
                door_state = str(data.get("door_state", "LOCKED"))
                if existing:
                    existing.door_state = door_state
                    existing.servo_angle_deg = 90 if door_state == "OPEN" else 0
                else:
                    db.add(
                        RecognitionHistory(
                            event_id=evt_id,
                            device_id=str(data.get("device_id", "esp32_cam_01")),
                            identity=str(data.get("identity", "UNKNOWN")),
                            person_name=str(data.get("person_name", "unknown")),
                            confidence=float(data.get("confidence", 0.0)),
                            authorized=bool(data.get("authorized", False)),
                            door_action=str(data.get("door_action", "KEEP_LOCKED")),
                            door_state=door_state,
                            servo_angle_deg=90 if door_state == "OPEN" else 0,
                        )
                    )
                self._sync_device_row(db, "door_servo_1", state=door_state, online=True)

            elif topic == TOPIC_STATUS_CAM:
                door_state = str(data.get("door_state", "LOCKED"))
                online = bool(data.get("online", True))
                self._sync_device_row(db, "door_servo_1", state=door_state, online=online)

            elif topic == TOPIC_CAM_ACK:
                door_state = str(data.get("door_state", "LOCKED"))
                self._sync_device_row(db, "door_servo_1", state=door_state, online=True)
                self._record_device_ack(db, "esp32_cam_01", data)

            elif topic == TOPIC_SYSTEM_CAM:
                online = bool(data.get("online", False))
                self._sync_device_row(db, "door_servo_1", online=online)

    # -----------------------------------------------------------------
    # CÁC HÀM GỬI LỆNH ĐIỀU KHIỂN TỪ BACKEND XUỐNG 3 CỤM ESP32
    # -----------------------------------------------------------------
    def publish_json(
        self, topic: str, payload: Dict[str, Any], qos: int = 1, retain: bool = False
    ) -> bool:
        raw = json.dumps(payload, ensure_ascii=False)
        info = self.client.publish(topic, raw, qos=qos, retain=retain)
        self.append_log("MQTT_TX", topic, payload)
        logger.info("[MQTT TX] %s -> %s (rc=%s)", topic, raw, info.rc)
        return info.rc == mqtt.MQTT_ERR_SUCCESS

    def control_cluster1(
        self,
        mode: str = "MANUAL",
        light: Optional[bool] = None,
        buzzer: Optional[bool] = None,
        command_id: Optional[str] = None,
        triggered_by: str = "WEB_USER",
    ) -> Dict[str, Any]:
        """Gửi lệnh điều khiển Cụm ESP 1 (Đèn GPIO26 + Còi GPIO25 + Chế độ AUTO/MANUAL)."""
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

        # Cập nhật lạc quan (optimistic state) và lưu lịch sử lệnh
        with self._lock:
            c1 = self.latest_state["esp32_cluster1"]
            c1["mode"] = mode
            if outputs:
                c1["outputs"].update(outputs)

        with db_session() as db:
            db.add(
                DeviceHistory(
                    command_id=cmd_id,
                    cluster_id="esp32_cluster1",
                    device_id="esp32_cluster1",
                    action="CONTROL_CLUSTER1",
                    state=json.dumps(outputs) if outputs else mode,
                    mode=mode,
                    triggered_by=triggered_by,
                    ack_received=False,
                    success=True,
                    payload_json=json.dumps(payload, ensure_ascii=False),
                )
            )
            if light is not None:
                self._sync_device_row(db, "light_1", state="ON" if light else "OFF", mode=mode)
            else:
                self._sync_device_row(db, "light_1", mode=mode)
            if buzzer is not None:
                self._sync_device_row(db, "buzzer_1", state="ON" if buzzer else "OFF", mode=mode)
            else:
                self._sync_device_row(db, "buzzer_1", mode=mode)

        return payload

    def control_cluster2(
        self,
        mode: str = "MANUAL",
        light: Optional[bool] = None,
        fan: Optional[bool] = None,
        command_id: Optional[str] = None,
        triggered_by: str = "WEB_USER",
    ) -> Dict[str, Any]:
        """Gửi lệnh điều khiển Cụm ESP 2 (Đèn GPIO2 + Quạt GPIO5 + Chế độ AUTO/MANUAL)."""
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

        with self._lock:
            c2 = self.latest_state["esp32_cluster2"]
            c2["mode"] = mode
            if outputs:
                c2["outputs"].update(outputs)

        with db_session() as db:
            db.add(
                DeviceHistory(
                    command_id=cmd_id,
                    cluster_id="esp32_cluster2",
                    device_id="esp32_cluster2",
                    action="CONTROL_CLUSTER2",
                    state=json.dumps(outputs) if outputs else mode,
                    mode=mode,
                    triggered_by=triggered_by,
                    ack_received=False,
                    success=True,
                    payload_json=json.dumps(payload, ensure_ascii=False),
                )
            )
            if light is not None:
                self._sync_device_row(db, "light_2", state="ON" if light else "OFF", mode=mode)
            else:
                self._sync_device_row(db, "light_2", mode=mode)
            if fan is not None:
                self._sync_device_row(db, "fan_1", state="ON" if fan else "OFF", mode=mode)
            else:
                self._sync_device_row(db, "fan_1", mode=mode)

        return payload

    def send_door_access_decision(
        self,
        identity: str,
        authorized: bool,
        person_name: str = "unknown",
        confidence: float = 0.0,
        event_id: Optional[str] = None,
        command_id: Optional[str] = None,
        image_url: Optional[str] = None,
        action_override: Optional[str] = None,
        triggered_by: str = "FACE_AI",
    ) -> Dict[str, Any]:
        """
        Gửi quyết định nhận diện khuôn mặt xuống ESP32-CAM để điều khiển Servo SG90 (GPIO13):
        - Nếu khớp mặt chủ nhà (`identity == "KNOWN"` và `authorized == True`):
          Gửi `action = "OPEN"` -> ESP32-CAM quay Servo SG90 góc 90° mở cửa trong 5s rồi đóng về 0°.
        - Nếu không khớp (`UNKNOWN` hoặc `NO_FACE` hoặc `authorized == False`):
          Gửi `action = "KEEP_LOCKED"` -> ESP32-CAM giữ nguyên Servo SG90 ở góc 0° (khóa cửa).
        """
        cmd_id = command_id or f"access_{uuid.uuid4().hex[:8]}"
        evt_id = event_id or f"evt_{uuid.uuid4().hex[:8]}"
        is_owner = (identity == "KNOWN") and bool(authorized)
        action = action_override or ("OPEN" if is_owner else "KEEP_LOCKED")
        door_state = "OPEN" if action == "OPEN" else "LOCKED"
        servo_deg = 90 if action == "OPEN" else 0

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
        if image_url:
            payload["image_url"] = image_url

        self.publish_json(TOPIC_CAM_COMMAND, payload, qos=1, retain=False)

        with self._lock:
            cam = self.latest_state["esp32_cam_01"]
            cam["last_identity"] = identity
            cam["last_person_name"] = payload["person_name"]
            cam["last_confidence"] = payload["confidence"]
            cam["door_state"] = door_state
            cam["servo_angle_deg"] = servo_deg
            if image_url:
                cam["last_image_url"] = image_url

        with db_session() as db:
            existing_rec = (
                db.query(RecognitionHistory)
                .filter(RecognitionHistory.event_id == evt_id)
                .first()
            )
            if existing_rec:
                existing_rec.command_id = cmd_id
                existing_rec.identity = identity
                existing_rec.person_name = payload["person_name"]
                existing_rec.confidence = payload["confidence"]
                existing_rec.authorized = is_owner
                existing_rec.door_action = action
                existing_rec.door_state = door_state
                existing_rec.servo_angle_deg = servo_deg
                if image_url:
                    existing_rec.image_url = image_url
            else:
                db.add(
                    RecognitionHistory(
                        event_id=evt_id,
                        command_id=cmd_id,
                        device_id="esp32_cam_01",
                        identity=identity,
                        person_name=payload["person_name"],
                        confidence=payload["confidence"],
                        authorized=is_owner,
                        door_action=action,
                        door_state=door_state,
                        servo_angle_deg=servo_deg,
                        image_url=image_url,
                    )
                )

            db.add(
                DeviceHistory(
                    command_id=cmd_id,
                    cluster_id="esp32_cam_01",
                    device_id="door_servo_1",
                    action="DOOR_ACCESS",
                    state=door_state,
                    mode="AUTO" if triggered_by == "FACE_AI" else "MANUAL",
                    triggered_by=triggered_by,
                    ack_received=False,
                    success=True,
                    payload_json=json.dumps(payload, ensure_ascii=False),
                )
            )
            self._sync_device_row(db, "door_servo_1", state=door_state)

            automation_engine.evaluate_face_recognition(
                db=db,
                identity=identity,
                person_name=payload["person_name"],
                confidence=payload["confidence"],
                authorized=is_owner,
                image_url=image_url,
            )

        ws_manager.broadcast_threadsafe(
            "FACE_RECOGNITION",
            {
                "decision": payload,
                "nodes": self.get_snapshot(),
            },
        )
        return payload

    def request_camera_capture(self, event_id: Optional[str] = None) -> Dict[str, Any]:
        """Yêu cầu ESP32-CAM chụp ảnh và gửi về Backend ngay lập tức qua MQTT."""
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


mqtt_service = SmartHomeMqttService()
