#pragma once

// Suggested ESP32 DevKit wiring. Confirm/change to match the assembled circuit.
constexpr int PIN_LIGHT = 18;
constexpr int PIN_FAN = 19;     // MOSFET gate/input, never drive fan directly.
constexpr int PIN_BUZZER = 23;

// Set false for active-low relay/MOSFET/buzzer modules.
constexpr bool OUTPUT_ACTIVE_HIGH = true;
