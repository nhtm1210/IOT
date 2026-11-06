#include <Arduino.h>
#include <ArduinoJson.h>
#include <BH1750.h>
#include <DHT.h>
#include <PubSubClient.h>
#include <WiFi.h>
#include <Wire.h>
#include <time.h>

#include "pins.h"

#if __has_include("secrets.h")
#include "secrets.h"
#else
#include "secrets.example.h"
#endif

namespace {
constexpr char DEVICE_ID[] = "esp32_sensor_01";
constexpr char SENSOR_TOPIC[] = "smarthome/sensor/node1";
constexpr char STATUS_TOPIC[] = "smarthome/system/node1/status";
constexpr char CLIENT_ID[] = "esp32_sensor_01";
constexpr uint32_t TELEMETRY_INTERVAL_MS = 5000;
constexpr uint32_t WIFI_RETRY_MS = 10000;
constexpr uint32_t MQTT_RETRY_MS = 5000;

WiFiClient networkClient;
PubSubClient mqtt(networkClient);
DHT dht(PIN_DHT, DHT22);
BH1750 lightSensor;
bool lightReady = false;
bool timeReady = false;
uint32_t lastTelemetry = 0;
uint32_t lastWiFiAttempt = 0;
uint32_t lastMqttAttempt = 0;
uint32_t sequenceNumber = 0;
bool previousPir1 = false;
bool previousPir2 = false;
bool previousDoor = false;

String timestampUtc() {
  struct tm timeInfo;
  if (!getLocalTime(&timeInfo, 0)) return "";
  char buffer[25];
  strftime(buffer, sizeof(buffer), "%Y-%m-%dT%H:%M:%SZ", &timeInfo);
  return String(buffer);
}

void publishNodeStatus(bool online) {
  JsonDocument doc;
  doc["schema_version"] = 1;
  doc["device_id"] = DEVICE_ID;
  doc["online"] = online;
  doc["firmware_version"] = "0.1.0";
  doc["ip"] = WiFi.isConnected() ? WiFi.localIP().toString() : "";
  const String timestamp = timestampUtc();
  if (timestamp.length()) doc["timestamp"] = timestamp;
  else doc["timestamp"] = nullptr;
  char payload[256];
  const size_t length = serializeJson(doc, payload, sizeof(payload));
  mqtt.publish(STATUS_TOPIC, payload, true);
  Serial.printf("[status] %s\n", payload);
}

void connectWiFi() {
  if (WiFi.isConnected()) return;
  const uint32_t now = millis();
  if (lastWiFiAttempt != 0 && now - lastWiFiAttempt < WIFI_RETRY_MS) return;
  lastWiFiAttempt = now;
  Serial.printf("[wifi] connecting to %s\n", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
}

void connectMqtt() {
  if (!WiFi.isConnected() || mqtt.connected()) return;
  const uint32_t now = millis();
  if (lastMqttAttempt != 0 && now - lastMqttAttempt < MQTT_RETRY_MS) return;
  lastMqttAttempt = now;
  const bool connected = MQTT_USERNAME[0]
      ? mqtt.connect(CLIENT_ID, MQTT_USERNAME, MQTT_PASSWORD,
                     STATUS_TOPIC, 1, true,
                     "{\"schema_version\":1,\"device_id\":\"esp32_sensor_01\",\"online\":false}")
      : mqtt.connect(CLIENT_ID, STATUS_TOPIC, 1, true,
                     "{\"schema_version\":1,\"device_id\":\"esp32_sensor_01\",\"online\":false}");
  if (connected) {
    Serial.println("[mqtt] connected");
    publishNodeStatus(true);
  } else {
    Serial.printf("[mqtt] connect failed, state=%d\n", mqtt.state());
  }
}

void publishTelemetry(bool pir1, bool pir2, bool doorOpen) {
  JsonDocument doc;
  doc["schema_version"] = 1;
  char messageId[48];
  snprintf(messageId, sizeof(messageId), "sensor_01_%08lx_%lu",
           (unsigned long)(ESP.getEfuseMac() & 0xffffffff),
           (unsigned long)++sequenceNumber);
  doc["message_id"] = messageId;
  doc["device_id"] = DEVICE_ID;
  const String timestamp = timestampUtc();
  if (timestamp.length()) doc["timestamp"] = timestamp;
  else doc["timestamp"] = nullptr;

  const float temperature = dht.readTemperature();
  const float humidity = dht.readHumidity();
  if (isfinite(temperature)) doc["temperature_c"] = temperature;
  else doc["temperature_c"] = nullptr;
  if (isfinite(humidity)) doc["humidity_pct"] = humidity;
  else doc["humidity_pct"] = nullptr;
  if (lightReady) {
    const float lux = lightSensor.readLightLevel();
    if (isfinite(lux) && lux >= 0) doc["light_lux"] = lux;
    else doc["light_lux"] = nullptr;
  } else {
    doc["light_lux"] = nullptr;
  }
  doc["pir_1"] = pir1;
  doc["pir_2"] = pir2;
  doc["door_open"] = doorOpen;

  char payload[384];
  const size_t length = serializeJson(doc, payload, sizeof(payload));
  if (length == 0 || length >= sizeof(payload)) {
    Serial.println("[mqtt] telemetry serialization failed");
    return;
  }
  Serial.printf("[read] %s\n", payload);
  if (!mqtt.connected()) return;
  if (mqtt.publish(SENSOR_TOPIC, payload, false)) {
    Serial.printf("[telemetry] %s\n", payload);
  } else {
    Serial.println("[mqtt] telemetry publish failed");
  }
}
}  // namespace

void setup() {
  Serial.begin(115200);
  delay(100);
  Serial.println("\n[boot] sensor node firmware 0.1.0");

  pinMode(PIN_PIR_1, INPUT);
  pinMode(PIN_PIR_2, INPUT);
  pinMode(PIN_DOOR, DOOR_USE_PULLUP ? INPUT_PULLUP : INPUT);
  dht.begin();
  Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL);
  lightReady = lightSensor.begin(BH1750::CONTINUOUS_HIGH_RES_MODE);
  Serial.printf("[sensor] BH1750 %s\n", lightReady ? "ready" : "not detected");

  WiFi.setAutoReconnect(true);
  WiFi.persistent(false);
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setBufferSize(512);
  mqtt.setKeepAlive(30);
  configTime(0, 0, "pool.ntp.org", "time.nist.gov");
  connectWiFi();
}

void loop() {
  connectWiFi();
  connectMqtt();
  if (mqtt.connected()) mqtt.loop();

  if (!timeReady && WiFi.isConnected()) {
    struct tm timeInfo;
    timeReady = getLocalTime(&timeInfo, 0);
  }

  const bool pir1 = digitalRead(PIN_PIR_1) == HIGH;
  const bool pir2 = digitalRead(PIN_PIR_2) == HIGH;
  const bool doorPinHigh = digitalRead(PIN_DOOR) == HIGH;
  const bool doorOpen = DOOR_OPEN_IS_HIGH ? doorPinHigh : !doorPinHigh;
  const uint32_t now = millis();
  const bool stateChanged = pir1 != previousPir1 || pir2 != previousPir2 || doorOpen != previousDoor;
  if (stateChanged || now - lastTelemetry >= TELEMETRY_INTERVAL_MS) {
    lastTelemetry = now;
    previousPir1 = pir1;
    previousPir2 = pir2;
    previousDoor = doorOpen;
    publishTelemetry(pir1, pir2, doorOpen);
  }
  delay(5);
}
