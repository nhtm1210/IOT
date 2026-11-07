# Firmware Smart Home IoT

## Main hardware firmware

- `esp32-cluster1-test`: PIR GPIO27, LED GPIO26 and buzzer GPIO25; motion interrupt turns on the LED/buzzer and a new motion extends the 5-second timer. This is the active firmware for cluster 1.
- `esp32-cluster2-test`: DHT22 GPIO4, LDR ADC GPIO34, BH1750 I2C, light GPIO2 and fan relay GPIO5; automatic darkness and temperature/humidity rules. This is the active firmware for cluster 2.

The two cluster projects match the current physical setup and keep local automation active without Wi-Fi or MQTT. They publish telemetry and status whenever MQTT is available. The earlier `esp32-sensor-node` and `esp32-control-node` projects are retained as prototypes for the original architecture; they use a different pin map.

## Other firmware

- `esp32-cam`: AI Thinker camera page, motion-triggered JPEG upload, MQTT-controlled SG90 door.

All projects target PlatformIO with Arduino Framework. Install PlatformIO Core or the VS Code extension, then run `pio run` from each project directory.

## Configure Wi-Fi and MQTT

For each cluster and camera project, copy `include/secrets.example.h` to `include/secrets.h` and set Wi-Fi and broker values. In the camera project also set `RECOGNITION_URL` to the backend's LAN HTTP endpoint. Local secrets are ignored by Git. `MQTT_HOST` must be the broker's LAN address, not `localhost`.

The active topics, JSON schemas, HTTP image upload, recognition states and door command are specified in [MQTT_SPEC.md](MQTT_SPEC.md). PubSubClient publishes at QoS 0, so backend must correlate app-level ACKs and use timeouts.

## Cluster 1

`esp32-cluster1-test` uses PIR GPIO27, LED GPIO26 and buzzer GPIO25. A rising PIR interrupt turns on the LED and buzzer; each new trigger restarts the 5-second hold timer. Set `BUZZER_ACTIVE_HIGH` in `include/pins.h` to `false` if the buzzer module is active-low.

```sh
cd esp32-cluster1-test
pio run
pio run -t upload --upload-port COM3
pio device monitor -b 115200 -p COM3
```

Replace `COM3` with the port shown by `pio device list`.

## Cluster 2

`esp32-cluster2-test` follows the supplied wiring: DHT22 GPIO4, LDR analog output GPIO34, BH1750 SDA/SCL GPIO22/21, light output GPIO2, and fan relay input GPIO5. Local control works without Wi-Fi or MQTT; sensor telemetry and output status publish when connected. Light turns on when the LDR ADC reading is below 2000. The fan turns on only when temperature is at least 30 C and humidity is at most 40%; it turns off at 28 C or below, or humidity 45% or above. These are initial control thresholds and can be adjusted in `include/pins.h`. BH1750 lux is reported for comparison; the analog LDR reading drives the light rule, matching the supplied sketch.

The relay output defaults to active-high. Check the relay module's input polarity before connecting the fan, and power the fan through the relay/driver with a suitable supply. Never power a fan directly from an ESP32 GPIO.

```sh
cd esp32-cluster2-test
pio run
pio run -t upload --upload-port COM3
pio device monitor -b 115200 -p COM3
```

Replace `COM3` with the port shown by `pio device list`.

## ESP32-CAM

The camera project uses the AI Thinker pin map, provides a local capture page at `http://<camera-ip>/`, uploads JPEGs to the backend on motion/manual capture, and accepts backend access commands for the SG90 on GPIO13. Confirm the board is AI Thinker and leave the SD slot unused. Recognition runs in backend; the camera fails closed and opens only for a matching `KNOWN` + `authorized: true` command. Power SG90 from a suitable 5V supply with common ground; do not power it from the 3.3V pin. Uploading this firmware replaces the firmware currently on the camera, so the local page will be provided by this project afterward and its IP may differ if DHCP assigns another address.

```powershell
cd esp32-cam
Copy-Item include/secrets.example.h include/secrets.h
# Edit secrets.h: Wi-Fi, MQTT broker, and backend LAN URL.
py -m platformio run
py -m platformio run -t upload --upload-port COM3
py -m platformio device monitor -b 115200 -p COM3
```

Use the current serial port instead of `COM3`. The cluster projects use the same secrets setup and PlatformIO upload flow. The camera page's “Chup anh moi” button returns the JPEG and submits it to the backend recognition endpoint.

The older `esp32-sensor-node` and `esp32-control-node` projects use the original draft pin map and message contract. Use them only if the hardware is rewired to match. The active cluster and camera interfaces are documented in [MQTT_SPEC.md](MQTT_SPEC.md).
