#pragma once

// Wiring based on the supplied cluster 2 sketch.
constexpr int PIN_DHT = 4;
constexpr int PIN_LIGHT_OUTPUT = 2;
constexpr int PIN_FAN_RELAY = 5;
constexpr int PIN_LDR_ANALOG = 34;
constexpr int PIN_I2C_SDA = 22;
constexpr int PIN_I2C_SCL = 21;

constexpr bool DHT_IS_DHT22 = true;
constexpr bool RELAY_ACTIVE_HIGH = true;
constexpr int ANALOG_DARK_THRESHOLD = 2000;
constexpr float FAN_TEMP_ON_C = 30.0f;
constexpr float FAN_TEMP_OFF_C = 28.0f;
constexpr float FAN_HUMIDITY_ON_PCT = 40.0f;
constexpr float FAN_HUMIDITY_OFF_PCT = 45.0f;
