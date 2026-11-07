#include <Arduino.h>
#include <ArduinoJson.h>
#include <ESP32Servo.h>
#include <HTTPClient.h>
#include <PubSubClient.h>
#include <WebServer.h>
#include <WiFi.h>
#include "esp_camera.h"

#if __has_include("secrets.h")
#include "secrets.h"
#else
#include "secrets.example.h"
#endif

namespace {
constexpr char DEVICE_ID[] = "esp32_cam_01";
constexpr char MOTION_TOPIC[] = "smarthome/security/motion";
constexpr char ACCESS_COMMAND_TOPIC[] = "smarthome/security/access/esp32_cam_01/command";
constexpr char ACCESS_ACK_TOPIC[] = "smarthome/security/access/esp32_cam_01/ack";
constexpr char CAMERA_STATUS_TOPIC[] = "smarthome/device/esp32_cam_01/status";
constexpr char SYSTEM_STATUS_TOPIC[] = "smarthome/system/esp32_cam_01/status";

// AI Thinker ESP32-CAM camera pin map.
constexpr int PWDN_GPIO_NUM = 32;
constexpr int RESET_GPIO_NUM = -1;
constexpr int XCLK_GPIO_NUM = 0;
constexpr int SIOD_GPIO_NUM = 26;
constexpr int SIOC_GPIO_NUM = 27;
constexpr int Y9_GPIO_NUM = 35;
constexpr int Y8_GPIO_NUM = 34;
constexpr int Y7_GPIO_NUM = 39;
constexpr int Y6_GPIO_NUM = 36;
constexpr int Y5_GPIO_NUM = 21;
constexpr int Y4_GPIO_NUM = 19;
constexpr int Y3_GPIO_NUM = 18;
constexpr int Y2_GPIO_NUM = 5;
constexpr int VSYNC_GPIO_NUM = 25;
constexpr int HREF_GPIO_NUM = 23;
constexpr int PCLK_GPIO_NUM = 22;

// GPIO13 is exposed on AI Thinker boards and is available when the SD slot is unused.
constexpr int SERVO_PIN = 13;
constexpr int DOOR_CLOSED_DEG = 0;
constexpr int DOOR_OPEN_DEG = 90;
constexpr uint32_t DOOR_OPEN_MS = 5000;
constexpr uint32_t WIFI_RETRY_MS = 10000;
constexpr uint32_t MQTT_RETRY_MS = 5000;
constexpr uint32_t CAPTURE_COOLDOWN_MS = 3000;
constexpr char ROOT_PAGE[] =
    "<!doctype html><html><head><meta name='viewport' content='width=device-width,initial-scale=1'>"
    "<title>Smart Home Camera</title></head><body><h2>Smart Home Camera</h2>"
    "<button id='capture'>Chup anh moi</button><p id='state'></p><img id='photo' style='max-width:100%;height:auto'>"
    "<script>document.getElementById('capture').onclick=async()=>{let s=document.getElementById('state');"
    "s.textContent='Dang chup va gui backend...';let r=await fetch('/capture?t='+Date.now());"
    "if(!r.ok){s.textContent='Chup/gui that bai: '+r.status;return;}"
    "document.getElementById('photo').src=URL.createObjectURL(await r.blob());s.textContent='Da chup; backend dang xu ly nhan dien.';};</script></body></html>";

WebServer server(80);
WiFiClient networkClient;
PubSubClient mqtt(networkClient);
Servo doorServo;
bool cameraReady = false;
bool webStarted = false;
bool doorOpen = false;
uint32_t doorOpenedAt = 0;
uint32_t lastWiFiAttempt = 0;
uint32_t lastMqttAttempt = 0;
uint32_t lastCaptureAt = 0;
uint32_t captureSequence = 0;
String pendingMotionEvent;
String lastCommandId;

bool initializeCamera() {
  camera_config_t config{};
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;
  config.frame_size = psramFound() ? FRAMESIZE_SVGA : FRAMESIZE_VGA;
  config.jpeg_quality = 12;
  config.fb_count = psramFound() ? 2 : 1;
  config.grab_mode = CAMERA_GRAB_LATEST;
  config.fb_location = psramFound() ? CAMERA_FB_IN_PSRAM : CAMERA_FB_IN_DRAM;

  const esp_err_t result = esp_camera_init(&config);
  if (result != ESP_OK) {
    Serial.printf("[camera] init failed: 0x%x\n", result);
    return false;
  }
  Serial.printf("[camera] ready, psram=%s\n", psramFound() ? "yes" : "no");
  return true;
}

void setDoor(bool open) {
  doorOpen = open;
  doorServo.write(open ? DOOR_OPEN_DEG : DOOR_CLOSED_DEG);
  if (open) doorOpenedAt = millis();
  Serial.printf("[door] %s\n", open ? "UNLOCKED" : "LOCKED");
}

void publishDoorAck(const char *commandId, const char *eventId,
                    bool success, const char *error) {
  if (!mqtt.connected()) return;
  JsonDocument doc;
  doc["schema_version"] = 1;
  doc["command_id"] = commandId;
  doc["event_id"] = eventId;
  doc["device_id"] = DEVICE_ID;
  doc["success"] = success;
  doc["error"] = error ? error : nullptr;
  doc["door_state"] = doorOpen ? "OPEN" : "LOCKED";
  doc["timestamp_ms"] = millis();
  char payload[320];
  const size_t size = serializeJson(doc, payload, sizeof(payload));
  if (size && size < sizeof(payload)) mqtt.publish(ACCESS_ACK_TOPIC, payload, false);
}

void handleAccessCommand(const byte *payload, unsigned int length) {
  JsonDocument doc;
  const DeserializationError parseError = deserializeJson(doc, payload, length);
  const char *commandId = doc["command_id"] | "";
  const char *eventId = doc["event_id"] | "";
  const char *target = doc["device_id"] | "";
  const char *action = doc["action"] | "";
  const char *identity = doc["identity"] | "";
  const bool authorized = doc["authorized"] | false;
  if (parseError || !commandId[0] || !eventId[0] || strcmp(target, DEVICE_ID) != 0) {
    publishDoorAck(commandId, eventId, false, "INVALID_COMMAND");
    return;
  }
  if (lastCommandId.equals(commandId)) {
    publishDoorAck(commandId, eventId, true, nullptr);
    return;
  }
  if (strcmp(action, "OPEN") == 0 && strcmp(identity, "KNOWN") == 0 && authorized) {
    lastCommandId = commandId;
    setDoor(true);
    publishDoorAck(commandId, eventId, true, nullptr);
    return;
  }
  if (strcmp(action, "KEEP_LOCKED") == 0) {
    lastCommandId = commandId;
    setDoor(false);
    publishDoorAck(commandId, eventId, true, nullptr);
    return;
  }
  publishDoorAck(commandId, eventId, false, "ACCESS_DENIED");
}

void mqttCallback(char *topic, byte *payload, unsigned int length) {
  if (strcmp(topic, MOTION_TOPIC) == 0) {
    JsonDocument doc;
    if (deserializeJson(doc, payload, length)) return;
    const char *eventId = doc["event_id"] | "";
    if (eventId[0]) {
      pendingMotionEvent = eventId;
      Serial.printf("[motion] trigger received: %s\n", eventId);
    }
  } else if (strcmp(topic, ACCESS_COMMAND_TOPIC) == 0) {
    handleAccessCommand(payload, length);
  }
}

void publishCameraStatus(bool online) {
  if (!mqtt.connected()) return;
  JsonDocument doc;
  doc["schema_version"] = 1;
  doc["device_id"] = DEVICE_ID;
  doc["online"] = online;
  doc["camera_ready"] = cameraReady;
  doc["door_state"] = doorOpen ? "OPEN" : "LOCKED";
  doc["firmware_version"] = "1.0.0";
  char payload[256];
  const size_t size = serializeJson(doc, payload, sizeof(payload));
  if (size && size < sizeof(payload)) mqtt.publish(CAMERA_STATUS_TOPIC, payload, true);
}

void connectWiFi() {
  if (WiFi.isConnected()) return;
  const uint32_t now = millis();
  if (lastWiFiAttempt && now - lastWiFiAttempt < WIFI_RETRY_MS) return;
  lastWiFiAttempt = now;
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.persistent(false);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.printf("[wifi] connecting to %s\n", WIFI_SSID);
}

void connectMqtt() {
  if (!WiFi.isConnected() || mqtt.connected()) return;
  const uint32_t now = millis();
  if (lastMqttAttempt && now - lastMqttAttempt < MQTT_RETRY_MS) return;
  lastMqttAttempt = now;
  const char *will = "{\"schema_version\":1,\"device_id\":\"esp32_cam_01\",\"online\":false}";
  const bool connected = MQTT_USERNAME[0]
      ? mqtt.connect(DEVICE_ID, MQTT_USERNAME, MQTT_PASSWORD, SYSTEM_STATUS_TOPIC, 1, true, will)
      : mqtt.connect(DEVICE_ID, SYSTEM_STATUS_TOPIC, 1, true, will);
  if (!connected) {
    Serial.printf("[mqtt] connect failed: %d\n", mqtt.state());
    return;
  }
  mqtt.subscribe(MOTION_TOPIC, 1);
  mqtt.subscribe(ACCESS_COMMAND_TOPIC, 1);
  mqtt.publish(SYSTEM_STATUS_TOPIC,
      "{\"schema_version\":1,\"device_id\":\"esp32_cam_01\",\"online\":true,\"firmware_version\":\"1.0.0\"}", true);
  publishCameraStatus(true);
  Serial.println("[mqtt] connected; subscribed to motion and access commands");
}

String makeCaptureEventId() {
  char id[48];
  snprintf(id, sizeof(id), "capture_%08lx_%lu",
           (unsigned long)(ESP.getEfuseMac() & 0xffffffff), (unsigned long)++captureSequence);
  return String(id);
}

bool uploadForRecognition(camera_fb_t *frame, const String &eventId) {
  if (!WiFi.isConnected()) {
    Serial.println("[recognition] no Wi-Fi; image not sent");
    return false;
  }
  HTTPClient http;
  http.setTimeout(8000);
  if (!http.begin(RECOGNITION_URL)) {
    Serial.println("[recognition] invalid backend URL");
    return false;
  }
  http.addHeader("Content-Type", "image/jpeg");
  http.addHeader("X-Device-Id", DEVICE_ID);
  http.addHeader("X-Event-Id", eventId);
  const int code = http.POST(frame->buf, frame->len);
  const String response = code > 0 ? http.getString() : http.errorToString(code);
  Serial.printf("[recognition] backend HTTP %d, event=%s, response=%s\n",
                code, eventId.c_str(), response.c_str());
  http.end();
  return code == HTTP_CODE_OK || code == HTTP_CODE_ACCEPTED;
}

camera_fb_t *captureAndSubmit(const String &eventId) {
  if (!cameraReady) return nullptr;
  camera_fb_t *frame = esp_camera_fb_get();
  if (!frame) {
    Serial.println("[camera] capture failed");
    return nullptr;
  }
  lastCaptureAt = millis();
  Serial.printf("[camera] captured event=%s, bytes=%u, %ux%u\n",
                eventId.c_str(), static_cast<unsigned>(frame->len), frame->width, frame->height);
  uploadForRecognition(frame, eventId);
  return frame;
}

void handleRoot() {
  server.send(200, "text/html; charset=utf-8", ROOT_PAGE);
}

void handleCapture() {
  camera_fb_t *frame = captureAndSubmit(makeCaptureEventId());
  if (!frame) {
    server.send(503, "text/plain; charset=utf-8", "Camera capture failed");
    return;
  }
  WiFiClient client = server.client();
  server.setContentLength(frame->len);
  server.send(200, "image/jpeg", "");
  client.write(frame->buf, frame->len);
  esp_camera_fb_return(frame);
}

void setupWebServer() {
  server.on("/", HTTP_GET, handleRoot);
  server.on("/capture", HTTP_GET, handleCapture);
  server.onNotFound([]() { server.send(404, "text/plain", "Not found"); });
  server.begin();
  Serial.printf("[web] camera page: http://%s/\n", WiFi.localIP().toString().c_str());
}

void processMotionCapture() {
  if (pendingMotionEvent.isEmpty()) return;
  if (!WiFi.isConnected() || !mqtt.connected()) return;
  if (lastCaptureAt && millis() - lastCaptureAt < CAPTURE_COOLDOWN_MS) return;
  const String eventId = pendingMotionEvent;
  pendingMotionEvent = "";
  camera_fb_t *frame = captureAndSubmit(eventId);
  if (frame) esp_camera_fb_return(frame);
}
}  // namespace

void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.println("\n[boot] ESP32-CAM face access firmware 1.0.0 (AI Thinker)");
  cameraReady = initializeCamera();

  doorServo.setPeriodHertz(50);
  doorServo.attach(SERVO_PIN, 500, 2400);
  setDoor(false);

  WiFi.setAutoReconnect(true);
  WiFi.persistent(false);
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(mqttCallback);
  mqtt.setBufferSize(512);
  mqtt.setKeepAlive(30);
  connectWiFi();
}

void loop() {
  connectWiFi();
  connectMqtt();
  if (mqtt.connected()) mqtt.loop();

  if (WiFi.isConnected() && !webStarted) {
    setupWebServer();
    webStarted = true;
  }
  if (webStarted) server.handleClient();
  processMotionCapture();

  if (doorOpen && millis() - doorOpenedAt >= DOOR_OPEN_MS) {
    setDoor(false);
    publishCameraStatus(true);
  }
  delay(2);
}
