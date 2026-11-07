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
constexpr char STATUS_TOPIC[] = "smarthome/device/cluster2/status";
constexpr char SYSTEM_TOPIC[] = "smarthome/system/cluster2/status";

DHT dht(PIN_DHT, DHT_IS_DHT22 ? DHT22 : DHT11);
BH1750 lightMeter;
bool bh1750Found = false;
bool lightOn = false;
bool fanOn = false;
uint32_t lastSampleAt = 0;
uint32_t lastWiFiAttempt = 0;
uint32_t lastMqttAttempt = 0;
uint32_t messageSequence = 0;
WiFiClient networkClient;
PubSubClient mqtt(networkClient);

void publishStatus() {
  if (!mqtt.connected()) return;
  JsonDocument doc;
  doc["schema_version"] = 1;
  doc["device_id"] = DEVICE_ID;
  doc["online"] = true;
  doc["mode"] = "AUTO";
  doc["outputs"]["light"] = lightOn;
  doc["outputs"]["fan"] = fanOn;
  doc["firmware_version"] = "1.0.0";
  char payload[256];
  const size_t size = serializeJson(doc, payload, sizeof(payload));
  if (size && size < sizeof(payload)) mqtt.publish(STATUS_TOPIC, payload, true);
}

void publishTelemetry(int analogLight, bool isDark, float temperature,
                      float humidity, float lux) {
  if (!mqtt.connected()) return;
  JsonDocument doc;
  doc["schema_version"] = 1;
  char messageId[48];
  snprintf(messageId, sizeof(messageId), "cluster2_%08lx_%lu",
           (unsigned long)(ESP.getEfuseMac() & 0xffffffff), (unsigned long)++messageSequence);
  doc["message_id"] = messageId;
  doc["device_id"] = DEVICE_ID;
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
    if (mqtt.publish(SENSOR_TOPIC, payload, false)) Serial.printf("[mqtt] %s\n", payload);
    else Serial.println("[mqtt] telemetry publish failed");
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
  mqtt.publish(SYSTEM_TOPIC,
      "{\"schema_version\":1,\"device_id\":\"esp32_cluster2\",\"online\":true,\"firmware_version\":\"1.0.0\"}", true);
  publishStatus();
  Serial.println("[mqtt] connected");
}

void writeRelay(int pin, bool enabled) {
  const bool pinHigh = RELAY_ACTIVE_HIGH ? enabled : !enabled;
  digitalWrite(pin, pinHigh ? HIGH : LOW);
}

void setLight(bool enabled) {
  if (lightOn == enabled) return;
  lightOn = enabled;
  digitalWrite(PIN_LIGHT_OUTPUT, enabled ? HIGH : LOW);
  Serial.printf("[light] %s (darkness threshold: ADC < %d)\n",
                enabled ? "ON" : "OFF", ANALOG_DARK_THRESHOLD);
}

void setFan(bool enabled) {
  if (fanOn == enabled) return;
  fanOn = enabled;
  writeRelay(PIN_FAN_RELAY, enabled);
  Serial.printf("[fan] relay %s\n", enabled ? "ON" : "OFF");
}

void sampleAndControl() {
  const int analogLight = analogRead(PIN_LDR_ANALOG);
  const bool isDark = analogLight < ANALOG_DARK_THRESHOLD;
  setLight(isDark);

  const float temperature = dht.readTemperature();
  const float humidity = dht.readHumidity();
  float lux = NAN;
  if (bh1750Found) lux = lightMeter.readLightLevel();

  Serial.printf("[light sensor] LDR ADC=%d, dark=%s, BH1750=",
                analogLight, isDark ? "yes" : "no");
  if (bh1750Found && isfinite(lux) && lux >= 0) Serial.printf("%.1f lx\n", lux);
  else if (bh1750Found) Serial.println("read error");
  else Serial.println("not detected");

  if (!isfinite(temperature) || !isfinite(humidity)) {
    Serial.println("[DHT] read error; fan state unchanged");
    publishTelemetry(analogLight, isDark, temperature, humidity, lux);
    return;
  }

  Serial.printf("[DHT] temperature=%.1f C, humidity=%.1f %%\n", temperature, humidity);
  if (!fanOn && temperature >= FAN_TEMP_ON_C && humidity <= FAN_HUMIDITY_ON_PCT) {
    setFan(true);
  } else if (fanOn && (temperature <= FAN_TEMP_OFF_C || humidity >= FAN_HUMIDITY_OFF_PCT)) {
    setFan(false);
  }
  publishTelemetry(analogLight, isDark, temperature, humidity, lux);
  publishStatus();
}
}  // namespace

void setup() {
  Serial.begin(115200);
  delay(300);

  digitalWrite(PIN_LIGHT_OUTPUT, LOW);
  digitalWrite(PIN_FAN_RELAY, RELAY_ACTIVE_HIGH ? LOW : HIGH);
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
  mqtt.setBufferSize(512);
  mqtt.setKeepAlive(30);

  Serial.println("\n[boot] cluster 2 temperature + light + light/fan outputs test");
  Serial.printf("[pins] DHT=GPIO%d, LDR=GPIO%d, I2C SDA/SCL=%d/%d, light=GPIO%d, fan relay=GPIO%d\n",
                PIN_DHT, PIN_LDR_ANALOG, PIN_I2C_SDA, PIN_I2C_SCL,
                PIN_LIGHT_OUTPUT, PIN_FAN_RELAY);
  Serial.printf("[BH1750] %s\n", bh1750Found ? "detected" : "not detected; using LDR ADC for light control");
  Serial.printf("[thresholds] dark ADC<%d; fan ON if temp>=%.1f C AND humidity<=%.1f%%; fan OFF if temp<=%.1f C OR humidity>=%.1f%%\n",
                ANALOG_DARK_THRESHOLD, FAN_TEMP_ON_C, FAN_HUMIDITY_ON_PCT,
                FAN_TEMP_OFF_C, FAN_HUMIDITY_OFF_PCT);
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
