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
constexpr char STATUS_TOPIC[] = "smarthome/device/cluster1/status";
constexpr char SYSTEM_TOPIC[] = "smarthome/system/cluster1/status";
constexpr uint32_t OUTPUT_HOLD_MS = 5000;
constexpr uint32_t WIFI_RETRY_MS = 10000;
constexpr uint32_t MQTT_RETRY_MS = 5000;
constexpr uint32_t STATUS_INTERVAL_MS = 30000;

portMUX_TYPE motionMux = portMUX_INITIALIZER_UNLOCKED;
volatile uint32_t lastMotionAt = 0;
volatile bool motionPending = false;
bool outputsOn = false;
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

void setOutputs(bool enabled) {
  digitalWrite(PIN_LED, enabled ? HIGH : LOW);
  digitalWrite(PIN_BUZZER, (BUZZER_ACTIVE_HIGH ? enabled : !enabled) ? HIGH : LOW);
  outputsOn = enabled;
  Serial.printf("[outputs] light=%s buzzer=%s\n", enabled ? "ON" : "OFF", enabled ? "ON" : "OFF");
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
  doc["firmware_version"] = "1.0.0";
  doc["outputs"]["light"] = outputsOn;
  doc["outputs"]["buzzer"] = outputsOn;
  char payload[256];
  const size_t size = serializeJson(doc, payload, sizeof(payload));
  if (size && size < sizeof(payload)) mqtt.publish(STATUS_TOPIC, payload, true);
}

void publishMotionEvent() {
  if (!mqtt.connected()) return;
  char eventId[48];
  snprintf(eventId, sizeof(eventId), "motion_%08lx_%lu",
           (unsigned long)(ESP.getEfuseMac() & 0xffffffff), (unsigned long)++eventSequence);

  JsonDocument event;
  event["schema_version"] = 1;
  event["event_id"] = eventId;
  event["device_id"] = DEVICE_ID;
  event["event_type"] = "MOTION_DETECTED";
  event["pir"] = true;
  event["timestamp_ms"] = millis();
  char payload[256];
  const size_t size = serializeJson(event, payload, sizeof(payload));
  if (!size || size >= sizeof(payload)) return;

  mqtt.publish(MOTION_TOPIC, payload, false);
  mqtt.publish(SENSOR_TOPIC, payload, false);
  Serial.printf("[mqtt] motion event: %s\n", payload);
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
  mqtt.publish(SYSTEM_TOPIC,
      "{\"schema_version\":1,\"device_id\":\"esp32_cluster1\",\"online\":true,\"firmware_version\":\"1.0.0\"}", true);
  publishNodeStatus(true);
  Serial.println("[mqtt] connected");
}
}  // namespace

void setup() {
  Serial.begin(115200);
  delay(200);
  digitalWrite(PIN_LED, LOW);
  digitalWrite(PIN_BUZZER, BUZZER_ACTIVE_HIGH ? LOW : HIGH);
  pinMode(PIN_LED, OUTPUT);
  pinMode(PIN_BUZZER, OUTPUT);
  pinMode(PIN_PIR, INPUT);
  attachInterrupt(digitalPinToInterrupt(PIN_PIR), motionISR, RISING);

  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setBufferSize(512);
  mqtt.setKeepAlive(30);
  Serial.println("\n[boot] cluster 1 motion alarm firmware 1.0.0");
  Serial.printf("[pins] PIR=%d light=%d buzzer=%d\n", PIN_PIR, PIN_LED, PIN_BUZZER);
  connectWiFi();
}

void loop() {
  connectWiFi();
  connectMqtt();
  if (mqtt.connected()) mqtt.loop();

  uint32_t triggerAt = 0;
  if (takeMotion(triggerAt)) {
    Serial.println("[pir] MOTION DETECTED");
    setOutputs(true);
    publishMotionEvent();
  }

  if (outputsOn && static_cast<uint32_t>(millis() - triggerAt) >= OUTPUT_HOLD_MS) {
    portENTER_CRITICAL(&motionMux);
    triggerAt = lastMotionAt;
    const bool newMotion = motionPending;
    motionPending = false;
    portEXIT_CRITICAL(&motionMux);
    if (!newMotion && static_cast<uint32_t>(millis() - triggerAt) >= OUTPUT_HOLD_MS) {
      setOutputs(false);
      publishNodeStatus(true);
    }
  }

  if (mqtt.connected() && millis() - lastStatusAt >= STATUS_INTERVAL_MS) {
    lastStatusAt = millis();
    publishNodeStatus(true);
  }
  delay(5);
}
