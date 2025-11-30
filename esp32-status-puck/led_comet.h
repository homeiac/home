// LED Comet System Header for ESP32 Status Puck
// Hardware: 5x WS2812 LEDs in ring around display

#ifndef LED_COMET_H
#define LED_COMET_H

#include <Arduino.h>

// State color definitions
extern const uint32_t COLOR_WORKING;  // Tomato red RGB(255, 99, 71)
extern const uint32_t COLOR_RESTING;  // Cool white RGB(224, 240, 255)

// Initialization
void initLeds();

// Main update functions
void updateLedComet(float progress, uint32_t color);
void setLedColor(uint32_t color);
void updateLeds();  // Call from main loop for animations

// Special effects
void celebrationRainbow();           // Start 1-second rainbow burst
void pulseWarning(float progress);   // Breathing effect for final minute

// Helper functions
uint8_t applyGamma(uint8_t value);
uint32_t lerpColor(uint32_t c1, uint32_t c2, float t);

#endif  // LED_COMET_H
