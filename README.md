# Firmware Smart Home IoT

## Projects

- `esp32-sensor-node`: DHT22, BH1750, two PIR, MC-38; MQTT telemetry to backend.
- `esp32-control-node`: LED, fan MOSFET, buzzer; MQTT command, ACK and status.
- `esp32-cam`: AI Thinker ESP32-CAM initialization and periodic JPEG capture diagnostic.

All projects target PlatformIO with Arduino Framework. Install PlatformIO Core or the VS Code extension, then run `pio run` from each project directory.

## Configure Wi-Fi and MQTT

In the sensor and control projects, copy `include/secrets.example.h` to `include/secrets.h` and set the Wi-Fi and broker values. The local secrets file is ignored by Git. `MQTT_HOST` must be the LAN address of the broker, not `localhost`.

Default MQTT topics:

| Topic | Direction | Purpose |
|---|---|---|
| `smarthome/sensor/node1` | Sensor → backend | Sensor snapshot every 5 seconds and on digital input changes |
| `smarthome/device/node2/command` | Backend → control | Set desired output state |
| `smarthome/device/node2/ack` | Control → backend | Command result keyed by `command_id` |
| `smarthome/device/node2/status` | Control → backend | Retained output state |
| `smarthome/system/node1/status` | Sensor → backend | Retained node state and Last Will |
| `smarthome/system/node2/status` | Control → backend | Node state and Last Will |

PubSubClient publishes telemetry, ACK, status and Last Will at QoS 0; command subscription requests QoS 1. Backend should publish commands at QoS 1 and still enforce an application-level ACK timeout, since MQTT delivery does not prove output application and device ACK can be lost.

## Sensor node

Default pin map follows the project overview: BH1750 SDA/SCL 21/22, MC-38 25, DHT22 27, PIR 32/33. Door input is enabled with `INPUT_PULLUP`; for a contact wired from GPIO25 to GND, LOW means closed and HIGH means open. Verify the physical wiring and contact behavior before powering the board.

Build/upload/monitor:

```sh
cd firmware/esp32-sensor-node
pio run
pio run -t upload
pio device monitor -b 115200
```

## Control node

Suggested pin map is LED GPIO18, fan MOSFET input GPIO19, buzzer GPIO23. These are defaults for the firmware and must match the assembled wiring. The fan must use a MOSFET and suitable external supply, never a GPIO directly. Set `OUTPUT_ACTIVE_HIGH` in `include/pins.h` to `false` for active-low modules. All outputs start OFF.

The firmware accepts the grouped `outputs` command schema below and the legacy single-device `state` command (`light_1`, `fan_1`, `buzzer_1`). Commands set desired state and are idempotent; they do not toggle.

```json
{
  "schema_version": 1,
  "command_id": "cmd_0001",
  "device_id": "esp32_control_01",
  "mode": "MANUAL",
  "outputs": { "light": true, "fan": false, "buzzer": false }
}
```

## ESP32-CAM

The camera project uses the AI Thinker pin map and board definition `esp32cam`. Confirm the module label matches AI Thinker before upload; camera pinouts differ across ESP32-CAM variants. This first firmware checks camera initialization and captures a JPEG every 10 seconds, reporting its size and dimensions over Serial. It does not claim face recognition and does not transmit images.

## Payloads

Sensor telemetry uses nullable numeric measurements and UTC timestamps when NTP is available:

```json
{
  "schema_version": 1,
  "message_id": "sensor_01_42",
  "device_id": "esp32_sensor_01",
  "timestamp": "2026-11-06T02:30:00Z",
  "temperature_c": 28.5,
  "humidity_pct": 65.2,
  "light_lux": 120.5,
  "pir_1": true,
  "pir_2": false,
  "door_open": true
}
```

Command ACK includes `command_id`, `success`, `error`, and actual applied output state. Backend should wait for ACK/status; successful MQTT publish alone is not confirmation that firmware applied the command.
