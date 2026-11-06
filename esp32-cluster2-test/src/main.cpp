#include <Arduino.h>
#include <BH1750.h>
#include <DHT.h>
#include <Wire.h>

#include "pins.h"

namespace {
constexpr uint32_t SAMPLE_INTERVAL_MS = 2000;

DHT dht(PIN_DHT, DHT_IS_DHT22 ? DHT22 : DHT11);
BH1750 lightMeter;
bool bh1750Found = false;
bool lightOn = false;
bool fanOn = false;
uint32_t lastSampleAt = 0;

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
    return;
  }

  Serial.printf("[DHT] temperature=%.1f C, humidity=%.1f %%\n", temperature, humidity);
  if (!fanOn && temperature >= FAN_TEMP_ON_C && humidity <= FAN_HUMIDITY_ON_PCT) {
    setFan(true);
  } else if (fanOn && (temperature <= FAN_TEMP_OFF_C || humidity >= FAN_HUMIDITY_OFF_PCT)) {
    setFan(false);
  }
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

  Serial.println("\n[boot] cluster 2 temperature + light + light/fan outputs test");
  Serial.printf("[pins] DHT=GPIO%d, LDR=GPIO%d, I2C SDA/SCL=%d/%d, light=GPIO%d, fan relay=GPIO%d\n",
                PIN_DHT, PIN_LDR_ANALOG, PIN_I2C_SDA, PIN_I2C_SCL,
                PIN_LIGHT_OUTPUT, PIN_FAN_RELAY);
  Serial.printf("[BH1750] %s\n", bh1750Found ? "detected" : "not detected; using LDR ADC for light control");
  Serial.printf("[thresholds] dark ADC<%d; fan ON if temp>=%.1f C AND humidity<=%.1f%%; fan OFF if temp<=%.1f C OR humidity>=%.1f%%\n",
                ANALOG_DARK_THRESHOLD, FAN_TEMP_ON_C, FAN_HUMIDITY_ON_PCT,
                FAN_TEMP_OFF_C, FAN_HUMIDITY_OFF_PCT);
}

void loop() {
  const uint32_t now = millis();
  if (now - lastSampleAt >= SAMPLE_INTERVAL_MS) {
    lastSampleAt = now;
    sampleAndControl();
  }
  delay(10);
}
