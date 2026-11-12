#pragma once

// Sơ đồ chân Cụm ESP32 1: Cảm biến chuyển động PIR + Đèn + Còi báo động
constexpr int PIN_PIR = 27;     // Cảm biến chuyển động PIR (HC-SR501 OUT)
constexpr int PIN_LED = 26;     // Đèn LED chiếu sáng / cảnh báo
constexpr int PIN_BUZZER = 25;  // Còi báo động Active Buzzer

// Mức kích hoạt thiết bị đầu ra (đặt false nếu module kích mức LOW)
constexpr bool LED_ACTIVE_HIGH = true;
constexpr bool BUZZER_ACTIVE_HIGH = true;

// Thời gian giữ đèn sáng và còi kêu sau khi hết chuyển động (ms)
constexpr uint32_t OUTPUT_HOLD_MS = 5000;
