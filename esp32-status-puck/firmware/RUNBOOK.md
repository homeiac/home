# ESP32 Status Puck Firmware Runbook

## Build & Flash

### Prerequisites
```bash
cd esp32-status-puck/firmware
source .venv/bin/activate
```

### Build Only
```bash
pio run
```

### Build and Flash
```bash
pio run -t upload
```

### If Flash Fails ("No serial data received")
1. Hold **BOOT** button
2. Press and release **RESET** while holding BOOT
3. Release BOOT
4. Retry flash command

### If Device Unresponsive After Flash
- **Hard power cycle**: Unplug and replug USB cable
- Reset button alone may not be enough

## Screen Saver / Ambient Mode

- Activates after 30 seconds of no interaction
- Display dims to 5% (not off - see gotcha below)
- LEDs turn off
- Wake by: encoder turn, button press, or touch
- 5-second grace period after boot before ambient mode can activate

### Gotcha: PWM Brightness 0 Breaks Recovery
Setting `setDisplayBrightness(0)` breaks the PWM channel - the display won't come back when you try to restore brightness. Use 5% minimum instead.

```cpp
// BAD - won't recover
setDisplayBrightness(0);

// GOOD - recovers fine
setDisplayBrightness(5);
```

## Hardware

- **Board**: Elecrow CrowPanel 1.28" ESP32-S3 Rotary Display
- **Display**: GC9A01 240x240 round LCD
- **Touch**: CST816D capacitive
- **LEDs**: 5x WS2812B (NeoPixel)
- **Input**: Rotary encoder with push button

### Pin Definitions
| Function | Pin |
|----------|-----|
| TFT SCLK | 10 |
| TFT MOSI | 11 |
| TFT DC | 3 |
| TFT CS | 9 |
| TFT RST | 14 |
| TFT Backlight | 46 |
| Touch SDA | 6 |
| Touch SCL | 7 |
| Encoder A | 45 |
| Encoder B | 42 |
| Encoder SW | 41 |
| LED Data | 48 |

## Apps

### Status App (default)
- Shows Claude Code sessions or Home Assistant status
- Rotate encoder to switch views
- Click to refresh

### Pomodoro App
- Long press to access app menu
- Select preset with encoder
- Click to start timer
- Double-click to reset
- Triple-click to toggle test mode (60x speed)
