"""
Script giả lập đồng thời cả 3 cụm ESP32 (Cluster 1, Cluster 2, ESP32-CAM) qua MQTT.
Giúp Thành viên 1 và Thành viên 2 kiểm thử toàn bộ giao tiếp MQTT + Backend
ngay trên máy tính kể cả khi chưa cắm mạch thật.

Chạy lệnh:
    python simulator_esp32.py
"""

from __future__ import annotations

import json
import os
import random
import time
import paho.mqtt.client as mqtt

BROKER_HOST = os.getenv("MQTT_HOST", "127.0.0.1")
BROKER_PORT = int(os.getenv("MQTT_PORT", "1883"))

# Trạng thái giả lập của 3 cụm đúng theo kịch bản phần cứng
cluster1_state = {
    "mode": "AUTO",
    "pir": False,
    "light": False,
    "buzzer": False,
    "seq": 0,
}

cluster2_state = {
    "mode": "AUTO",
    "temperature_c": 31.2,
    "humidity_pct": 36.5,
    "light_adc": 1400,
    "light_lux": 18.0,
    "is_dark": True,
    "light": True,
    "fan": True,
    "seq": 0,
}

cam_state = {
    "door_state": "LOCKED",
    "servo_angle_deg": 0,
    "last_identity": "NONE",
    "last_person_name": None,
    "door_opened_at": 0.0,
}


def publish_json(client: mqtt.Client, topic: str, data: dict, retain: bool = False) -> None:
    payload = json.dumps(data, ensure_ascii=False)
    client.publish(topic, payload, qos=1, retain=retain)
    print(f"[SIM TX] {topic} -> {payload}")


def publish_cluster1_status(client: mqtt.Client) -> None:
    publish_json(
        client,
        "smarthome/device/cluster1/status",
        {
            "schema_version": 1,
            "device_id": "esp32_cluster1",
            "online": True,
            "mode": cluster1_state["mode"],
            "pir": cluster1_state["pir"],
            "outputs": {
                "light": cluster1_state["light"],
                "buzzer": cluster1_state["buzzer"],
            },
            "firmware_version": "1.1.0-sim",
        },
        retain=True,
    )


def publish_cluster2_status(client: mqtt.Client) -> None:
    publish_json(
        client,
        "smarthome/device/cluster2/status",
        {
            "schema_version": 1,
            "device_id": "esp32_cluster2",
            "online": True,
            "mode": cluster2_state["mode"],
            "outputs": {
                "light": cluster2_state["light"],
                "buzzer": False,
                "fan": cluster2_state["fan"],
            },
            "firmware_version": "1.1.0-sim",
        },
        retain=True,
    )


def publish_cam_status(client: mqtt.Client) -> None:
    publish_json(
        client,
        "smarthome/device/esp32_cam_01/status",
        {
            "schema_version": 1,
            "device_id": "esp32_cam_01",
            "online": True,
            "camera_ready": True,
            "door_state": cam_state["door_state"],
            "servo_angle_deg": cam_state["servo_angle_deg"],
            "last_identity": cam_state["last_identity"],
            "last_person_name": cam_state["last_person_name"],
            "firmware_version": "1.1.0-sim",
        },
        retain=True,
    )


def on_connect(client: mqtt.Client, userdata, flags, rc: int) -> None:
    print(f"[SIM] Đã kết nối tới Broker {BROKER_HOST}:{BROKER_PORT} (rc={rc})")
    client.subscribe("smarthome/device/cluster1/command", qos=1)
    client.subscribe("smarthome/device/cluster2/command", qos=1)
    client.subscribe("smarthome/security/access/esp32_cam_01/command", qos=1)

    # Publish online status cho 3 cụm
    for dev_id, sys_topic in [
        ("esp32_cluster1", "smarthome/system/cluster1/status"),
        ("esp32_cluster2", "smarthome/system/cluster2/status"),
        ("esp32_cam_01", "smarthome/system/esp32_cam_01/status"),
    ]:
        publish_json(
            client,
            sys_topic,
            {
                "schema_version": 1,
                "device_id": dev_id,
                "online": True,
                "firmware_version": "1.1.0-sim",
            },
            retain=True,
        )

    publish_cluster1_status(client)
    publish_cluster2_status(client)
    publish_cam_status(client)


def on_message(client: mqtt.Client, userdata, msg: mqtt.MQTTMessage) -> None:
    topic = msg.topic
    raw = msg.payload.decode("utf-8", errors="replace")
    print(f"[SIM RX] {topic} <- {raw}")
    try:
        doc = json.loads(raw)
    except json.JSONDecodeError:
        return

    now_ms = int(time.monotonic() * 1000)

    # 1. Xử lý lệnh điều khiển Cụm 1
    if topic == "smarthome/device/cluster1/command":
        cmd_id = doc.get("command_id", "unknown")
        cluster1_state["mode"] = doc.get("mode", cluster1_state["mode"])
        if isinstance(doc.get("outputs"), dict):
            if "light" in doc["outputs"]:
                cluster1_state["light"] = bool(doc["outputs"]["light"])
            if "buzzer" in doc["outputs"]:
                cluster1_state["buzzer"] = bool(doc["outputs"]["buzzer"])
        elif "state" in doc:
            enabled = doc["state"] == "ON"
            target = doc.get("device_id", "esp32_cluster1")
            if target == "light_1":
                cluster1_state["light"] = enabled
            elif target == "buzzer_1":
                cluster1_state["buzzer"] = enabled
            else:
                cluster1_state["light"] = enabled
                cluster1_state["buzzer"] = enabled

        publish_json(
            client,
            "smarthome/device/cluster1/ack",
            {
                "schema_version": 1,
                "command_id": cmd_id,
                "device_id": "esp32_cluster1",
                "mode": cluster1_state["mode"],
                "success": True,
                "error": None,
                "outputs": {
                    "light": cluster1_state["light"],
                    "buzzer": cluster1_state["buzzer"],
                },
                "timestamp_ms": now_ms,
            },
        )
        publish_cluster1_status(client)

    # 2. Xử lý lệnh điều khiển Cụm 2
    elif topic == "smarthome/device/cluster2/command":
        cmd_id = doc.get("command_id", "unknown")
        cluster2_state["mode"] = doc.get("mode", cluster2_state["mode"])
        if isinstance(doc.get("outputs"), dict):
            if "light" in doc["outputs"]:
                cluster2_state["light"] = bool(doc["outputs"]["light"])
            if "fan" in doc["outputs"]:
                cluster2_state["fan"] = bool(doc["outputs"]["fan"])
        elif "state" in doc:
            enabled = doc["state"] == "ON"
            target = doc.get("device_id", "esp32_cluster2")
            if target in ("light_2", "light_1"):
                cluster2_state["light"] = enabled
            elif target == "fan_1":
                cluster2_state["fan"] = enabled

        publish_json(
            client,
            "smarthome/device/cluster2/ack",
            {
                "schema_version": 1,
                "command_id": cmd_id,
                "device_id": "esp32_cluster2",
                "mode": cluster2_state["mode"],
                "success": True,
                "error": None,
                "outputs": {
                    "light": cluster2_state["light"],
                    "fan": cluster2_state["fan"],
                },
                "timestamp_ms": now_ms,
            },
        )
        publish_cluster2_status(client)

    # 3. Xử lý lệnh đóng/mở cửa Servo SG90 trên ESP32-CAM
    elif topic == "smarthome/security/access/esp32_cam_01/command":
        cmd_id = doc.get("command_id", "unknown")
        evt_id = doc.get("event_id", cmd_id)
        action = doc.get("action", "KEEP_LOCKED")
        identity = doc.get("identity", "UNKNOWN")
        person_name = doc.get("person_name", "unknown")
        confidence = float(doc.get("confidence", 0.0))
        authorized = bool(doc.get("authorized", False))

        cam_state["last_identity"] = identity
        cam_state["last_person_name"] = person_name

        if action == "OPEN" and identity == "KNOWN" and authorized:
            cam_state["door_state"] = "OPEN"
            cam_state["servo_angle_deg"] = 90
            cam_state["door_opened_at"] = time.monotonic()
            print("[SIM CAM] KHỚP MẶT CHỦ NHÀ -> Quay Servo SG90 góc 90° MỞ CỬA!")
        else:
            cam_state["door_state"] = "LOCKED"
            cam_state["servo_angle_deg"] = 0
            print("[SIM CAM] KHÔNG KHỚP MẶT CHỦ NHÀ -> Giữ nguyên Servo SG90 góc 0° (KHÓA CỬA)!")

        publish_json(
            client,
            "smarthome/security/recognition",
            {
                "schema_version": 1,
                "event_id": evt_id,
                "device_id": "esp32_cam_01",
                "identity": identity,
                "person_name": person_name,
                "confidence": confidence,
                "authorized": cam_state["door_state"] == "OPEN",
                "door_action": "OPEN" if cam_state["door_state"] == "OPEN" else "KEEP_LOCKED",
                "door_state": cam_state["door_state"],
                "timestamp_ms": now_ms,
            },
        )
        publish_json(
            client,
            "smarthome/security/access/esp32_cam_01/ack",
            {
                "schema_version": 1,
                "command_id": cmd_id,
                "event_id": evt_id,
                "device_id": "esp32_cam_01",
                "identity": identity,
                "success": True,
                "error": None,
                "door_state": cam_state["door_state"],
                "servo_angle_deg": cam_state["servo_angle_deg"],
                "timestamp_ms": now_ms,
            },
        )
        publish_cam_status(client)


def main() -> None:
    if hasattr(mqtt, "CallbackAPIVersion"):
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id="esp32_all_simulator")
    else:
        client = mqtt.Client(client_id="esp32_all_simulator")

    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(BROKER_HOST, BROKER_PORT, keepalive=30)
    client.loop_start()

    last_c2_sample = 0.0
    last_c1_toggle = 0.0

    try:
        while True:
            now = time.monotonic()
            now_ms = int(now * 1000)

            # Tự động đóng cửa SG90 về 0 độ sau 5 giây mở cửa
            if cam_state["door_state"] == "OPEN" and (now - cam_state["door_opened_at"] >= 5.0):
                cam_state["door_state"] = "LOCKED"
                cam_state["servo_angle_deg"] = 0
                print("[SIM CAM] Hết 5 giây -> Tự động quay Servo SG90 về 0° ĐÓNG CỬA.")
                publish_cam_status(client)

            # Cụm 2: mỗi 2 giây đọc nhiệt độ, độ ẩm, ánh sáng và tự động bật/tắt quạt & đèn
            if now - last_c2_sample >= 2.0:
                last_c2_sample = now
                cluster2_state["seq"] += 1
                # Dao động nhẹ quanh ngưỡng để dễ quan sát kịch bản
                temp = round(random.choice([31.5, 32.0, 27.5]), 1)
                hum = round(random.choice([36.0, 38.5, 48.0]), 1)
                adc = random.choice([1200, 1500, 2600])
                is_dark = adc < 2000

                cluster2_state["temperature_c"] = temp
                cluster2_state["humidity_pct"] = hum
                cluster2_state["light_adc"] = adc
                cluster2_state["light_lux"] = round(15.0 if is_dark else 240.0, 1)
                cluster2_state["is_dark"] = is_dark

                if cluster2_state["mode"] == "AUTO":
                    # Kịch bản Cụm 2:
                    # - Trời tối -> bật đèn, trời sáng -> tắt đèn
                    cluster2_state["light"] = is_dark
                    # - Độ ẩm thấp (<= 40%) và nhiệt độ cao (>= 30°C) -> bật quạt, không thì tắt
                    cluster2_state["fan"] = (temp >= 30.0) and (hum <= 40.0)

                publish_json(
                    client,
                    "smarthome/sensor/cluster2",
                    {
                        "schema_version": 1,
                        "message_id": f"cluster2_sim_{cluster2_state['seq']}",
                        "device_id": "esp32_cluster2",
                        "mode": cluster2_state["mode"],
                        "timestamp_ms": now_ms,
                        "temperature_c": cluster2_state["temperature_c"],
                        "humidity_pct": cluster2_state["humidity_pct"],
                        "light_adc": cluster2_state["light_adc"],
                        "light_lux": cluster2_state["light_lux"],
                        "is_dark": cluster2_state["is_dark"],
                        "outputs": {
                            "light": cluster2_state["light"],
                            "fan": cluster2_state["fan"],
                        },
                    },
                )
                publish_cluster2_status(client)

            # Cụm 1: mỗi 12 giây giả lập có chuyển động PIR trong 5 giây rồi tắt
            if not cluster1_state["pir"] and (now - last_c1_toggle >= 12.0):
                last_c1_toggle = now
                cluster1_state["pir"] = True
                cluster1_state["seq"] += 1
                if cluster1_state["mode"] == "AUTO":
                    cluster1_state["light"] = True
                    cluster1_state["buzzer"] = True

                evt_payload = {
                    "schema_version": 1,
                    "event_id": f"motion_sim_{cluster1_state['seq']}",
                    "device_id": "esp32_cluster1",
                    "event_type": "MOTION_DETECTED",
                    "pir": True,
                    "outputs": {
                        "light": cluster1_state["light"],
                        "buzzer": cluster1_state["buzzer"],
                    },
                    "timestamp_ms": now_ms,
                }
                publish_json(client, "smarthome/security/motion", evt_payload)
                publish_json(client, "smarthome/sensor/cluster1", evt_payload)
                publish_cluster1_status(client)

            elif cluster1_state["pir"] and (now - last_c1_toggle >= 5.0):
                last_c1_toggle = now
                cluster1_state["pir"] = False
                cluster1_state["seq"] += 1
                if cluster1_state["mode"] == "AUTO":
                    cluster1_state["light"] = False
                    cluster1_state["buzzer"] = False

                clear_payload = {
                    "schema_version": 1,
                    "event_id": f"motion_sim_{cluster1_state['seq']}",
                    "device_id": "esp32_cluster1",
                    "event_type": "MOTION_CLEARED",
                    "pir": False,
                    "outputs": {
                        "light": cluster1_state["light"],
                        "buzzer": cluster1_state["buzzer"],
                    },
                    "timestamp_ms": now_ms,
                }
                publish_json(client, "smarthome/sensor/cluster1", clear_payload)
                publish_cluster1_status(client)

            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n[SIM] Đang dừng giả lập...")
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
