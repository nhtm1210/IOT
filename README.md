# Firmware Smart Home IoT

## Main hardware firmware

- `esp32-cluster1-test`: PIR GPIO27, LED GPIO26 and buzzer GPIO25; motion interrupt turns on the LED/buzzer and a new motion extends the 5-second timer. This is the active firmware for cluster 1.
- `esp32-cluster2-test`: DHT22 GPIO4, LDR ADC GPIO34, BH1750 I2C, light GPIO2 and fan relay GPIO5; automatic darkness and temperature/humidity rules. This is the active firmware for cluster 2.

These two cluster projects match the current physical setup and run locally without Wi-Fi or MQTT. The earlier `esp32-sensor-node` and `esp32-control-node` projects are retained as MQTT integration prototypes for the original architecture; they use a different pin map.

## Other firmware

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

## Cluster 1

`esp32-cluster1-test` uses PIR GPIO27, LED GPIO26 and buzzer GPIO25. A rising PIR interrupt turns on the LED and buzzer; each new trigger restarts the 5-second hold timer. Set `BUZZER_ACTIVE_HIGH` in `include/pins.h` to `false` if the buzzer module is active-low.

```sh
cd firmware/esp32-cluster1-test
pio run
pio run -t upload --upload-port COM3
pio device monitor -b 115200 -p COM3
```

Replace `COM3` with the port shown by `pio device list`.

## Cluster 2

`esp32-cluster2-test` follows the supplied wiring: DHT22 GPIO4, LDR analog output GPIO34, BH1750 SDA/SCL GPIO22/21, light output GPIO2, and fan relay input GPIO5. It runs without Wi-Fi or MQTT. Light turns on when the LDR ADC reading is below 2000. The fan turns on only when temperature is at least 30 C and humidity is at most 40%; it turns off at 28 C or below, or humidity 45% or above. These are initial control thresholds and can be adjusted in `include/pins.h`. BH1750 lux is reported for comparison; the analog LDR reading drives the light rule, matching the supplied sketch.

The relay output defaults to active-high. Check the relay module's input polarity before connecting the fan, and power the fan through the relay/driver with a suitable supply. Never power a fan directly from an ESP32 GPIO.

```sh
cd firmware/esp32-cluster2-test
pio run
pio run -t upload --upload-port COM3
pio device monitor -b 115200 -p COM3
```

Replace `COM3` with the port shown by `pio device list`.

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
