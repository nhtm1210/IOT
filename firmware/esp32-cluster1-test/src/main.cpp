#include <Arduino.h>
#include <ArduinoJson.h>
#include <PubSubClient.h>
#include <WiFi.h>

#include "pins.h"
#if __has_include("secrets.h")
#include "secrets.h"
#else
#include "secrets.example.h"
#endif

namespace {
constexpr char DEVICE_ID[] = "esp32_cluster1";
constexpr char MOTION_TOPIC[] = "smarthome/security/motion";
constexpr char SENSOR_TOPIC[] = "smarthome/sensor/cluster1";
constexpr char COMMAND_TOPIC[] = "smarthome/device/cluster1/command";
constexpr char ACK_TOPIC[] = "smarthome/device/cluster1/ack";
constexpr char STATUS_TOPIC[] = "smarthome/device/cluster1/status";
constexpr char SYSTEM_TOPIC[] = "smarthome/system/cluster1/status";

constexpr uint32_t WIFI_RETRY_MS = 10000;
constexpr uint32_t MQTT_RETRY_MS = 5000;
constexpr uint32_t STATUS_INTERVAL_MS = 30000;
constexpr uint32_t MOTION_REPUBLISH_COOLDOWN_MS = 3000;

portMUX_TYPE motionMux = portMUX_INITIALIZER_UNLOCKED;
volatile uint32_t lastMotionAt = 0;
volatile bool motionPending = false;

bool lightOn = false;
bool buzzerOn = false;
bool motionActive = false;
uint32_t holdUntilMs = 0;
uint32_t lastMotionPublishAt = 0;
String currentMode = "AUTO";

uint32_t lastWiFiAttempt = 0;
uint32_t lastMqttAttempt = 0;
uint32_t lastStatusAt = 0;
uint32_t eventSequence = 0;

WiFiClient networkClient;
PubSubClient mqtt(networkClient);

void ARDUINO_ISR_ATTR motionISR() {
  portENTER_CRITICAL_ISR(&motionMux);
  lastMotionAt = millis();
  motionPending = true;
  portEXIT_CRITICAL_ISR(&motionMux);
}

void writePin(int pin, bool enabled, bool activeHigh) {
  const bool pinHigh = activeHigh ? enabled : !enabled;
  digitalWrite(pin, pinHigh ? HIGH : LOW);
}

void applyOutputs(bool nextLight, bool nextBuzzer) {
  const bool changed = (lightOn != nextLight) || (buzzerOn != nextBuzzer);
  lightOn = nextLight;
  buzzerOn = nextBuzzer;
  writePin(PIN_LED, lightOn, LED_ACTIVE_HIGH);
  writePin(PIN_BUZZER, buzzerOn, BUZZER_ACTIVE_HIGH);
  if (changed) {
    Serial.printf("[outputs] mode=%s light=%s buzzer=%s\n",
                  currentMode.c_str(),
                  lightOn ? "ON" : "OFF",
                  buzzerOn ? "ON" : "OFF");
  }
}

bool takeMotion(uint32_t &triggerAt) {
  portENTER_CRITICAL(&motionMux);
  const bool triggered = motionPending;
  triggerAt = lastMotionAt;
  motionPending = false;
  portEXIT_CRITICAL(&motionMux);
  return triggered;
}

void publishNodeStatus(bool online) {
  if (!mqtt.connected()) return;
  JsonDocument doc;
  doc["schema_version"] = 1;
  doc["device_id"] = DEVICE_ID;
  doc["online"] = online;
  doc["mode"] = currentMode;
  doc["pir"] = motionActive;
  doc["outputs"]["light"] = lightOn;
  doc["outputs"]["buzzer"] = buzzerOn;
  doc["firmware_version"] = "1.1.0";
  char payload[320];
  const size_t size = serializeJson(doc, payload, sizeof(payload));
  if (size && size < sizeof(payload)) {
    mqtt.publish(STATUS_TOPIC, payload, true);
  }
}

void publishMotionState(bool detected) {
  if (!mqtt.connected()) return;
  char eventId[48];
  snprintf(eventId, sizeof(eventId), "motion_%08lx_%lu",
           (unsigned long)(ESP.getEfuseMac() & 0xffffffff),
           (unsigned long)++eventSequence);

  JsonDocument event;
  event["schema_version"] = 1;
  event["event_id"] = eventId;
  event["device_id"] = DEVICE_ID;
  event["event_type"] = detected ? "MOTION_DETECTED" : "MOTION_CLEARED";
  event["pir"] = detected;
  event["outputs"]["light"] = lightOn;
  event["outputs"]["buzzer"] = buzzerOn;
  event["timestamp_ms"] = millis();

  char payload[320];
  const size_t size = serializeJson(event, payload, sizeof(payload));
  if (!size || size >= sizeof(payload)) return;

  if (detected) {
    mqtt.publish(MOTION_TOPIC, payload, false);
  }
  mqtt.publish(SENSOR_TOPIC, payload, false);
  Serial.printf("[mqtt] %s: %s\n", detected ? "motion detected" : "motion cleared", payload);
}

void publishAck(const char *commandId, bool success, const char *error) {
  if (!mqtt.connected()) return;
  JsonDocument doc;
  doc["schema_version"] = 1;
  doc["command_id"] = commandId;
  doc["device_id"] = DEVICE_ID;
  doc["mode"] = currentMode;
  doc["success"] = success;
  doc["error"] = (error && error[0]) ? error : nullptr;
  doc["outputs"]["light"] = lightOn;
  doc["outputs"]["buzzer"] = buzzerOn;
  doc["timestamp_ms"] = millis();

  char payload[320];
  const size_t size = serializeJson(doc, payload, sizeof(payload));
  if (size && size < sizeof(payload)) {
    mqtt.publish(ACK_TOPIC, payload, false);
    Serial.printf("[ack] %s\n", payload);
  }
}

void handleCommand(const byte *payload, unsigned int length) {
  JsonDocument doc;
  const DeserializationError parseError = deserializeJson(doc, payload, length);
  const char *commandId = doc["command_id"] | "";
  if (parseError || !commandId[0]) {
    publishAck(commandId, false, "INVALID_COMMAND");
    return;
  }

  const char *target = doc["device_id"] | DEVICE_ID;
  if (strcmp(target, DEVICE_ID) != 0 &&
      strcmp(target, "light_1") != 0 &&
      strcmp(target, "buzzer_1") != 0) {
    publishAck(commandId, false, "UNKNOWN_DEVICE");
    return;
  }

  const char *mode = doc["mode"] | currentMode.c_str();
  if (strcmp(mode, "AUTO") != 0 && strcmp(mode, "MANUAL") != 0) {
    publishAck(commandId, false, "INVALID_MODE");
    return;
  }

  bool nextLight = lightOn;
  bool nextBuzzer = buzzerOn;
  bool hasOutputChange = false;

  if (doc["outputs"].is<JsonObjectConst>()) {
    JsonObjectConst req = doc["outputs"].as<JsonObjectConst>();
    if (req["light"].is<bool>()) {
      nextLight = req["light"].as<bool>();
      hasOutputChange = true;
    }
    if (req["buzzer"].is<bool>()) {
      nextBuzzer = req["buzzer"].as<bool>();
      hasOutputChange = true;
    }
  } else if (doc["state"].is<const char *>()) {
    const char *state = doc["state"];
    if (strcmp(state, "ON") == 0 || strcmp(state, "OFF") == 0) {
      const bool enabled = (strcmp(state, "ON") == 0);
      if (strcmp(target, "light_1") == 0) {
        nextLight = enabled;
        hasOutputChange = true;
      } else if (strcmp(target, "buzzer_1") == 0) {
        nextBuzzer = enabled;
        hasOutputChange = true;
      } else {
        nextLight = enabled;
        nextBuzzer = enabled;
        hasOutputChange = true;
      }
    } else {
      publishAck(commandId, false, "INVALID_STATE");
      return;
    }
  }

  currentMode = mode;
  if (hasOutputChange) {
    applyOutputs(nextLight, nextBuzzer);
  } else if (currentMode == "AUTO" && !motionActive) {
    applyOutputs(false, false);
  }

  publishAck(commandId, true, nullptr);
  publishNodeStatus(true);
}

void mqttCallback(char *topic, byte *payload, unsigned int length) {
  if (strcmp(topic, COMMAND_TOPIC) == 0) {
    handleCommand(payload, length);
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
  const char *will = "{\"schema_version\":1,\"device_id\":\"esp32_cluster1\",\"online\":false}";
  const bool connected = MQTT_USERNAME[0]
      ? mqtt.connect(DEVICE_ID, MQTT_USERNAME, MQTT_PASSWORD, SYSTEM_TOPIC, 1, true, will)
      : mqtt.connect(DEVICE_ID, SYSTEM_TOPIC, 1, true, will);
  if (!connected) {
    Serial.printf("[mqtt] connect failed: %d\n", mqtt.state());
    return;
  }
  mqtt.subscribe(COMMAND_TOPIC, 1);
  mqtt.publish(SYSTEM_TOPIC,
      "{\"schema_version\":1,\"device_id\":\"esp32_cluster1\",\"online\":true,\"firmware_version\":\"1.1.0\"}", true);
  publishNodeStatus(true);
  Serial.println("[mqtt] connected & subscribed to command topic");
}
}  // namespace

void setup() {
  Serial.begin(115200);
  delay(200);

  // Đưa đèn và còi về trạng thái an toàn (TẮT) khi khởi động
  writePin(PIN_LED, false, LED_ACTIVE_HIGH);
  writePin(PIN_BUZZER, false, BUZZER_ACTIVE_HIGH);
  pinMode(PIN_LED, OUTPUT);
  pinMode(PIN_BUZZER, OUTPUT);
  pinMode(PIN_PIR, INPUT);
  attachInterrupt(digitalPinToInterrupt(PIN_PIR), motionISR, RISING);

  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(mqttCallback);
  mqtt.setBufferSize(512);
  mqtt.setKeepAlive(30);

  Serial.println("\n[boot] Cluster 1 Motion Alarm Firmware 1.1.0");
  Serial.printf("[pins] PIR=%d light=%d buzzer=%d hold_ms=%lu\n",
                PIN_PIR, PIN_LED, PIN_BUZZER, (unsigned long)OUTPUT_HOLD_MS);
  connectWiFi();
}

void loop() {
  connectWiFi();
  connectMqtt();
  if (mqtt.connected()) mqtt.loop();

  const uint32_t now = millis();
  uint32_t triggerAt = 0;
  const bool isrTriggered = takeMotion(triggerAt);
  const bool pirPinHigh = (digitalRead(PIN_PIR) == HIGH);

  // Khi phát hiện chuyển động (từ ngắt RISING hoặc chân PIR đang ở mức HIGH)
  if (isrTriggered || pirPinHigh) {
    holdUntilMs = now + OUTPUT_HOLD_MS;
    const bool firstTrigger = !motionActive;
    motionActive = true;

    if (currentMode == "AUTO") {
      applyOutputs(true, true);
    }

    if (firstTrigger || isrTriggered ||
        (now - lastMotionPublishAt >= MOTION_REPUBLISH_COOLDOWN_MS)) {
      lastMotionPublishAt = now;
      Serial.println("[pir] MOTION DETECTED -> Light ON, Buzzer ON");
      publishMotionState(true);
      publishNodeStatus(true);
    }
  } else if (motionActive && static_cast<int32_t>(now - holdUntilMs) >= 0) {
    // Hết chuyển động và đã qua thời gian giữ OUTPUT_HOLD_MS
    motionActive = false;
    Serial.println("[pir] MOTION CLEARED -> Light OFF, Buzzer OFF");
    if (currentMode == "AUTO") {
      applyOutputs(false, false);
    }
    publishMotionState(false);
    publishNodeStatus(true);
  }

  if (mqtt.connected() && now - lastStatusAt >= STATUS_INTERVAL_MS) {
    lastStatusAt = now;
    publishNodeStatus(true);
  }
  delay(5);
}
