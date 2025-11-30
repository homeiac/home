# LED Comet System Integration Guide

## Hardware Setup
- **LEDs**: 5x WS2812 RGB LEDs in ring around display
- **Pin**: GPIO 48
- **Calibration**: 195° offset from screen arc position (already applied in code)

## Quick Start

### 1. Include and Initialize
```cpp
#include "led_comet.h"

void setup() {
  initLeds();  // Call once during setup
}
```

### 2. Main Loop Integration
```cpp
void loop() {
  // Update LED animations (handles celebration auto-update)
  updateLeds();

  // Your timer logic...
  float progress = calculateTimerProgress();  // 0.0 to 1.0

  // Update comet position based on timer state
  if (isWorking) {
    if (timeRemaining <= 60) {
      // Final minute: pulse warning
      pulseWarning(progress);
    } else {
      // Normal working: tomato red comet
      updateLedComet(progress, COLOR_WORKING);
    }
  } else {
    // Resting: cool white comet
    updateLedComet(progress, COLOR_RESTING);
  }
}
```

### 3. State Transitions
```cpp
// When work session completes
void onWorkComplete() {
  celebrationRainbow();  // Start rainbow burst
  // Celebration auto-completes after 1 second
}

// When switching states
void onStateChange(bool working) {
  if (working) {
    setLedColor(COLOR_WORKING);  // Tomato red
  } else {
    setLedColor(COLOR_RESTING);  // Cool white
  }
}
```

## API Reference

### Core Functions

#### `void initLeds()`
Initialize LED hardware. Call once in `setup()`.

#### `void updateLedComet(float progress, uint32_t color)`
Update comet position and color.
- **progress**: Timer progress (0.0 = start, 1.0 = complete)
- **color**: Base color in 0xRRGGBB format

Example:
```cpp
updateLedComet(0.75f, COLOR_WORKING);  // 75% complete, red comet
```

#### `void setLedColor(uint32_t color)`
Set base color for comet (called on state change).
```cpp
setLedColor(COLOR_WORKING);  // Switch to tomato red
```

#### `void updateLeds()`
Update LED animations. Call every frame in main loop.
Required for celebration rainbow animation.

### Special Effects

#### `void celebrationRainbow()`
Start 1-second rainbow cascade celebration.
- Non-blocking, frame-based animation
- Auto-fades to rest color (cool white)
- Call once to start, `updateLeds()` handles animation

Example:
```cpp
if (workSessionComplete) {
  celebrationRainbow();  // Start celebration
}
```

#### `void pulseWarning(float progress)`
Breathing effect for final 60 seconds.
- Oscillates brightness: 80% ↔ 100%
- 2-second cycle (slow breathing)
- Uses current base color

Example:
```cpp
if (timeRemaining <= 60 && isWorking) {
  pulseWarning(currentProgress);
}
```

### Helper Functions

#### `uint32_t lerpColor(uint32_t c1, uint32_t c2, float t)`
Linear interpolation between two colors.
```cpp
uint32_t transition = lerpColor(COLOR_WORKING, COLOR_RESTING, 0.5f);
```

#### `uint8_t applyGamma(uint8_t value)`
Apply gamma correction (γ=2.2) to brightness value.

## Color Constants

```cpp
const uint32_t COLOR_WORKING = 0xFF6347;  // Tomato red RGB(255, 99, 71)
const uint32_t COLOR_RESTING = 0xE0F0FF;  // Cool white RGB(224, 240, 255)
```

### Custom Colors
Create custom colors in 0xRRGGBB format:
```cpp
uint32_t customColor = 0xFF00FF;  // Magenta RGB(255, 0, 255)
updateLedComet(progress, customColor);
```

## Comet Effect Details

### Trail Configuration
- **Lead LED**: 100% brightness (position matches arc tip)
- **Trail**: 40%, 15%, 5% (gamma-corrected)
- **Smooth interpolation**: Sub-LED position accuracy

### Position Calculation
1. Arc progress (0.0-1.0) → angle (0-360°)
2. Apply 195° calibration offset
3. Map to LED ring (5 LEDs = 72° per LED)
4. Reverse direction for physical arrangement
5. Smooth interpolation between LEDs

## Performance Notes

- **Frame rate**: Designed for 60 FPS operation
- **Non-blocking**: All animations use frame-based updates
- **Memory**: Minimal state tracking (~20 bytes)
- **CPU**: Fast floating-point math, gamma lookup table

## Troubleshooting

### Comet position doesn't match arc
- Verify `LED_ANGLE_OFFSET = 195.0f` constant
- Check LED physical orientation (LED 0 position)

### Colors don't match screen
- Use exact color constants: `COLOR_WORKING`, `COLOR_RESTING`
- Verify NeoPixel color order: `NEO_GRB` (default for WS2812)

### Trail looks choppy
- Increase frame rate (call `updateLedComet()` more frequently)
- Verify smooth progress values (avoid jumps)

### Celebration doesn't auto-complete
- Ensure `updateLeds()` is called in main loop
- Check `celebrationActive` flag state

## Example: Complete Integration

```cpp
#include "led_comet.h"

// Timer state
float timerProgress = 0.0f;
bool isWorking = true;
uint32_t timeRemaining = 1500;  // 25 minutes in seconds

void setup() {
  initLeds();
  setLedColor(COLOR_WORKING);
}

void loop() {
  // Update animations
  updateLeds();

  // Update timer (your logic here)
  timerProgress = calculateProgress();
  timeRemaining = calculateTimeRemaining();

  // Handle LED effects based on state
  if (isWorking) {
    if (timeRemaining <= 60) {
      pulseWarning(timerProgress);
    } else {
      updateLedComet(timerProgress, COLOR_WORKING);
    }
  } else {
    updateLedComet(timerProgress, COLOR_RESTING);
  }

  // Check for work completion
  if (timerProgress >= 1.0f && isWorking) {
    celebrationRainbow();
    isWorking = false;
    setLedColor(COLOR_RESTING);
  }

  delay(16);  // ~60 FPS
}
```

## Technical Specifications

- **LED Type**: WS2812 RGB (NeoPixel compatible)
- **Control Protocol**: 800 KHz data rate
- **Color Depth**: 24-bit RGB (8 bits per channel)
- **Gamma Correction**: γ = 2.2 (perceptually linear brightness)
- **Update Rate**: 60 FPS capable
- **Animation Duration**: 1000ms rainbow celebration
- **Pulse Period**: 2000ms breathing cycle
