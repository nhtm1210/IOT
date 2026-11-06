#include <Arduino.h>
#include "pins.h"

namespace {
constexpr uint32_t OUTPUT_HOLD_MS = 5000;

portMUX_TYPE motionMux = portMUX_INITIALIZER_UNLOCKED;
volatile uint32_t lastMotionAt = 0;
volatile bool motionPending = false;
bool outputsOn = false;

void ARDUINO_ISR_ATTR motionISR() {
  portENTER_CRITICAL_ISR(&motionMux);
  lastMotionAt = millis();
  motionPending = true;
  portEXIT_CRITICAL_ISR(&motionMux);
}

void setOutputs(bool enabled) {
  digitalWrite(PIN_LED, enabled ? HIGH : LOW);
  const bool buzzerHigh = BUZZER_ACTIVE_HIGH ? enabled : !enabled;
  digitalWrite(PIN_BUZZER, buzzerHigh ? HIGH : LOW);
  outputsOn = enabled;
  Serial.printf("[outputs] LED %s, buzzer %s\n",
                enabled ? "ON" : "OFF", enabled ? "ON" : "OFF");
}

bool takeMotion(uint32_t &triggerAt) {
  portENTER_CRITICAL(&motionMux);
  const bool triggered = motionPending;
  triggerAt = lastMotionAt;
  motionPending = false;
  portEXIT_CRITICAL(&motionMux);
  return triggered;
}
}  // namespace

void setup() {
  Serial.begin(115200);
  delay(200);

  // Set inactive output levels before enabling the GPIOs.
  digitalWrite(PIN_LED, LOW);
  digitalWrite(PIN_BUZZER, BUZZER_ACTIVE_HIGH ? LOW : HIGH);
  pinMode(PIN_LED, OUTPUT);
  pinMode(PIN_BUZZER, OUTPUT);
  pinMode(PIN_PIR, INPUT);
  attachInterrupt(digitalPinToInterrupt(PIN_PIR), motionISR, RISING);

  Serial.println("\n[boot] cluster 1 PIR + LED + buzzer test");
  Serial.printf("[pins] PIR=GPIO%d, LED=GPIO%d, buzzer=GPIO%d\n",
                PIN_PIR, PIN_LED, PIN_BUZZER);
  Serial.println("[ready] Motion turns LED and buzzer on; they turn off 5 seconds after the latest trigger.");
}

void loop() {
  uint32_t triggerAt = 0;
  if (takeMotion(triggerAt)) {
    Serial.println("[pir] MOTION DETECTED");
    if (!outputsOn) setOutputs(true);
  }

  if (outputsOn) {
    const uint32_t elapsed = static_cast<uint32_t>(millis() - triggerAt);
    if (elapsed >= OUTPUT_HOLD_MS) {
      // Recheck under the same lock so a new interrupt extends the hold time.
      portENTER_CRITICAL(&motionMux);
      triggerAt = lastMotionAt;
      const bool newMotion = motionPending;
      motionPending = false;
      portEXIT_CRITICAL(&motionMux);
      if (!newMotion && static_cast<uint32_t>(millis() - triggerAt) >= OUTPUT_HOLD_MS) {
        Serial.println("[pir] CLEAR - no new motion for 5 seconds");
        setOutputs(false);
      } else if (newMotion) {
        Serial.println("[pir] MOTION DETECTED");
      }
    }
  }
  delay(5);
}
