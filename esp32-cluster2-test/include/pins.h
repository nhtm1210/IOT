#pragma once

// Sơ đồ chân Cụm ESP32 2: Cảm biến nhiệt độ/độ ẩm DHT22 + Cảm biến ánh sáng + Đèn + Quạt
constexpr int PIN_DHT = 4;           // Cảm biến DHT22 (DATA)
constexpr int PIN_LIGHT_OUTPUT = 2;  // Đèn chiếu sáng (LED)
constexpr int PIN_FAN_RELAY = 5;     // Quạt 5V qua module Relay / MOSFET
constexpr int PIN_LDR_ANALOG = 34;   // Cảm biến ánh sáng LDR (Analog ADC)
constexpr int PIN_I2C_SDA = 22;      // BH1750 I2C SDA
constexpr int PIN_I2C_SCL = 21;      // BH1750 I2C SCL

constexpr bool DHT_IS_DHT22 = true;
constexpr bool LIGHT_ACTIVE_HIGH = true;
constexpr bool RELAY_ACTIVE_HIGH = true;

// Ngưỡng cảm biến ánh sáng:
// - Với LDR ADC: giá trị đọc < ANALOG_DARK_THRESHOLD được hiểu là trời tối -> bật đèn, ngược lại trời sáng -> tắt đèn
// - Với BH1750 (nếu dùng lux): lux < LUX_DARK_THRESHOLD là trời tối
constexpr int ANALOG_DARK_THRESHOLD = 2000;
constexpr float LUX_DARK_THRESHOLD = 50.0f;

// Ngưỡng điều khiển quạt tự động:
// Nhiệt độ cao (>= FAN_TEMP_HIGH_C) VÀ độ ẩm thấp (<= FAN_HUMIDITY_LOW_PCT) -> Bật quạt, ngược lại -> Tắt quạt
constexpr float FAN_TEMP_HIGH_C = 30.0f;
constexpr float FAN_HUMIDITY_LOW_PCT = 40.0f;

// Giữ alias tương thích ngược
constexpr float FAN_TEMP_ON_C = FAN_TEMP_HIGH_C;
constexpr float FAN_HUMIDITY_ON_PCT = FAN_HUMIDITY_LOW_PCT;
