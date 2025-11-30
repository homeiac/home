// LED Comet System for ESP32 Status Puck Pomodoro Timer
// Hardware: 5x WS2812 LEDs in ring around display (pin 48)
// Calibrated offset: 195 degrees from screen arc position

#include <Adafruit_NeoPixel.h>
#include <Arduino.h>

// Constants
const uint8_t LED_PIN = 48;
const uint8_t LED_NUM = 5;
const float LED_ANGLE_OFFSET = 195.0f;  // Calibrated physical offset
const float GAMMA = 2.2f;

// Comet trail brightness levels (gamma-corrected)
const float TRAIL_BRIGHTNESS[] = {1.0f, 0.4f, 0.15f, 0.05f};
const uint8_t TRAIL_LENGTH = 4;

// Pulse warning parameters
const float PULSE_MIN = 0.8f;
const float PULSE_MAX = 1.0f;
const float PULSE_PERIOD_MS = 2000.0f;

// Celebration parameters
const uint16_t RAINBOW_DURATION_MS = 1000;
const uint16_t RAINBOW_FRAME_MS = 16;  // ~60 FPS
const uint8_t RAINBOW_CYCLES = 3;

// NeoPixel instance
Adafruit_NeoPixel leds(LED_NUM, LED_PIN, NEO_GRB + NEO_KHZ800);

// State tracking
uint32_t currentBaseColor = 0;
uint32_t celebrationStartTime = 0;
bool celebrationActive = false;

// ============================================================================
// HELPER FUNCTIONS
// ============================================================================

/**
 * Apply gamma correction to a brightness value
 * @param value Linear brightness (0-255)
 * @return Gamma-corrected brightness (0-255)
 */
uint8_t applyGamma(uint8_t value) {
  float normalized = value / 255.0f;
  float corrected = pow(normalized, GAMMA);
  return (uint8_t)(corrected * 255.0f);
}

/**
 * Linear interpolation between two colors
 * @param c1 Start color (0xRRGGBB)
 * @param c2 End color (0xRRGGBB)
 * @param t Interpolation factor (0.0 to 1.0)
 * @return Interpolated color (0xRRGGBB)
 */
uint32_t lerpColor(uint32_t c1, uint32_t c2, float t) {
  // Clamp t to valid range
  if (t < 0.0f) t = 0.0f;
  if (t > 1.0f) t = 1.0f;

  // Extract RGB components
  uint8_t r1 = (c1 >> 16) & 0xFF;
  uint8_t g1 = (c1 >> 8) & 0xFF;
  uint8_t b1 = c1 & 0xFF;

  uint8_t r2 = (c2 >> 16) & 0xFF;
  uint8_t g2 = (c2 >> 8) & 0xFF;
  uint8_t b2 = c2 & 0xFF;

  // Interpolate each component
  uint8_t r = r1 + (uint8_t)((r2 - r1) * t);
  uint8_t g = g1 + (uint8_t)((g2 - g1) * t);
  uint8_t b = b1 + (uint8_t)((b2 - b1) * t);

  return ((uint32_t)r << 16) | ((uint32_t)g << 8) | b;
}

/**
 * Scale a color by brightness factor
 * @param color Base color (0xRRGGBB)
 * @param brightness Scale factor (0.0 to 1.0)
 * @return Scaled color (0xRRGGBB)
 */
uint32_t scaleColor(uint32_t color, float brightness) {
  uint8_t r = ((color >> 16) & 0xFF) * brightness;
  uint8_t g = ((color >> 8) & 0xFF) * brightness;
  uint8_t b = (color & 0xFF) * brightness;

  return ((uint32_t)r << 16) | ((uint32_t)g << 8) | b;
}

/**
 * Convert progress to LED position with calibration offset
 * @param progress Arc progress (0.0 to 1.0)
 * @return LED floating-point position (0.0 to 5.0)
 */
float progressToLedPosition(float progress) {
  // Convert progress to angle (0-360 degrees)
  float arcAngle = progress * 360.0f;

  // Apply calibration offset and normalize
  float ledAngle = fmod(arcAngle + LED_ANGLE_OFFSET, 360.0f);

  // Convert to LED position (0.0 to 5.0)
  // Reverse direction to match physical LED arrangement
  float ledPos = (360.0f - ledAngle) / 72.0f;  // 72° per LED

  return fmod(ledPos, (float)LED_NUM);
}

// ============================================================================
// MAIN LED FUNCTIONS
// ============================================================================

/**
 * Initialize LED system
 */
void initLeds() {
  leds.begin();
  leds.setBrightness(255);  // Max brightness, we'll control via color scaling
  leds.clear();
  leds.show();
}

/**
 * Set base color for comet (called when state changes)
 * @param color Base color (0xRRGGBB)
 */
void setLedColor(uint32_t color) {
  currentBaseColor = color;
}

/**
 * Update LED comet effect to follow arc progress
 * @param progress Arc progress (0.0 to 1.0)
 * @param color Base color for comet (0xRRGGBB)
 */
void updateLedComet(float progress, uint32_t color) {
  // Check if celebration is active
  if (celebrationActive) {
    return;  // Celebration handles its own rendering
  }

  // Calculate LED position
  float ledPos = progressToLedPosition(progress);
  int leadLed = (int)ledPos;
  float fracPart = ledPos - leadLed;

  // Clear all LEDs first
  leds.clear();

  // Render comet with smooth interpolation
  for (int i = 0; i < TRAIL_LENGTH; i++) {
    int ledIndex = (leadLed - i + LED_NUM) % LED_NUM;

    // Calculate brightness for this trail position
    float brightness = TRAIL_BRIGHTNESS[i];

    // Apply smooth interpolation for lead LED
    if (i == 0) {
      // Lead LED gets interpolated brightness between full and first trail
      float interpBrightness = TRAIL_BRIGHTNESS[0] +
                               (TRAIL_BRIGHTNESS[1] - TRAIL_BRIGHTNESS[0]) * fracPart;
      brightness = interpBrightness;
    } else if (i == 1) {
      // Second LED gets inverse interpolation
      float interpBrightness = TRAIL_BRIGHTNESS[1] +
                               (TRAIL_BRIGHTNESS[0] - TRAIL_BRIGHTNESS[1]) * (1.0f - fracPart);
      brightness = interpBrightness;
    }

    // Apply gamma correction
    uint32_t ledColor = scaleColor(color, brightness);
    leds.setPixelColor(ledIndex, ledColor);
  }

  leds.show();
}

/**
 * Pulse warning effect for final 60 seconds (breathing)
 * @param progress Current timer progress (0.0 to 1.0)
 */
void pulseWarning(float progress) {
  // Calculate pulse brightness using sine wave
  float pulsePhase = (millis() % (uint32_t)PULSE_PERIOD_MS) / PULSE_PERIOD_MS;
  float pulseBrightness = PULSE_MIN + (PULSE_MAX - PULSE_MIN) *
                          (0.5f + 0.5f * sin(pulsePhase * 2.0f * PI));

  // Apply pulse to current color
  uint32_t pulsedColor = scaleColor(currentBaseColor, pulseBrightness);
  updateLedComet(progress, pulsedColor);
}

/**
 * Rainbow celebration effect (non-blocking, frame-based)
 * Call this once to start, then it auto-updates until complete
 */
void celebrationRainbow() {
  if (!celebrationActive) {
    // Start celebration
    celebrationActive = true;
    celebrationStartTime = millis();
  }

  uint32_t elapsed = millis() - celebrationStartTime;

  // Check if celebration is complete
  if (elapsed >= RAINBOW_DURATION_MS) {
    // Fade to rest color (cool white)
    celebrationActive = false;
    uint32_t restColor = 0xE0F0FF;  // Cool white RGB(224, 240, 255)

    // Smooth transition to rest color
    for (int i = 0; i < LED_NUM; i++) {
      leds.setPixelColor(i, restColor);
    }
    leds.show();
    return;
  }

  // Rainbow cascade effect
  float progress = (float)elapsed / RAINBOW_DURATION_MS;

  for (int i = 0; i < LED_NUM; i++) {
    // Calculate rainbow hue for this LED
    // Add spatial offset for cascade effect
    float hueOffset = (float)i / LED_NUM;
    float hue = fmod(progress * RAINBOW_CYCLES + hueOffset, 1.0f) * 65536.0f;

    uint32_t color = leds.ColorHSV((uint16_t)hue, 255, 255);
    leds.setPixelColor(i, color);
  }

  leds.show();
}

/**
 * Update LED system (call from main loop)
 * Handles celebration animation if active
 */
void updateLeds() {
  if (celebrationActive) {
    celebrationRainbow();
  }
}

// ============================================================================
// STATE-SPECIFIC COLOR DEFINITIONS
// ============================================================================

// Working state: Tomato red
const uint32_t COLOR_WORKING = 0xFF6347;  // RGB(255, 99, 71)

// Resting state: Cool white
const uint32_t COLOR_RESTING = 0xE0F0FF;  // RGB(224, 240, 255)
