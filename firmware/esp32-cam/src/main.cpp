#include <Arduino.h>
#include <ArduinoJson.h>
#include <ESP32Servo.h>
#include <HTTPClient.h>
#include <PubSubClient.h>
#include <WebServer.h>
#include <WiFi.h>
#include "esp_camera.h"

#include "pins.h"
#if __has_include("secrets.h")
#include "secrets.h"
#else
#include "secrets.example.h"
#endif

namespace {
constexpr char DEVICE_ID[] = "esp32_cam_01";
constexpr char MOTION_TOPIC[] = "smarthome/security/motion";
constexpr char RECOGNITION_TOPIC[] = "smarthome/security/recognition";
constexpr char ACCESS_COMMAND_TOPIC[] = "smarthome/security/access/esp32_cam_01/command";
constexpr char ACCESS_ACK_TOPIC[] = "smarthome/security/access/esp32_cam_01/ack";
constexpr char CAMERA_STATUS_TOPIC[] = "smarthome/device/esp32_cam_01/status";
constexpr char SYSTEM_STATUS_TOPIC[] = "smarthome/system/esp32_cam_01/status";

constexpr uint32_t WIFI_RETRY_MS = 10000;
constexpr uint32_t MQTT_RETRY_MS = 5000;
constexpr uint32_t CAPTURE_COOLDOWN_MS = 3000;
constexpr uint32_t STATUS_INTERVAL_MS = 30000;

constexpr char ROOT_PAGE[] =
    "<!doctype html><html><head><meta charset='utf-8'>"
    "<meta name='viewport' content='width=device-width,initial-scale=1'>"
    "<title>ESP32-CAM Smart Door Access</title>"
    "<style>body{font-family:sans-serif;max-width:640px;margin:16px auto;padding:0 12px}"
    "button{padding:10px 14px;margin-right:8px;cursor:pointer}#status{padding:10px;background:#f3f4f6;border-radius:6px}</style>"
    "</head><body><h2>ESP32-CAM Nhan Dien Chu Nha & Mo Cua SG90</h2>"
    "<div><button id='capture'>Chup anh & Nhan dien mo cua</button>"
    "<button id='enroll'>Luu mat chu nha (Enroll)</button></div>"
    "<p id='state'>San sang.</p><pre id='status'></pre>"
    "<img id='photo' style='max-width:100%;height:auto;border:1px solid #ccc;border-radius:6px'>"
    "<script>"
    "async function refreshStatus(){try{let r=await fetch('/status');if(r.ok){document.getElementById('status').textContent=JSON.stringify(await r.json(),null,2);}}catch(e){}}"
    "document.getElementById('capture').onclick=async()=>{let s=document.getElementById('state');"
    "s.textContent='Dang chup anh va doi chieu mat chu nha...';let r=await fetch('/capture?t='+Date.now());"
    "if(!r.ok){s.textContent='Chup/gui that bai: '+r.status;return;}"
    "document.getElementById('photo').src=URL.createObjectURL(await r.blob());"
    "s.textContent='Da gui anh nhan dien. Kiem tra trang thai cua ben duoi.';setTimeout(refreshStatus,800);};"
    "document.getElementById('enroll').onclick=async()=>{let s=document.getElementById('state');"
    "s.textContent='Dang chup va luu mau khuon mat chu nha...';let r=await fetch('/enroll?t='+Date.now(),{method:'POST'});"
    "s.textContent=await r.text();setTimeout(refreshStatus,800);};"
    "setInterval(refreshStatus,3000);refreshStatus();"
    "</script></body></html>";

WebServer server(80);
WiFiClient networkClient;
PubSubClient mqtt(networkClient);
Servo doorServo;

bool cameraReady = false;
bool webStarted = false;
bool doorOpen = false;
int currentServoDeg = DOOR_CLOSED_DEG;
uint32_t lastWiFiAttempt = 0;
uint32_t lastMqttAttempt = 0;
uint32_t lastCaptureAt = 0;
uint32_t lastStatusAt = 0;
uint32_t captureSequence = 0;

String pendingMotionEvent;
String lastCommandId;
String lastEventId;
String lastIdentity = "NONE";
String lastPersonName = "";
float lastConfidence = 0.0f;

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
  // Bật xử lý màu tự động của OV2640 để tránh ảnh xanh/tím khi ánh sáng thay đổi.
  sensor_t *sensor = esp_camera_sensor_get();
  if (sensor) {
    sensor->set_special_effect(sensor, 0); // màu tự nhiên
    sensor->set_whitebal(sensor, 1);       // auto white balance
    sensor->set_awb_gain(sensor, 1);
    sensor->set_wb_mode(sensor, 0);        // auto WB mode
    sensor->set_exposure_ctrl(sensor, 1);  // auto exposure
    sensor->set_aec2(sensor, 1);
    sensor->set_gain_ctrl(sensor, 1);      // auto gain
    sensor->set_bpc(sensor, 1);
    sensor->set_wpc(sensor, 1);
    sensor->set_raw_gma(sensor, 1);
    sensor->set_lenc(sensor, 1);
  }
  Serial.printf("[camera] ready, psram=%s\n", psramFound() ? "yes" : "no");
  return true;
}

void publishCameraStatus(bool online) {
  if (!mqtt.connected()) return;
  JsonDocument doc;
  doc["schema_version"] = 1;
  doc["device_id"] = DEVICE_ID;
  doc["online"] = online;
  doc["camera_ready"] = cameraReady;
  doc["door_state"] = doorOpen ? "OPEN" : "LOCKED";
  doc["servo_angle_deg"] = currentServoDeg;
  doc["last_identity"] = lastIdentity;
  if (lastPersonName.length()) doc["last_person_name"] = lastPersonName;
  else doc["last_person_name"] = nullptr;
  doc["firmware_version"] = "1.1.0";

  char payload[320];
  const size_t size = serializeJson(doc, payload, sizeof(payload));
  if (size && size < sizeof(payload)) {
    mqtt.publish(CAMERA_STATUS_TOPIC, payload, true);
  }
}

void setDoor(bool open) {
  doorOpen = open;
  currentServoDeg = open ? DOOR_OPEN_DEG : DOOR_CLOSED_DEG;
  doorServo.write(currentServoDeg);
  if (open) {
    Serial.printf("[door] MATCHED OWNER -> Servo SG90 rotated to %d deg (DOOR OPEN)\n",
                  currentServoDeg);
  } else {
    Serial.printf("[door] Servo SG90 at %d deg (DOOR LOCKED)\n", currentServoDeg);
  }
  publishCameraStatus(true);
}

void publishRecognitionEvent(const char *eventId, const char *identity,
                             const char *personName, float confidence,
                             bool authorized) {
  if (!mqtt.connected()) return;
  JsonDocument doc;
  doc["schema_version"] = 1;
  doc["event_id"] = eventId;
  doc["device_id"] = DEVICE_ID;
  doc["identity"] = identity;
  doc["person_name"] = (personName && personName[0]) ? personName : "unknown";
  doc["confidence"] = confidence;
  doc["authorized"] = authorized;
  doc["door_action"] = authorized ? "OPEN" : "KEEP_LOCKED";
  doc["door_state"] = doorOpen ? "OPEN" : "LOCKED";
  doc["timestamp_ms"] = millis();

  char payload[384];
  const size_t size = serializeJson(doc, payload, sizeof(payload));
  if (size && size < sizeof(payload)) {
    mqtt.publish(RECOGNITION_TOPIC, payload, false);
    Serial.printf("[recognition-event] %s\n", payload);
  }
}

void publishDoorAck(const char *commandId, const char *eventId,
                    bool success, const char *error) {
  if (!mqtt.connected()) return;
  JsonDocument doc;
  doc["schema_version"] = 1;
  doc["command_id"] = commandId;
  doc["event_id"] = eventId;
  doc["device_id"] = DEVICE_ID;
  doc["identity"] = lastIdentity;
  doc["success"] = success;
  doc["error"] = error ? error : nullptr;
  doc["door_state"] = doorOpen ? "OPEN" : "LOCKED";
  doc["servo_angle_deg"] = currentServoDeg;
  doc["timestamp_ms"] = millis();

  char payload[384];
  const size_t size = serializeJson(doc, payload, sizeof(payload));
  if (size && size < sizeof(payload)) {
    mqtt.publish(ACCESS_ACK_TOPIC, payload, false);
    Serial.printf("[ack] %s\n", payload);
  }
}

void applyAccessDecision(const char *commandId, const char *eventId,
                         const char *identity, const char *personName,
                         float confidence, bool authorized,
                         const char *action) {
  if (commandId && commandId[0] && lastCommandId.equals(commandId)) {
    publishDoorAck(commandId, eventId, true, nullptr);
    return;
  }
  if (commandId && commandId[0]) {
    lastCommandId = commandId;
  }
  if (eventId && eventId[0]) {
    lastEventId = eventId;
  }
  lastIdentity = (identity && identity[0]) ? identity : "UNKNOWN";
  lastPersonName = (personName && personName[0]) ? personName : "";
  lastConfidence = confidence;

  // Kịch bản:
  // - Nếu khớp khuôn mặt chủ nhà đã lưu sẵn (identity == "KNOWN", authorized == true, action == "OPEN"):
  //   Động cơ Servo SG90 quay góc 90 độ để mở cửa, giữ 5 giây rồi đóng lại.
  // - Nếu không khớp (UNKNOWN, NO_FACE, hoặc authorized == false):
  //   Động cơ Servo SG90 không quay (giữ nguyên ở góc 0 độ - LOCKED).
  if (strcmp(action, "OPEN") == 0 && strcmp(lastIdentity.c_str(), "KNOWN") == 0 && authorized) {
    setDoor(true);
    publishRecognitionEvent(eventId, lastIdentity.c_str(), lastPersonName.c_str(),
                            lastConfidence, true);
    publishDoorAck(commandId, eventId, true, nullptr);
    return;
  }

  // KEEP_LOCKED từ nhận diện chỉ giữ nguyên trạng thái hiện tại. Lệnh CLOSE
  // riêng từ Web mới được phép đóng một cửa đang mở.
  if (strcmp(action, "CLOSE") == 0) {
    setDoor(false);
  }
  publishRecognitionEvent(eventId, lastIdentity.c_str(), lastPersonName.c_str(),
                          lastConfidence, false);
  if (strcmp(action, "KEEP_LOCKED") == 0 || strcmp(action, "CLOSE") == 0) {
    publishDoorAck(commandId, eventId, true, nullptr);
  } else {
    publishDoorAck(commandId, eventId, false, "FACE_NOT_MATCHED_KEEP_LOCKED");
  }
}

void handleAccessCommand(const byte *payload, unsigned int length) {
  JsonDocument doc;
  const DeserializationError parseError = deserializeJson(doc, payload, length);
  const char *commandId = doc["command_id"] | "";
  const char *eventId = doc["event_id"] | "";
  const char *target = doc["device_id"] | DEVICE_ID;
  const char *action = doc["action"] | "";
  const char *identity = doc["identity"] | "UNKNOWN";
  const char *personName = doc["person_name"] | "";
  const float confidence = doc["confidence"] | 0.0f;
  const bool authorized = doc["authorized"] | false;

  if (parseError || !commandId[0] || strcmp(target, DEVICE_ID) != 0) {
    publishDoorAck(commandId, eventId, false, "INVALID_COMMAND");
    return;
  }

  // Cho phép Backend gửi lệnh yêu cầu chụp ảnh ngay lập tức nếu cần
  if (strcmp(action, "CAPTURE") == 0) {
    pendingMotionEvent = eventId[0] ? String(eventId) : String(commandId);
    publishDoorAck(commandId, pendingMotionEvent.c_str(), true, nullptr);
    return;
  }

  applyAccessDecision(commandId,
                      eventId[0] ? eventId : commandId,
                      identity,
                      personName,
                      confidence,
                      authorized,
                      action);
}

void mqttCallback(char *topic, byte *payload, unsigned int length) {
  if (strcmp(topic, MOTION_TOPIC) == 0) {
    JsonDocument doc;
    if (deserializeJson(doc, payload, length)) return;
    const char *eventId = doc["event_id"] | "";
    const bool pir = doc["pir"] | true;
    if (pir && eventId[0]) {
      pendingMotionEvent = eventId;
      Serial.printf("[motion] trigger received -> capture event=%s\n", eventId);
    }
  } else if (strcmp(topic, ACCESS_COMMAND_TOPIC) == 0) {
    handleAccessCommand(payload, length);
  }
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
      "{\"schema_version\":1,\"device_id\":\"esp32_cam_01\",\"online\":true,\"firmware_version\":\"1.1.0\"}", true);
  publishCameraStatus(true);
  Serial.println("[mqtt] connected; subscribed to motion and access commands");
}

String makeCaptureEventId(const char *prefix = "capture") {
  char id[48];
  snprintf(id, sizeof(id), "%s_%08lx_%lu",
           prefix,
           (unsigned long)(ESP.getEfuseMac() & 0xffffffff),
           (unsigned long)++captureSequence);
  return String(id);
}

bool uploadForRecognition(camera_fb_t *frame, const String &eventId, bool enrollOwner = false) {
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
  if (enrollOwner) {
    http.addHeader("X-Mode", "ENROLL_OWNER");
    http.addHeader("X-Person-Name", "owner");
  }

  const int code = http.POST(frame->buf, frame->len);
  const String response = code > 0 ? http.getString() : http.errorToString(code);
  Serial.printf("[recognition] backend HTTP %d, event=%s, response=%s\n",
                code, eventId.c_str(), response.c_str());
  http.end();

  // Nếu Backend trả về trực tiếp quyết định nhận diện trong JSON HTTP response,
  // xử lý ngay lập tức (đồng thời chống trùng lặp với lệnh MQTT qua command_id).
  if (!enrollOwner && (code == HTTP_CODE_OK || code == HTTP_CODE_ACCEPTED) && response.length() > 2) {
    JsonDocument respDoc;
    if (!deserializeJson(respDoc, response)) {
      const char *identity = respDoc["identity"] | "";
      const char *action = respDoc["action"] | "";
      if (identity[0] && action[0]) {
        const char *cmdId = respDoc["command_id"] | eventId.c_str();
        const char *personName = respDoc["person_name"] | "";
        const float confidence = respDoc["confidence"] | 0.0f;
        const bool authorized = respDoc["authorized"] | false;
        applyAccessDecision(cmdId, eventId.c_str(), identity, personName,
                            confidence, authorized, action);
      }
    }
  }

  return code == HTTP_CODE_OK || code == HTTP_CODE_ACCEPTED;
}

camera_fb_t *captureAndSubmit(const String &eventId, bool enrollOwner = false) {
  if (!cameraReady) return nullptr;
  camera_fb_t *frame = esp_camera_fb_get();
  if (!frame) {
    Serial.println("[camera] capture failed");
    return nullptr;
  }
  lastCaptureAt = millis();
  Serial.printf("[camera] captured event=%s, bytes=%u, %ux%u\n",
                eventId.c_str(), static_cast<unsigned>(frame->len), frame->width, frame->height);
  uploadForRecognition(frame, eventId, enrollOwner);
  return frame;
}

void handleRoot() {
  server.send(200, "text/html; charset=utf-8", ROOT_PAGE);
}

void handleStatus() {
  JsonDocument doc;
  doc["device_id"] = DEVICE_ID;
  doc["camera_ready"] = cameraReady;
  doc["door_state"] = doorOpen ? "OPEN" : "LOCKED";
  doc["servo_angle_deg"] = currentServoDeg;
  doc["last_event_id"] = lastEventId;
  doc["last_identity"] = lastIdentity;
  doc["last_person_name"] = lastPersonName;
  doc["last_confidence"] = lastConfidence;
  doc["mqtt_connected"] = mqtt.connected();
  String out;
  serializeJson(doc, out);
  server.send(200, "application/json", out);
}

void handleCapture() {
  camera_fb_t *frame = captureAndSubmit(makeCaptureEventId("capture"), false);
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

void handleEnroll() {
  const String eventId = makeCaptureEventId("enroll");
  camera_fb_t *frame = captureAndSubmit(eventId, true);
  if (!frame) {
    server.send(503, "text/plain; charset=utf-8", "Khong the chup anh de luu mau chu nha");
    return;
  }
  esp_camera_fb_return(frame);
  server.send(200, "text/plain; charset=utf-8",
              "Da chup va gui anh luu mau khuon mat chu nha (event=" + eventId + ")");
}

void setupWebServer() {
  server.on("/", HTTP_GET, handleRoot);
  server.on("/status", HTTP_GET, handleStatus);
  server.on("/capture", HTTP_GET, handleCapture);
  server.on("/enroll", HTTP_POST, handleEnroll);
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
  camera_fb_t *frame = captureAndSubmit(eventId, false);
  if (frame) esp_camera_fb_return(frame);
}
}  // namespace

void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.println("\n[boot] ESP32-CAM Face Access & SG90 Door Firmware 1.1.0 (AI Thinker)");
  cameraReady = initializeCamera();

  // Khởi tạo Servo SG90 ở trạng thái đóng cửa (0 độ)
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

  const uint32_t now = millis();
  if (mqtt.connected() && now - lastStatusAt >= STATUS_INTERVAL_MS) {
    lastStatusAt = now;
    publishCameraStatus(true);
  }
  delay(2);
}
