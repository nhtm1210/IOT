#pragma once

// Sơ đồ chân chuẩn cho bo mạch AI Thinker ESP32-CAM (Camera OV2640)
constexpr int PWDN_GPIO_NUM = 32;
constexpr int RESET_GPIO_NUM = -1;
constexpr int XCLK_GPIO_NUM = 0;
constexpr int SIOD_GPIO_NUM = 26;
constexpr int SIOC_GPIO_NUM = 27;
constexpr int Y9_GPIO_NUM = 35;
constexpr int Y8_GPIO_NUM = 34;
constexpr int Y7_GPIO_NUM = 39;
constexpr int Y6_GPIO_NUM = 36;
constexpr int Y5_GPIO_NUM = 21;
constexpr int Y4_GPIO_NUM = 19;
constexpr int Y3_GPIO_NUM = 18;
constexpr int Y2_GPIO_NUM = 5;
constexpr int VSYNC_GPIO_NUM = 25;
constexpr int HREF_GPIO_NUM = 23;
constexpr int PCLK_GPIO_NUM = 22;

// Đèn Flash tích hợp trên ESP32-CAM
constexpr int FLASH_LED_PIN = 4;

// Động cơ Servo SG90 điều khiển đóng/mở cửa
// Chân GPIO13 trống trên AI Thinker ESP32-CAM khi không dùng thẻ nhớ SD
constexpr int SERVO_PIN = 13;
constexpr int DOOR_CLOSED_DEG = 0;     // Góc đóng/khóa cửa (không quay)
constexpr int DOOR_OPEN_DEG = 90;      // Góc quay mở cửa khi khớp mặt chủ nhà
constexpr uint32_t DOOR_OPEN_MS = 5000; // Thời gian giữ cửa mở trước khi tự đóng lại (5 giây)
