#include <Arduino.h>
#include <ArduinoJson.h>
#include <BH1750.h>
#include <DHT.h>
#include <PubSubClient.h>
#include <WiFi.h>
#include <Wire.h>

#include "pins.h"
#if __has_include("secrets.h")
#include "secrets.h"
#else
#include "secrets.example.h"
#endif

namespace {
constexpr uint32_t SAMPLE_INTERVAL_MS = 2000;
constexpr uint32_t WIFI_RETRY_MS = 10000;
constexpr uint32_t MQTT_RETRY_MS = 5000;
constexpr char DEVICE_ID[] = "esp32_cluster2";
constexpr char SENSOR_TOPIC[] = "smarthome/sensor/cluster2";
constexpr char COMMAND_TOPIC[] = "smarthome/device/cluster2/command";
constexpr char ACK_TOPIC[] = "smarthome/device/cluster2/ack";
constexpr char STATUS_TOPIC[] = "smarthome/device/cluster2/status";
constexpr char SYSTEM_TOPIC[] = "smarthome/system/cluster2/status";

DHT dht(PIN_DHT, DHT_IS_DHT22 ? DHT22 : DHT11);
BH1750 lightMeter;
bool bh1750Found = false;
bool lightOn = false;
bool fanOn = false;
String currentMode = "AUTO";

uint32_t lastSampleAt = 0;
uint32_t lastWiFiAttempt = 0;
uint32_t lastMqttAttempt = 0;
uint32_t messageSequence = 0;
WiFiClient networkClient;
PubSubClient mqtt(networkClient);

void writePin(int pin, bool enabled, bool activeHigh) {
  const bool pinHigh = activeHigh ? enabled : !enabled;
  digitalWrite(pin, pinHigh ? HIGH : LOW);
}

void setLight(bool enabled) {
  if (lightOn == enabled) return;
  lightOn = enabled;
  writePin(PIN_LIGHT_OUTPUT, enabled, LIGHT_ACTIVE_HIGH);
  Serial.printf("[light] %s (mode=%s, darkness threshold: ADC < %d)\n",
                enabled ? "ON" : "OFF", currentMode.c_str(), ANALOG_DARK_THRESHOLD);
}

void setFan(bool enabled) {
  if (fanOn == enabled) return;
  fanOn = enabled;
  writePin(PIN_FAN_RELAY, enabled, RELAY_ACTIVE_HIGH);
  Serial.printf("[fan] %s (mode=%s)\n", enabled ? "ON" : "OFF", currentMode.c_str());
}

void publishStatus() {
  if (!mqtt.connected()) return;
  JsonDocument doc;
  doc["schema_version"] = 1;
  doc["device_id"] = DEVICE_ID;
  doc["online"] = true;
  doc["mode"] = currentMode;
  doc["outputs"]["light"] = lightOn;
  doc["outputs"]["fan"] = fanOn;
  doc["firmware_version"] = "1.1.0";
  char payload[256];
  const size_t size = serializeJson(doc, payload, sizeof(payload));
  if (size && size < sizeof(payload)) {
    mqtt.publish(STATUS_TOPIC, payload, true);
  }
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
  doc["outputs"]["fan"] = fanOn;
  doc["timestamp_ms"] = millis();

  char payload[320];
  const size_t size = serializeJson(doc, payload, sizeof(payload));
  if (size && size < sizeof(payload)) {
    mqtt.publish(ACK_TOPIC, payload, false);
    Serial.printf("[ack] %s\n", payload);
  }
}

void publishTelemetry(int analogLight, bool isDark, float temperature,
                      float humidity, float lux) {
  if (!mqtt.connected()) return;
  JsonDocument doc;
  doc["schema_version"] = 1;
  char messageId[48];
  snprintf(messageId, sizeof(messageId), "cluster2_%08lx_%lu",
           (unsigned long)(ESP.getEfuseMac() & 0xffffffff),
           (unsigned long)++messageSequence);
  doc["message_id"] = messageId;
  doc["device_id"] = DEVICE_ID;
  doc["mode"] = currentMode;
  doc["timestamp_ms"] = millis();
  if (isfinite(temperature)) doc["temperature_c"] = temperature;
  else doc["temperature_c"] = nullptr;
  if (isfinite(humidity)) doc["humidity_pct"] = humidity;
  else doc["humidity_pct"] = nullptr;
  doc["light_adc"] = analogLight;
  if (isfinite(lux) && lux >= 0) doc["light_lux"] = lux;
  else doc["light_lux"] = nullptr;
  doc["is_dark"] = isDark;
  doc["outputs"]["light"] = lightOn;
  doc["outputs"]["fan"] = fanOn;

  char payload[384];
  const size_t size = serializeJson(doc, payload, sizeof(payload));
  if (size && size < sizeof(payload)) {
    if (mqtt.publish(SENSOR_TOPIC, payload, false)) {
      Serial.printf("[mqtt] %s\n", payload);
    } else {
      Serial.println("[mqtt] telemetry publish failed");
    }
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
      strcmp(target, "light_2") != 0 &&
      strcmp(target, "light_1") != 0 &&
      strcmp(target, "fan_1") != 0) {
    publishAck(commandId, false, "UNKNOWN_DEVICE");
    return;
  }

  const char *mode = doc["mode"] | currentMode.c_str();
  if (strcmp(mode, "AUTO") != 0 && strcmp(mode, "MANUAL") != 0) {
    publishAck(commandId, false, "INVALID_MODE");
    return;
  }

  bool nextLight = lightOn;
  bool nextFan = fanOn;
  bool hasOutputChange = false;

  if (doc["outputs"].is<JsonObjectConst>()) {
    JsonObjectConst req = doc["outputs"].as<JsonObjectConst>();
    if (req["light"].is<bool>()) {
      nextLight = req["light"].as<bool>();
      hasOutputChange = true;
    }
    if (req["fan"].is<bool>()) {
      nextFan = req["fan"].as<bool>();
      hasOutputChange = true;
    }
  } else if (doc["state"].is<const char *>()) {
    const char *state = doc["state"];
    if (strcmp(state, "ON") == 0 || strcmp(state, "OFF") == 0) {
      const bool enabled = (strcmp(state, "ON") == 0);
      if (strcmp(target, "light_2") == 0 || strcmp(target, "light_1") == 0) {
        nextLight = enabled;
        hasOutputChange = true;
      } else if (strcmp(target, "fan_1") == 0) {
        nextFan = enabled;
        hasOutputChange = true;
      } else {
        publishAck(commandId, false, "DEVICE_REQUIRED");
        return;
      }
    } else {
      publishAck(commandId, false, "INVALID_STATE");
      return;
    }
  }

  currentMode = mode;
  if (hasOutputChange) {
    setLight(nextLight);
    setFan(nextFan);
  }

  publishAck(commandId, true, nullptr);
  publishStatus();
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
  const char *will = "{\"schema_version\":1,\"device_id\":\"esp32_cluster2\",\"online\":false}";
  const bool connected = MQTT_USERNAME[0]
      ? mqtt.connect(DEVICE_ID, MQTT_USERNAME, MQTT_PASSWORD, SYSTEM_TOPIC, 1, true, will)
      : mqtt.connect(DEVICE_ID, SYSTEM_TOPIC, 1, true, will);
  if (!connected) {
    Serial.printf("[mqtt] connect failed: %d\n", mqtt.state());
    return;
  }
  mqtt.subscribe(COMMAND_TOPIC, 1);
  mqtt.publish(SYSTEM_TOPIC,
      "{\"schema_version\":1,\"device_id\":\"esp32_cluster2\",\"online\":true,\"firmware_version\":\"1.1.0\"}", true);
  publishStatus();
  Serial.println("[mqtt] connected & subscribed to command topic");
}

void sampleAndControl() {
  const int analogLight = analogRead(PIN_LDR_ANALOG);
  float lux = NAN;
  if (bh1750Found) {
    lux = lightMeter.readLightLevel();
  }

  // Xác định trời tối / trời sáng:
  // - Mặc định dùng giá trị analog LDR (< ANALOG_DARK_THRESHOLD là trời tối)
  // - Nếu BH1750 có kết nối và đọc hợp lệ trong khi LDR không nối (ADC == 0), hỗ trợ đánh giá theo lux
  bool isDark = (analogLight < ANALOG_DARK_THRESHOLD);
  if (bh1750Found && isfinite(lux) && lux >= 0 && analogLight == 0) {
    isDark = (lux < LUX_DARK_THRESHOLD);
  }

  // Kịch bản tự động cho đèn: trời tối -> bật đèn, trời sáng -> tắt đèn
  if (currentMode == "AUTO") {
    setLight(isDark);
  }

  const float temperature = dht.readTemperature();
  const float humidity = dht.readHumidity();

  Serial.printf("[light sensor] LDR ADC=%d, dark=%s, BH1750=",
                analogLight, isDark ? "yes" : "no");
  if (bh1750Found && isfinite(lux) && lux >= 0) Serial.printf("%.1f lx\n", lux);
  else if (bh1750Found) Serial.println("read error");
  else Serial.println("not detected");

  if (!isfinite(temperature) || !isfinite(humidity)) {
    Serial.println("[DHT] read error; fan state unchanged");
    publishTelemetry(analogLight, isDark, temperature, humidity, lux);
    publishStatus();
    return;
  }

  Serial.printf("[DHT] temperature=%.1f C, humidity=%.1f %%\n", temperature, humidity);

  // Kịch bản tự động cho quạt:
  // Nếu độ ẩm thấp (<= FAN_HUMIDITY_LOW_PCT) VÀ nhiệt độ cao (>= FAN_TEMP_HIGH_C) -> Bật quạt
  // Không thỏa điều kiện -> Tắt quạt
  if (currentMode == "AUTO") {
    const bool shouldTurnOnFan =
        (temperature >= FAN_TEMP_HIGH_C) && (humidity <= FAN_HUMIDITY_LOW_PCT);
    setFan(shouldTurnOnFan);
  }

  publishTelemetry(analogLight, isDark, temperature, humidity, lux);
  publishStatus();
}
}  // namespace

void setup() {
  Serial.begin(115200);
  delay(300);

  // Đưa thiết bị đầu ra (đèn, quạt) về trạng thái TẮT an toàn khi khởi động
  writePin(PIN_LIGHT_OUTPUT, false, LIGHT_ACTIVE_HIGH);
  writePin(PIN_FAN_RELAY, false, RELAY_ACTIVE_HIGH);
  pinMode(PIN_LIGHT_OUTPUT, OUTPUT);
  pinMode(PIN_FAN_RELAY, OUTPUT);
  pinMode(PIN_LDR_ANALOG, INPUT);

  analogReadResolution(12);
  dht.begin();
  Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL);
  bh1750Found = lightMeter.begin(BH1750::CONTINUOUS_HIGH_RES_MODE, 0x23, &Wire);

  WiFi.setAutoReconnect(true);
  WiFi.persistent(false);
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(mqttCallback);
  mqtt.setBufferSize(512);
  mqtt.setKeepAlive(30);

  Serial.println("\n[boot] Cluster 2 Environment & Light/Fan Automation Firmware 1.1.0");
  Serial.printf("[pins] DHT=GPIO%d, LDR=GPIO%d, I2C SDA/SCL=%d/%d, light=GPIO%d, fan relay=GPIO%d\n",
                PIN_DHT, PIN_LDR_ANALOG, PIN_I2C_SDA, PIN_I2C_SCL,
                PIN_LIGHT_OUTPUT, PIN_FAN_RELAY);
  Serial.printf("[BH1750] %s\n", bh1750Found ? "detected" : "not detected; using LDR ADC for light control");
  Serial.printf("[rules] dark ADC<%d -> Light ON else OFF; temp>=%.1f C AND humidity<=%.1f%% -> Fan ON else OFF\n",
                ANALOG_DARK_THRESHOLD, FAN_TEMP_HIGH_C, FAN_HUMIDITY_LOW_PCT);
  connectWiFi();
}

void loop() {
  connectWiFi();
  connectMqtt();
  if (mqtt.connected()) mqtt.loop();
  const uint32_t now = millis();
  if (now - lastSampleAt >= SAMPLE_INTERVAL_MS) {
    lastSampleAt = now;
    sampleAndControl();
  }
  delay(10);
}
