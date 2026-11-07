# Firmware ↔ Backend Contract

Version 1 contract for the current two ESP32 clusters and AI Thinker ESP32-CAM. The two cluster nodes keep their local automation active if Wi-Fi or MQTT is unavailable. Backend owns persistence, user enrollment, face matching and the access decision. ESP32-CAM never opens the door from a local face guess; it requires an authorized MQTT command from the backend.

## Broker and wire rules

- Broker: MQTT TCP, normally port `1883` on the backend host's LAN address. Configure per node in `include/secrets.h`; never commit this file.
- JSON UTF-8; `schema_version` is integer `1`; device timestamps use `timestamp_ms` (ESP uptime) because nodes do not require NTP.
- Firmware uses PubSubClient. It subscribes at QoS 1; PubSubClient publishes at QoS 0. Backend should publish commands at QoS 1 and use the application ACK topics below. Do not retain command messages. Device status and online state are retained.
- Keep the broker LAN-only for the demo and configure credentials/ACL so only the backend can publish access commands. Never expose the unauthenticated broker to the public internet.
- Device IDs are `esp32_cluster1`, `esp32_cluster2`, and `esp32_cam_01`.

## Topics

| Topic | Direction | QoS / retain | Purpose |
|---|---|---|---|
| `smarthome/security/motion` | Cluster 1 → backend and camera | 0 / no | Motion event; backend stores it, CAM captures and uploads an image |
| `smarthome/sensor/cluster1` | Cluster 1 → backend | 0 / no | Same motion event for sensor/event history |
| `smarthome/sensor/cluster2` | Cluster 2 → backend | 0 / no | DHT, light sensor and local output snapshot every 2 s |
| `smarthome/device/cluster1/status` | Cluster 1 → backend | 0 / yes | Alarm light/buzzer applied state |
| `smarthome/device/cluster2/status` | Cluster 2 → backend | 0 / yes | AUTO mode and light/fan applied state |
| `smarthome/system/cluster1/status` | Cluster 1 → backend | 0 / yes | Online state; Last Will says offline |
| `smarthome/system/cluster2/status` | Cluster 2 → backend | 0 / yes | Online state; Last Will says offline |
| `smarthome/system/esp32_cam_01/status` | CAM → backend | 0 / yes | Camera/door node availability |
| `smarthome/device/esp32_cam_01/status` | CAM → backend | 0 / yes | Camera ready and current door state |
| `smarthome/security/access/esp32_cam_01/command` | Backend → CAM | subscribe QoS 1, do not retain | Authorized door action after recognition |
| `smarthome/security/access/esp32_cam_01/ack` | CAM → backend | 0 / no | Door command result |

## Cluster 1 motion event

PIR GPIO27 rising edge turns on LED GPIO26 and active buzzer GPIO25 for 5 seconds after the latest motion. Each event is published to both motion and sensor topics.

```json
{
  "schema_version": 1,
  "event_id": "motion_12ab34cd_1",
  "device_id": "esp32_cluster1",
  "event_type": "MOTION_DETECTED",
  "pir": true,
  "timestamp_ms": 23841
}
```

CAM subscribes to `smarthome/security/motion`, captures JPEG, and sends it to the backend HTTP endpoint below. Backend should deduplicate by `event_id`.

## Cluster 2 sensor snapshot

GPIO mapping: DHT22 GPIO4; LDR analog GPIO34; BH1750 SDA/SCL GPIO22/21; lamp output GPIO2; fan relay input GPIO5. Light is ON when `light_adc < 2000`. Fan turns ON when temperature is at least 30 C AND humidity is at most 40%; it turns OFF when temperature is at most 28 C OR humidity is at least 45%. These are initial thresholds, configurable in `esp32-cluster2-test/include/pins.h`.

```json
{
  "schema_version": 1,
  "message_id": "cluster2_12ab34cd_1",
  "device_id": "esp32_cluster2",
  "timestamp_ms": 12000,
  "temperature_c": 31.2,
  "humidity_pct": 38.0,
  "light_adc": 1400,
  "light_lux": 12.4,
  "is_dark": true,
  "outputs": { "light": true, "fan": true }
}
```

`temperature_c`, `humidity_pct`, and `light_lux` can be `null` on read failure. `light_adc` and `is_dark` use the analog LDR, matching the local automation; BH1750 is reported for monitoring.

## Camera image upload and recognition

When it receives a motion event (or when a user clicks “Chup anh moi” at the camera's local page), CAM sends the JPEG body by HTTP:

```http
POST /api/security/recognize HTTP/1.1
Content-Type: image/jpeg
X-Device-Id: esp32_cam_01
X-Event-Id: motion_12ab34cd_1
```

Default full URL is configured as `RECOGNITION_URL` in `esp32-cam/include/secrets.h`; the example is `http://192.168.1.10:8000/api/security/recognize`. Backend should accept raw JPEG bytes and return `200` or `202` after accepting the event. It must perform face detection/matching against enrolled owner data, persist the recognition, and publish one door command. The ESP32-CAM does not contain an enrolled face template or perform face matching itself.

Recognition state contract: `NO_FACE` means no face found; `KNOWN` means a face matched an enrolled, authorized resident; `UNKNOWN` means a face exists but no enrolled identity matched. Do not treat camera/network failure as `UNKNOWN` and do not open for `UNKNOWN` or `NO_FACE`. Require confidence policy and preferably multiple consecutive frames in backend before authorization.

## Backend door command

Publish to `smarthome/security/access/esp32_cam_01/command`, QoS 1, retain false:

```json
{
  "schema_version": 1,
  "command_id": "access_00042",
  "event_id": "motion_12ab34cd_1",
  "device_id": "esp32_cam_01",
  "identity": "KNOWN",
  "authorized": true,
  "action": "OPEN"
}
```

For `UNKNOWN`, `NO_FACE`, or any denied result publish `action: "KEEP_LOCKED"`, `authorized: false`, and the matching identity value. CAM accepts `OPEN` only when `identity == "KNOWN"` AND `authorized == true` AND `device_id` matches. It rotates SG90 to 90 degrees, then returns it to 0 degrees after 5 seconds. `OPEN` and `KEEP_LOCKED` are set-state operations, not toggles.

CAM publishes an ACK:

```json
{
  "schema_version": 1,
  "command_id": "access_00042",
  "event_id": "motion_12ab34cd_1",
  "device_id": "esp32_cam_01",
  "success": true,
  "error": null,
  "door_state": "OPEN",
  "timestamp_ms": 24100
}
```

Backend correlates using `command_id` and `event_id`, sets a timeout, and stores the final door result. Since device publishes are QoS 0, it should not interpret successful broker publish as successful door movement.

## Minimum backend work

1. Mosquitto configured on a LAN-reachable address; subscribe to `smarthome/#` during integration.
2. Persist cluster telemetry, motion events, node status, recognition results and access ACKs.
3. Implement `POST /api/security/recognize` to accept JPEG raw body and headers above. Enroll owner reference images/descriptors securely; classify `NO_FACE`, `KNOWN`, `UNKNOWN`.
4. Publish `OPEN` only for authorized `KNOWN`; publish `KEEP_LOCKED` otherwise.
5. Expose stored recognition/access events to the frontend API when it is ready.
