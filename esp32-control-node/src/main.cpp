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
constexpr char DEVICE_ID[] = "esp32_control_01";
constexpr char COMMAND_TOPIC[] = "smarthome/device/node2/command";
constexpr char ACK_TOPIC[] = "smarthome/device/node2/ack";
constexpr char STATUS_TOPIC[] = "smarthome/device/node2/status";
constexpr char SYSTEM_TOPIC[] = "smarthome/system/node2/status";
constexpr char CLIENT_ID[] = "esp32_control_01";
constexpr uint32_t WIFI_RETRY_MS = 10000;
constexpr uint32_t MQTT_RETRY_MS = 5000;

struct Outputs {
  bool light = false;
  bool fan = false;
  bool buzzer = false;
} outputs;
String currentMode = "MANUAL";
WiFiClient networkClient;
PubSubClient mqtt(networkClient);
uint32_t lastWiFiAttempt = 0;
uint32_t lastMqttAttempt = 0;

void writeOutput(int pin, bool enabled) {
  const bool pinHigh = OUTPUT_ACTIVE_HIGH ? enabled : !enabled;
  digitalWrite(pin, pinHigh ? HIGH : LOW);
}

void applyOutputs() {
  writeOutput(PIN_LIGHT, outputs.light);
  writeOutput(PIN_FAN, outputs.fan);
  writeOutput(PIN_BUZZER, outputs.buzzer);
}

void addOutputs(JsonObject target) {
  target["light"] = outputs.light;
  target["fan"] = outputs.fan;
  target["buzzer"] = outputs.buzzer;
}

void publishStatus() {
  if (!mqtt.connected()) return;
  JsonDocument doc;
  doc["schema_version"] = 1;
  doc["device_id"] = DEVICE_ID;
  doc["online"] = true;
  doc["mode"] = currentMode;
  addOutputs(doc["outputs"].to<JsonObject>());
  doc["firmware_version"] = "0.1.0";
  char payload[320];
  const size_t length = serializeJson(doc, payload, sizeof(payload));
  if (length && length < sizeof(payload)) {
    mqtt.publish(STATUS_TOPIC, payload, true);
    Serial.printf("[status] %s\n", payload);
  }
}

void publishAck(const char *commandId, bool success, const char *error) {
  if (!mqtt.connected()) return;
  JsonDocument doc;
  doc["schema_version"] = 1;
  doc["command_id"] = commandId;
  doc["device_id"] = DEVICE_ID;
  doc["success"] = success;
  if (error && error[0]) doc["error"] = error;
  else doc["error"] = nullptr;
  addOutputs(doc["applied"].to<JsonObject>());
  char payload[320];
  const size_t length = serializeJson(doc, payload, sizeof(payload));
  if (length && length < sizeof(payload)) {
    mqtt.publish(ACK_TOPIC, payload, false);
    Serial.printf("[ack] %s\n", payload);
  }
}

bool parseBool(JsonVariantConst value, bool &out) {
  if (value.is<bool>()) {
    out = value.as<bool>();
    return true;
  }
  return false;
}

void handleCommand(const byte *payload, unsigned int length) {
  JsonDocument doc;
  const DeserializationError parseError = deserializeJson(doc, payload, length);
  const char *commandId = doc["command_id"] | "";
  if (parseError || !commandId[0]) {
    Serial.printf("[command] invalid JSON: %s\n", parseError.c_str());
    publishAck(commandId, false, "INVALID_COMMAND");
    return;
  }
  const int schemaVersion = doc["schema_version"] | 1;
  if (schemaVersion != 1) {
    publishAck(commandId, false, "UNSUPPORTED_SCHEMA");
    return;
  }
  const char *target = doc["device_id"] | "";
  if (strcmp(target, DEVICE_ID) != 0 && strcmp(target, "light_1") != 0 &&
      strcmp(target, "fan_1") != 0 && strcmp(target, "buzzer_1") != 0) {
    publishAck(commandId, false, "UNKNOWN_DEVICE");
    return;
  }

  Outputs next = outputs;
  bool valid = false;
  if (doc["outputs"].is<JsonObjectConst>()) {
    JsonObjectConst requested = doc["outputs"].as<JsonObjectConst>();
    valid = requested["light"].is<bool>() && requested["fan"].is<bool>() &&
            requested["buzzer"].is<bool>() &&
            parseBool(requested["light"], next.light) &&
            parseBool(requested["fan"], next.fan) &&
            parseBool(requested["buzzer"], next.buzzer);
  } else if (doc["state"].is<const char *>()) {
    const char *state = doc["state"];
    if (strcmp(state, "ON") == 0 || strcmp(state, "OFF") == 0) {
      const bool enabled = strcmp(state, "ON") == 0;
      if (strcmp(target, "light_1") == 0) next.light = enabled;
      else if (strcmp(target, "fan_1") == 0) next.fan = enabled;
      else if (strcmp(target, "buzzer_1") == 0) next.buzzer = enabled;
      else {
        publishAck(commandId, false, "DEVICE_REQUIRED");
        return;
      }
      valid = true;
    }
  }
  const char *mode = doc["mode"] | "MANUAL";
  if (strcmp(mode, "MANUAL") != 0 && strcmp(mode, "AUTO") != 0) valid = false;
  if (!valid) {
    publishAck(commandId, false, "INVALID_COMMAND");
    return;
  }

  // Commands represent desired state, so repeats never toggle an output.
  outputs = next;
  currentMode = mode;
  applyOutputs();
  publishAck(commandId, true, nullptr);
  publishStatus();
}

void mqttCallback(char *topic, byte *payload, unsigned int length) {
  if (strcmp(topic, COMMAND_TOPIC) == 0) handleCommand(payload, length);
}

void connectWiFi() {
  if (WiFi.isConnected()) return;
  const uint32_t now = millis();
  if (lastWiFiAttempt != 0 && now - lastWiFiAttempt < WIFI_RETRY_MS) return;
  lastWiFiAttempt = now;
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.printf("[wifi] connecting to %s\n", WIFI_SSID);
}

void connectMqtt() {
  if (!WiFi.isConnected() || mqtt.connected()) return;
  const uint32_t now = millis();
  if (lastMqttAttempt != 0 && now - lastMqttAttempt < MQTT_RETRY_MS) return;
  lastMqttAttempt = now;
  const char *will = "{\"schema_version\":1,\"device_id\":\"esp32_control_01\",\"online\":false}";
  const bool connected = MQTT_USERNAME[0]
      ? mqtt.connect(CLIENT_ID, MQTT_USERNAME, MQTT_PASSWORD, SYSTEM_TOPIC, 1, true, will)
      : mqtt.connect(CLIENT_ID, SYSTEM_TOPIC, 1, true, will);
  if (!connected) {
    Serial.printf("[mqtt] connect failed, state=%d\n", mqtt.state());
    return;
  }
  Serial.println("[mqtt] connected");
  mqtt.publish(SYSTEM_TOPIC,
      "{\"schema_version\":1,\"device_id\":\"esp32_control_01\",\"online\":true,\"firmware_version\":\"0.1.0\"}", true);
  if (!mqtt.subscribe(COMMAND_TOPIC, 1)) Serial.println("[mqtt] command subscribe failed");
  publishStatus();
}
}  // namespace

void setup() {
  Serial.begin(115200);
  delay(100);
  Serial.println("\n[boot] control node firmware 0.1.0");

  // Establish safe OFF levels before enabling the GPIO outputs.
  digitalWrite(PIN_LIGHT, OUTPUT_ACTIVE_HIGH ? LOW : HIGH);
  digitalWrite(PIN_FAN, OUTPUT_ACTIVE_HIGH ? LOW : HIGH);
  digitalWrite(PIN_BUZZER, OUTPUT_ACTIVE_HIGH ? LOW : HIGH);
  pinMode(PIN_LIGHT, OUTPUT);
  pinMode(PIN_FAN, OUTPUT);
  pinMode(PIN_BUZZER, OUTPUT);
  outputs = {};

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
  delay(5);
}
