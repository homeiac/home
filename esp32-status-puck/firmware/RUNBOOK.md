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
Setting `ledcWrite(PWM_CHANNEL, 0)` breaks the PWM channel - the display won't come back. Current workaround uses 5% minimum.

```cpp
// BAD - won't recover
setDisplayBrightness(0);

// CURRENT WORKAROUND - recovers fine
setDisplayBrightness(5);
```

### Proper Fix (TODO)
The correct approach is to use the GC9A01's native sleep commands via LovyanGFX:

```cpp
// Sleep - sends SLPIN (0x10) to display controller
gfx.getPanel()->setSleep(true);

// Wake - sends SLPOUT (0x11), needs 120ms delay
gfx.getPanel()->setSleep(false);
delay(120);
```

This puts the display controller itself to sleep (µA range) instead of just dimming the backlight.

**Power consumption comparison:**
| Mode | Current |
|------|---------|
| Display awake | 10-20mA |
| Display sleep | µA |
| Backlight on | +30-40mA |

**References:**
- [GC9A01 Datasheet](https://www.buydisplay.com/download/ic/GC9A01A.pdf)
- [LovyanGFX Issue #138](https://github.com/lovyan03/LovyanGFX/issues/138)

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
