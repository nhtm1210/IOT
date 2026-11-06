#pragma once

// GPIOs from the project overview. Verify these against the assembled board.
constexpr int PIN_I2C_SDA = 21;
constexpr int PIN_I2C_SCL = 22;
constexpr int PIN_DOOR = 25;
constexpr int PIN_DHT = 27;
constexpr int PIN_PIR_1 = 32;
constexpr int PIN_PIR_2 = 33;

// MC-38 contact connected between GPIO and GND: LOW=closed, HIGH=open.
constexpr bool DOOR_USE_PULLUP = true;
constexpr bool DOOR_OPEN_IS_HIGH = true;
