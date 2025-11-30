/**
 * ESP32 Status Puck - Pomodoro Timer
 *
 * A beautiful, minimalist Pomodoro timer following Jony Ive's design philosophy:
 * "Simplicity is not the absence of clutter. It's the absence of everything
 * that distracts from what's essential."
 *
 * Hardware: Elecrow CrowPanel 1.28" ESP32-S3 Rotary Display
 */

#define LGFX_USE_V1
#include <Arduino.h>
#include <LovyanGFX.hpp>
#include <lvgl.h>
#include <Adafruit_NeoPixel.h>
#include <Wire.h>
#include <Preferences.h>
#include "CST816D.h"

// ============================================
// Color Constants (Jony Ive palette)
// ============================================
#define COLOR_TOMATO_START 0xFFAA00  // Work start - warm orange-yellow
#define COLOR_TOMATO_END   0x990000  // Work end - deep crimson
#define COLOR_TOMATO     0xFF6347  // Work fallback
#define COLOR_COOL_WHITE 0xE0F0FF  // Rest - signifying renewal
#define COLOR_DARK_GRAY  0x333333  // Background - present, not distracting
#define COLOR_WHITE      0xFFFFFF  // Text

// ============================================
// Pin Definitions
// ============================================
#define POWER_PIN_1 1
#define POWER_PIN_2 2
#define TFT_SCLK 10
#define TFT_MOSI 11
#define TFT_DC   3
#define TFT_CS   9
#define TFT_RST  14
#define TFT_BL   46
#define PWM_CHANNEL 0
#define PWM_FREQ    5000
#define PWM_RES     8
#define TP_I2C_SDA 6
#define TP_I2C_SCL 7
#define TP_RST     13
#define TP_INT     5
#define I2C_SDA 38
#define I2C_SCL 39
#define ENCODER_A  45
#define ENCODER_B  42
#define ENCODER_SW 41
#define LED_PIN 48
#define LED_NUM 5

// Display dimensions
static const uint32_t SCREEN_WIDTH = 240;
static const uint32_t SCREEN_HEIGHT = 240;

// ============================================
// Test Mode - Accelerated timers (1 min = 1 sec)
// Triple-click to toggle at runtime
// ============================================
bool testMode = false;  // Start in normal mode, triple-click to enable test mode
unsigned long getTimeScale() { return testMode ? 60 : 1; }  // 60x faster in test mode

// ============================================
// Timing Constants
// ============================================
const unsigned long DOUBLE_CLICK_MS = 400;  // Slightly longer to allow triple-click
const unsigned long LONG_PRESS_MS = 1000;
const unsigned long AMBIENT_TIMEOUT_MS = 30000;  // Applied at runtime
const unsigned long ONE_MINUTE_MS = 60000;       // Applied at runtime
const float PULSE_PERIOD_MS = 1200.0f;  // 1.2 second breathing cycle (more visible)
float ledAngleOffset = 120.0f;  // Calibrated: LED 0 is at 4 o'clock
const float GAMMA = 2.2f;

// ============================================
// Pomodoro State Machine
// ============================================
enum PomodoroState {
    SETTING,   // Choosing preset - arc empty
    WORKING,   // Focus time - tomato red
    RESTING,   // Recovery - cool white
    PAUSED     // Held breath - everything dims
};

struct PomodoroPreset {
    const char* name;
    int workMinutes;
    int restMinutes;
};

const PomodoroPreset PRESETS[] = {
    { "25 + 5",  25, 5  },  // Classic Pomodoro
    { "45 + 15", 45, 15 },  // Deep Work
    { "15 + 3",  15, 3  },  // Sprint
    { "50 + 10", 50, 10 }   // Extended
};
const int NUM_PRESETS = 4;

// ============================================
// State Variables
// ============================================
PomodoroState currentState = SETTING;
PomodoroState stateBeforePause = SETTING;
int presetIndex = 0;
unsigned long timerStartTime = 0;
unsigned long timerDuration = 0;
unsigned long pausedElapsed = 0;
int completedPomodoros = 0;
unsigned long lastInteractionTime = 0;
bool ambientMode = false;

// Animation state
float currentProgress = 0.0f;
float targetProgress = 0.0f;
uint32_t currentLedColor = 0;
uint32_t targetLedColor = 0;

// Offset calibration display
lv_obj_t* offsetLabel = NULL;
unsigned long offsetDisplayTime = 0;
bool offsetDisplayVisible = false;
bool calibrationMode = false;  // When true, show test pattern
float calibrationAngle = 120.0f;  // Arc position during calibration

// Celebration state
bool celebrating = false;
unsigned long celebrationStart = 0;
const unsigned long CELEBRATION_DURATION = 1000;

// ============================================
// Button State
// ============================================
portMUX_TYPE buttonMux = portMUX_INITIALIZER_UNLOCKED;
volatile unsigned long buttonPressTime = 0;
volatile bool buttonDown = false;
volatile int clickCount = 0;
unsigned long lastClickTime = 0;
bool longPressHandled = false;

// Encoder state
volatile int lastEncoderCLK;
volatile int8_t encoderDelta = 0;

// ============================================
// LVGL UI Objects
// ============================================
lv_obj_t* arcBackground = NULL;
lv_obj_t* arcForeground = NULL;  // Kept for compatibility
lv_obj_t* arcSegments[5] = {NULL, NULL, NULL, NULL, NULL};  // 5 segment arcs
lv_obj_t* timeLabel = NULL;
lv_obj_t* presetLabel = NULL;
lv_obj_t* dots[4] = {NULL, NULL, NULL, NULL};

// Segment configuration - clock-like with wide gaps
const int NUM_SEGMENTS = 5;
const float SEGMENT_GAP_DEG = 12.0f;  // Wide gaps like clock divisions
const float SEGMENT_SWEEP_DEG = (360.0f - (NUM_SEGMENTS * SEGMENT_GAP_DEG)) / NUM_SEGMENTS;  // ~60° each

// 5 colors from orange-yellow to deep crimson
const uint32_t SEGMENT_COLORS[5] = {
    0xFFAA00,  // Segment 1: Orange-yellow
    0xFF7700,  // Segment 2: Orange
    0xFF4400,  // Segment 3: Orange-red
    0xDD2200,  // Segment 4: Red
    0xAA0000   // Segment 5: Deep crimson
};

// ============================================
// LovyanGFX Display Configuration
// ============================================
class LGFX : public lgfx::LGFX_Device {
    lgfx::Panel_GC9A01 _panel_instance;
    lgfx::Bus_SPI _bus_instance;

public:
    LGFX(void) {
        {
            auto cfg = _bus_instance.config();
            cfg.spi_host = SPI2_HOST;
            cfg.spi_mode = 0;
            cfg.freq_write = 80000000;
            cfg.freq_read = 20000000;
            cfg.spi_3wire = true;
            cfg.use_lock = true;
            cfg.dma_channel = SPI_DMA_CH_AUTO;
            cfg.pin_sclk = TFT_SCLK;
            cfg.pin_mosi = TFT_MOSI;
            cfg.pin_miso = -1;
            cfg.pin_dc = TFT_DC;
            _bus_instance.config(cfg);
            _panel_instance.setBus(&_bus_instance);
        }
        {
            auto cfg = _panel_instance.config();
            cfg.pin_cs = TFT_CS;
            cfg.pin_rst = TFT_RST;
            cfg.pin_busy = -1;
            cfg.memory_width = 240;
            cfg.memory_height = 240;
            cfg.panel_width = 240;
            cfg.panel_height = 240;
            cfg.offset_x = 0;
            cfg.offset_y = 0;
            cfg.offset_rotation = 0;
            cfg.dummy_read_pixel = 8;
            cfg.dummy_read_bits = 1;
            cfg.readable = false;
            cfg.invert = true;
            cfg.rgb_order = false;
            cfg.dlen_16bit = false;
            cfg.bus_shared = false;
            _panel_instance.config(cfg);
        }
        setPanel(&_panel_instance);
    }
};

LGFX gfx;
CST816D touch(TP_I2C_SDA, TP_I2C_SCL, TP_RST, TP_INT);

// LVGL Buffers
static lv_disp_draw_buf_t draw_buf;
static lv_color_t *buf = NULL;
static lv_color_t *buf1 = NULL;

// LED Ring
Adafruit_NeoPixel leds(LED_NUM, LED_PIN, NEO_GRB + NEO_KHZ800);

// Preferences for persistence
Preferences prefs;

// ============================================
// Forward Declarations
// ============================================
void createPomodoroUI();
void updateTimeLabel(unsigned long elapsedMs);
void updateProgressDots();
void updateArc(float progress, uint32_t color, float pulse);
void updateLedComet(float progress, uint32_t color, float brightness);
void handleEncoder();
void handleButton();
void startWork();
void transitionToRest();
void transitionToSetting();
void runCelebration();
float smoothValue(float current, float target, float factor);
uint32_t lerpColor(uint32_t c1, uint32_t c2, float t);
float getPulseFactor(unsigned long remainingMs, unsigned long totalDuration);
void checkAmbientMode();
void setDisplayBrightness(uint8_t percent);

// ============================================
// ISR - Button
// ============================================
void IRAM_ATTR buttonISR() {
    portENTER_CRITICAL_ISR(&buttonMux);

    bool pressed = (digitalRead(ENCODER_SW) == LOW);
    unsigned long now = millis();

    if (pressed && !buttonDown) {
        buttonDown = true;
        buttonPressTime = now;
    } else if (!pressed && buttonDown) {
        buttonDown = false;
        if (now - buttonPressTime < LONG_PRESS_MS) {
            clickCount++;
            lastClickTime = now;
        }
    }

    portEXIT_CRITICAL_ISR(&buttonMux);
}

// ============================================
// Display Flush Callback
// ============================================
void my_disp_flush(lv_disp_drv_t *disp, const lv_area_t *area, lv_color_t *color_p) {
    if (gfx.getStartCount() > 0) {
        gfx.endWrite();
    }
    gfx.pushImageDMA(area->x1, area->y1,
                     area->x2 - area->x1 + 1,
                     area->y2 - area->y1 + 1,
                     (lgfx::rgb565_t *)&color_p->full);
    lv_disp_flush_ready(disp);
}

// ============================================
// Touchpad Read Callback
// ============================================
void my_touchpad_read(lv_indev_drv_t *indev_driver, lv_indev_data_t *data) {
    uint16_t touchX, touchY;
    uint8_t gesture;
    bool touched = touch.getTouch(&touchX, &touchY, &gesture);

    if (touched) {
        data->state = LV_INDEV_STATE_PR;
        data->point.x = touchX;
        data->point.y = touchY;
        lastInteractionTime = millis();
        ambientMode = false;
    } else {
        data->state = LV_INDEV_STATE_REL;
    }
}

// ============================================
// Create Pomodoro UI
// ============================================
void createPomodoroUI() {
    // Get active screen
    lv_obj_t* scr = lv_scr_act();

    // Set black background
    lv_obj_set_style_bg_color(scr, lv_color_black(), 0);

    // Create 5 segment arcs (background + foreground in one)
    for (int i = 0; i < NUM_SEGMENTS; i++) {
        // Calculate segment angle range
        float segStart = i * (SEGMENT_SWEEP_DEG + SEGMENT_GAP_DEG);
        float segEnd = segStart + SEGMENT_SWEEP_DEG;

        arcSegments[i] = lv_arc_create(scr);
        lv_obj_set_size(arcSegments[i], 220, 220);
        lv_obj_center(arcSegments[i]);
        lv_arc_set_rotation(arcSegments[i], 270);  // Start at 12 o'clock
        lv_arc_set_bg_angles(arcSegments[i], (int)segStart, (int)segEnd);
        lv_arc_set_range(arcSegments[i], 0, 100);
        lv_arc_set_value(arcSegments[i], 0);
        lv_obj_remove_style(arcSegments[i], NULL, LV_PART_KNOB);
        lv_obj_clear_flag(arcSegments[i], LV_OBJ_FLAG_CLICKABLE);

        // Background: dark gray
        lv_obj_set_style_arc_color(arcSegments[i], lv_color_hex(COLOR_DARK_GRAY), LV_PART_MAIN);
        lv_obj_set_style_arc_width(arcSegments[i], 12, LV_PART_MAIN);

        // Foreground: segment color
        lv_obj_set_style_arc_color(arcSegments[i], lv_color_hex(SEGMENT_COLORS[i]), LV_PART_INDICATOR);
        lv_obj_set_style_arc_width(arcSegments[i], 12, LV_PART_INDICATOR);
    }

    // Keep arcForeground pointing to first segment for compatibility
    arcForeground = arcSegments[0];

    // Time label (MM:SS) - Montserrat 48
    timeLabel = lv_label_create(scr);
    lv_obj_set_style_text_font(timeLabel, &lv_font_montserrat_48, 0);
    lv_obj_set_style_text_color(timeLabel, lv_color_hex(COLOR_WHITE), 0);
    lv_label_set_text(timeLabel, "00:00");
    lv_obj_align(timeLabel, LV_ALIGN_CENTER, 0, -10);

    // Preset label (shown in SETTING state)
    presetLabel = lv_label_create(scr);
    lv_obj_set_style_text_font(presetLabel, &lv_font_montserrat_24, 0);
    lv_obj_set_style_text_color(presetLabel, lv_color_hex(COLOR_WHITE), 0);
    lv_label_set_text(presetLabel, PRESETS[presetIndex].name);
    lv_obj_align(presetLabel, LV_ALIGN_CENTER, 0, 0);

    // Progress dots (4 circles below time)
    int dotRadius = 4;
    int dotSpacing = 16;
    int startX = -((4 - 1) * dotSpacing) / 2;

    for (int i = 0; i < 4; i++) {
        dots[i] = lv_obj_create(scr);
        lv_obj_set_size(dots[i], dotRadius * 2, dotRadius * 2);
        lv_obj_set_style_radius(dots[i], LV_RADIUS_CIRCLE, 0);
        lv_obj_set_style_border_width(dots[i], 0, 0);
        lv_obj_align(dots[i], LV_ALIGN_CENTER, startX + i * dotSpacing, 35);

        // Initially empty (20% opacity via darker color)
        lv_obj_set_style_bg_color(dots[i], lv_color_hex(0x331a10), 0);  // Dark tomato
    }

    // Initial state: show preset selector
    lv_obj_add_flag(timeLabel, LV_OBJ_FLAG_HIDDEN);
    updateProgressDots();
}

// ============================================
// Update Time Label
// ============================================
void updateTimeLabel(unsigned long elapsedMs) {
    int totalSeconds = elapsedMs / 1000;
    int minutes = totalSeconds / 60;
    int seconds = totalSeconds % 60;

    char buf[8];
    snprintf(buf, sizeof(buf), "%02d:%02d", minutes, seconds);
    lv_label_set_text(timeLabel, buf);
}

// ============================================
// Update Progress Dots
// ============================================
void updateProgressDots() {
    uint32_t accentColor = (currentState == RESTING) ? COLOR_COOL_WHITE : COLOR_TOMATO;

    // Calculate dimmed color (20% opacity effect)
    uint8_t r = ((accentColor >> 16) & 0xFF) * 0.2;
    uint8_t g = ((accentColor >> 8) & 0xFF) * 0.2;
    uint8_t b = (accentColor & 0xFF) * 0.2;
    uint32_t dimColor = (r << 16) | (g << 8) | b;

    int dotsToFill = completedPomodoros % 4;

    for (int i = 0; i < 4; i++) {
        if (i < dotsToFill) {
            lv_obj_set_style_bg_color(dots[i], lv_color_hex(accentColor), 0);
        } else {
            lv_obj_set_style_bg_color(dots[i], lv_color_hex(dimColor), 0);
        }
    }
}


// ============================================
// Update Arc - 5 smooth LVGL arc segments
// Work: colored segments, Rest: plain white
// ============================================
void updateArc(float progress, uint32_t color, float pulse) {
    if (progress < 0.0f) progress = 0.0f;
    if (progress > 1.0f) progress = 1.0f;

    for (int i = 0; i < NUM_SEGMENTS; i++) {
        // Each segment covers 1/5 of total progress
        float segProgressStart = (float)i / NUM_SEGMENTS;
        float segProgressEnd = (float)(i + 1) / NUM_SEGMENTS;

        // Calculate segment fill (0-100)
        int segValue;
        if (progress <= segProgressStart) {
            segValue = 0;
        } else if (progress >= segProgressEnd) {
            segValue = 100;
        } else {
            // Partial fill within this segment
            float withinSeg = (progress - segProgressStart) / (segProgressEnd - segProgressStart);
            segValue = (int)(withinSeg * 100.0f + 0.5f);
        }

        lv_arc_set_value(arcSegments[i], segValue);

        // Work: colored segments, Rest: plain white
        uint32_t segColor;
        if (currentState == RESTING) {
            segColor = COLOR_COOL_WHITE;
        } else {
            segColor = SEGMENT_COLORS[i];
        }

        // Apply pulse for breathing effect
        uint8_t r = ((segColor >> 16) & 0xFF) * pulse;
        uint8_t g = ((segColor >> 8) & 0xFF) * pulse;
        uint8_t b = (segColor & 0xFF) * pulse;
        lv_obj_set_style_arc_color(arcSegments[i], lv_color_hex((r << 16) | (g << 8) | b), LV_PART_INDICATOR);
    }
}

// ============================================
// LED Fill Effect - Work: colored, Rest: white
// ============================================
void updateLedComet(float progress, uint32_t color, float brightness) {
    float arcTipAngle = progress * 360.0f;

    leds.clear();

    for (int i = 0; i < LED_NUM; i++) {
        float ledPhysicalAngle = ledAngleOffset - (i * 72.0f);
        if (ledPhysicalAngle < 0) ledPhysicalAngle += 360.0f;

        bool shouldLight = (arcTipAngle >= ledPhysicalAngle);

        if (ledPhysicalAngle < 72.0f && arcTipAngle < 300.0f) {
            shouldLight = (arcTipAngle >= ledPhysicalAngle);
        }

        if (shouldLight) {
            // Work: colored by segment, Rest: white
            uint32_t ledColor;
            if (currentState == RESTING) {
                ledColor = COLOR_COOL_WHITE;
            } else {
                int segmentIndex = (int)(ledPhysicalAngle / 72.0f);
                if (segmentIndex >= NUM_SEGMENTS) segmentIndex = NUM_SEGMENTS - 1;
                if (segmentIndex < 0) segmentIndex = 0;
                ledColor = SEGMENT_COLORS[segmentIndex];
            }

            uint8_t r = (ledColor >> 16) & 0xFF;
            uint8_t g = (ledColor >> 8) & 0xFF;
            uint8_t b = ledColor & 0xFF;

            float gammaBrightness = powf(brightness, GAMMA);
            uint8_t lr = r * gammaBrightness;
            uint8_t lg = g * gammaBrightness;
            uint8_t lb = b * gammaBrightness;
            leds.setPixelColor(i, leds.Color(lr, lg, lb));
        }
    }

    leds.show();
}

// ============================================
// Celebration Rainbow
// ============================================
void runCelebration() {
    unsigned long elapsed = millis() - celebrationStart;

    if (elapsed >= CELEBRATION_DURATION) {
        celebrating = false;
        return;
    }

    // Fast rainbow cascade
    float phase = (float)elapsed / CELEBRATION_DURATION;
    uint16_t hue = (uint16_t)(phase * 3 * 65536) % 65536;  // 3 rainbow cycles

    for (int i = 0; i < LED_NUM; i++) {
        uint16_t ledHue = hue + (i * 65536 / LED_NUM);
        leds.setPixelColor(i, leds.ColorHSV(ledHue, 255, 200));
    }
    leds.show();
}

// ============================================
// Smooth Value Interpolation
// ============================================
float smoothValue(float current, float target, float factor) {
    return current + (target - current) * factor;
}

// ============================================
// Color Interpolation
// ============================================
uint32_t lerpColor(uint32_t c1, uint32_t c2, float t) {
    uint8_t r1 = (c1 >> 16) & 0xFF, g1 = (c1 >> 8) & 0xFF, b1 = c1 & 0xFF;
    uint8_t r2 = (c2 >> 16) & 0xFF, g2 = (c2 >> 8) & 0xFF, b2 = c2 & 0xFF;

    uint8_t r = r1 + (r2 - r1) * t;
    uint8_t g = g1 + (g2 - g1) * t;
    uint8_t b = b1 + (b2 - b1) * t;

    return (r << 16) | (g << 8) | b;
}

// ============================================
// Pulse Factor for End Warning
// BREATHING ANIMATION: 1.2-second cycle, 50% to 100% brightness
// Triggers in final 30% of timer (purely percentage-based)
// ============================================
float getPulseFactor(unsigned long remainingMs, unsigned long totalDuration) {
    // Pure percentage: final 30% of duration
    unsigned long threshold = (totalDuration * 30) / 100;

    // Only pulse when near the end
    if (remainingMs > threshold) return 1.0f;

    // 1.2-second breathing cycle
    float phase = fmodf(millis(), PULSE_PERIOD_MS) / PULSE_PERIOD_MS;

    // Sine wave for organic breathing feel
    float pulse = sinf(phase * 2.0f * PI);

    // Map sine(-1 to +1) to brightness(0.5 to 1.0) - more dramatic range
    return 0.75f + 0.25f * pulse;
}

// ============================================
// Offset Calibration Display
// ============================================
void showOffsetDisplay() {
    if (offsetLabel == NULL) {
        offsetLabel = lv_label_create(lv_scr_act());
        lv_obj_set_style_text_color(offsetLabel, lv_color_hex(0xFFFF00), 0);
        lv_obj_set_style_text_font(offsetLabel, &lv_font_montserrat_24, 0);
        lv_obj_align(offsetLabel, LV_ALIGN_CENTER, 0, 60);
        // Initialize calibration angle from current offset
        calibrationAngle = ledAngleOffset;
    }

    char text[32];
    snprintf(text, sizeof(text), "Offset: %.0f", ledAngleOffset);
    lv_label_set_text(offsetLabel, text);
    lv_obj_clear_flag(offsetLabel, LV_OBJ_FLAG_HIDDEN);

    offsetDisplayTime = millis();
    offsetDisplayVisible = true;
    calibrationMode = true;

    Serial.printf("LED Offset: %.0f\n", ledAngleOffset);
}

void hideOffsetDisplay() {
    if (offsetLabel != NULL) {
        lv_obj_add_flag(offsetLabel, LV_OBJ_FLAG_HIDDEN);
    }
    offsetDisplayVisible = false;
    calibrationMode = false;

    // Reset arc back to value mode (0-360 range)
    lv_arc_set_range(arcForeground, 0, 360);
    lv_arc_set_value(arcForeground, 0);
}

void adjustOffset(int dir) {
    // Move the arc in 15 degree steps
    calibrationAngle += dir * 15.0f;
    if (calibrationAngle >= 360.0f) calibrationAngle -= 360.0f;
    if (calibrationAngle < 0.0f) calibrationAngle += 360.0f;

    // The offset is what makes arc angle 0 align with LED 0
    // LED 0 is at a fixed physical position
    // offset = angle where arc tip should be when LED 0 is lit
    ledAngleOffset = calibrationAngle;

    showOffsetDisplay();
}

// Show calibration pattern - LED 0 always lit, arc pointer rotates to match
void showCalibrationPattern() {
    // Show arc as a small 20° wedge that points at the current calibration angle
    // This makes it easy to see where the arc "tip" is pointing
    int wedgeSize = 20;
    int arcEnd = (int)calibrationAngle;
    int arcStart = arcEnd - wedgeSize;
    if (arcStart < 0) arcStart += 360;

    // Use the raw arc angles API for more control
    // LVGL arc: 0° is at 3 o'clock, goes clockwise
    // Our rotation is set to 270° so 0° becomes 12 o'clock
    lv_arc_set_angles(arcForeground, arcStart, arcEnd);
    lv_obj_set_style_arc_color(arcForeground, lv_color_hex(COLOR_TOMATO), LV_PART_INDICATOR);

    // Always light LED 0 (at 1 o'clock position)
    leds.clear();
    leds.setPixelColor(0, leds.Color(255, 99, 71));  // Tomato
    leds.show();
}

// ============================================
// Read Encoder
// ============================================
void handleEncoder() {
    static unsigned long lastEncoderTime = 0;
    unsigned long now = millis();

    // Debounce: ignore changes within 5ms
    if (now - lastEncoderTime < 5) {
        return;
    }

    int clk = digitalRead(ENCODER_A);

    if (clk != lastEncoderCLK && clk == HIGH) {
        lastEncoderTime = now;
        int dt = digitalRead(ENCODER_B);
        int dir = (dt != clk) ? 1 : -1;

        // In SETTING state: adjust offset (calibration)
        if (currentState == SETTING) {
            adjustOffset(dir);
        }

        lastInteractionTime = millis();
        ambientMode = false;
    }
    lastEncoderCLK = clk;
}

// ============================================
// Handle Button
// ============================================
void handleButton() {
    unsigned long now = millis();

    // Check for long press while button held
    if (buttonDown && !longPressHandled) {
        if (now - buttonPressTime >= LONG_PRESS_MS) {
            longPressHandled = true;

            // Long press: Skip to next phase
            if (currentState == WORKING) {
                transitionToRest();
                Serial.println("Skipped to rest");
            } else if (currentState == RESTING || currentState == PAUSED) {
                transitionToSetting();
                Serial.println("Skipped to setting");
            }

            lastInteractionTime = now;
            ambientMode = false;
        }
    }

    // Reset long press flag when button released
    if (!buttonDown) {
        longPressHandled = false;
    }

    // Process clicks after double-click window
    if (clickCount > 0 && now - lastClickTime >= DOUBLE_CLICK_MS) {
        if (clickCount == 1) {
            // Single click
            if (currentState == SETTING) {
                startWork();
            } else if (currentState == WORKING || currentState == RESTING) {
                // Pause the timer
                stateBeforePause = currentState;
                pausedElapsed = now - timerStartTime;
                currentState = PAUSED;
                Serial.println("Paused");
            } else if (currentState == PAUSED) {
                // Resume the timer
                timerStartTime = now - pausedElapsed;
                currentState = stateBeforePause;
                Serial.println("Resumed");
            }
        } else if (clickCount == 2) {
            // Double click: Reset
            transitionToSetting();
            Serial.println("Reset");
        } else if (clickCount >= 3) {
            // Triple click: Toggle test mode
            testMode = !testMode;
            transitionToSetting();
            Serial.printf("Test mode: %s (1 min = %s)\n",
                testMode ? "ON" : "OFF",
                testMode ? "1 sec" : "1 min");

            // Brief LED flash to indicate mode change
            uint32_t flashColor = testMode ? 0x00FF00 : 0x0000FF;  // Green=test, Blue=normal
            for (int i = 0; i < LED_NUM; i++) {
                leds.setPixelColor(i, flashColor);
            }
            leds.show();
            delay(200);
            leds.clear();
            leds.show();
        }

        clickCount = 0;
        lastInteractionTime = now;
        ambientMode = false;
    }
}

// ============================================
// Start Work Timer
// ============================================
void startWork() {
    currentState = WORKING;
    timerStartTime = millis();
    timerDuration = (PRESETS[presetIndex].workMinutes * 60UL * 1000UL) / getTimeScale();
    currentProgress = 0.0f;
    targetLedColor = COLOR_TOMATO;

    // Show time, hide preset
    lv_obj_clear_flag(timeLabel, LV_OBJ_FLAG_HIDDEN);
    lv_obj_add_flag(presetLabel, LV_OBJ_FLAG_HIDDEN);

    // Reset ALL segments to 0 and set gradient colors for work
    for (int i = 0; i < NUM_SEGMENTS; i++) {
        lv_arc_set_value(arcSegments[i], 0);
        lv_obj_set_style_arc_color(arcSegments[i], lv_color_hex(SEGMENT_COLORS[i]), LV_PART_INDICATOR);
    }

    updateProgressDots();
    Serial.printf("Started %s work session\n", PRESETS[presetIndex].name);
}

// ============================================
// Transition to Rest
// ============================================
void transitionToRest() {
    // Start celebration
    celebrating = true;
    celebrationStart = millis();

    // Increment completed pomodoros
    completedPomodoros++;

    // Save to preferences
    prefs.putInt("completed", completedPomodoros);

    // Setup rest timer
    currentState = RESTING;
    timerStartTime = millis() + CELEBRATION_DURATION;  // Start after celebration

    // Long break every 4 pomodoros
    int restMinutes = (completedPomodoros % 4 == 0) ? 15 : PRESETS[presetIndex].restMinutes;
    timerDuration = (restMinutes * 60UL * 1000UL) / getTimeScale();
    currentProgress = 0.0f;
    targetLedColor = COLOR_COOL_WHITE;

    // Reset ALL segments to 0 and set to white for rest phase
    for (int i = 0; i < NUM_SEGMENTS; i++) {
        lv_arc_set_value(arcSegments[i], 0);
        lv_obj_set_style_arc_color(arcSegments[i], lv_color_hex(COLOR_COOL_WHITE), LV_PART_INDICATOR);
    }

    updateProgressDots();
    Serial.printf("Work complete! Starting %d min rest\n", restMinutes);
}

// ============================================
// Transition to Setting
// ============================================
void transitionToSetting() {
    currentState = SETTING;
    currentProgress = 0.0f;

    // Reset ALL segments to 0 and restore original colors
    for (int i = 0; i < NUM_SEGMENTS; i++) {
        lv_arc_set_value(arcSegments[i], 0);
        lv_obj_set_style_arc_color(arcSegments[i], lv_color_hex(SEGMENT_COLORS[i]), LV_PART_INDICATOR);
    }

    // Show preset, hide time
    lv_obj_add_flag(timeLabel, LV_OBJ_FLAG_HIDDEN);
    lv_obj_clear_flag(presetLabel, LV_OBJ_FLAG_HIDDEN);
    lv_label_set_text(presetLabel, PRESETS[presetIndex].name);

    // Turn off LEDs
    leds.clear();
    leds.show();

    Serial.println("Ready for next session");
}

// ============================================
// Check Ambient Mode
// ============================================
void checkAmbientMode() {
    unsigned long now = millis();

    if (currentState == SETTING && !ambientMode) {
        if (now - lastInteractionTime >= AMBIENT_TIMEOUT_MS) {
            ambientMode = true;
            setDisplayBrightness(20);
            leds.clear();
            leds.show();
            Serial.println("Ambient mode");
        }
    }

    if (ambientMode && now - lastInteractionTime < 100) {
        ambientMode = false;
        setDisplayBrightness(50);
        Serial.println("Woke up");
    }
}

// ============================================
// Set Display Brightness
// ============================================
void setDisplayBrightness(uint8_t percent) {
    int pwm = (percent * 255) / 100;
    ledcWrite(PWM_CHANNEL, pwm);
}

// ============================================
// Setup
// ============================================
void setup() {
    Serial.begin(115200);
    Serial.println("\n\n=== Pomodoro Timer ===");
    Serial.println("Triple-click to toggle test mode (60x speed)");

    // Enable power pins
    pinMode(POWER_PIN_1, OUTPUT);
    digitalWrite(POWER_PIN_1, HIGH);
    pinMode(POWER_PIN_2, OUTPUT);
    digitalWrite(POWER_PIN_2, HIGH);
    delay(50);

    // Initialize I2C and touch
    Wire.begin(I2C_SDA, I2C_SCL);
    touch.begin();

    // Initialize display
    gfx.init();
    gfx.initDMA();
    gfx.startWrite();
    gfx.fillScreen(TFT_BLACK);

    // Setup encoder
    pinMode(ENCODER_A, INPUT);
    pinMode(ENCODER_B, INPUT);
    pinMode(ENCODER_SW, INPUT_PULLUP);
    attachInterrupt(digitalPinToInterrupt(ENCODER_SW), buttonISR, CHANGE);
    lastEncoderCLK = digitalRead(ENCODER_A);

    // Initialize LVGL
    lv_init();

    // Allocate LVGL buffers in PSRAM
    size_t buffer_size = sizeof(lv_color_t) * SCREEN_WIDTH * SCREEN_HEIGHT;
    buf = (lv_color_t *)heap_caps_malloc(buffer_size, MALLOC_CAP_SPIRAM);
    buf1 = (lv_color_t *)heap_caps_malloc(buffer_size, MALLOC_CAP_SPIRAM);

    if (!buf) buf = (lv_color_t *)malloc(buffer_size);
    if (!buf1) buf1 = (lv_color_t *)malloc(buffer_size);

    // Check for malloc failure - halt if allocation failed
    if (!buf || !buf1) {
        Serial.println("FATAL ERROR: Failed to allocate LVGL buffers!");
        Serial.printf("buf: %p, buf1: %p, buffer_size: %zu\n", buf, buf1, buffer_size);
        while (1) {
            delay(1000);  // Halt execution
        }
    }

    lv_disp_draw_buf_init(&draw_buf, buf, buf1, SCREEN_WIDTH * SCREEN_HEIGHT);

    // Initialize display driver
    static lv_disp_drv_t disp_drv;
    lv_disp_drv_init(&disp_drv);
    disp_drv.hor_res = SCREEN_WIDTH;
    disp_drv.ver_res = SCREEN_HEIGHT;
    disp_drv.flush_cb = my_disp_flush;
    disp_drv.draw_buf = &draw_buf;
    lv_disp_drv_register(&disp_drv);

    // Initialize touch input
    static lv_indev_drv_t indev_drv;
    lv_indev_drv_init(&indev_drv);
    indev_drv.type = LV_INDEV_TYPE_POINTER;
    indev_drv.read_cb = my_touchpad_read;
    lv_indev_drv_register(&indev_drv);

    // Setup backlight
    ledcSetup(PWM_CHANNEL, PWM_FREQ, PWM_RES);
    ledcAttachPin(TFT_BL, PWM_CHANNEL);
    setDisplayBrightness(50);

    // Initialize LED ring
    leds.begin();
    leds.setBrightness(150);
    leds.clear();
    leds.show();

    // Load saved pomodoros
    prefs.begin("pomo", false);
    completedPomodoros = prefs.getInt("completed", 0);
    Serial.printf("Loaded %d completed pomodoros\n", completedPomodoros);

    // Create UI
    delay(100);
    createPomodoroUI();

    lastInteractionTime = millis();
    Serial.println("Ready! Rotate encoder to select preset, click to start.");
}

// ============================================
// Main Loop
// ============================================
void loop() {
    unsigned long now = millis();

    // Handle input
    handleEncoder();
    handleButton();

    // State machine
    switch (currentState) {
        case SETTING:
            // Handle calibration mode - show test pattern
            if (calibrationMode) {
                showCalibrationPattern();

                // Auto-hide after 2 seconds of no adjustment
                if (millis() - offsetDisplayTime > 2000) {
                    hideOffsetDisplay();
                    lv_arc_set_value(arcForeground, 0);  // Reset arc
                    leds.clear();
                    leds.show();
                }
            }
            checkAmbientMode();
            break;

        case WORKING:
        case RESTING: {
            // Handle celebration first
            if (celebrating) {
                runCelebration();
                break;
            }

            // Calculate elapsed time
            unsigned long elapsed = now - timerStartTime;

            // Check if timer complete
            if (elapsed >= timerDuration) {
                // Render final frame at 100% before transitioning
                updateArc(1.0f, 0, 1.0f);
                updateLedComet(1.0f, 0, 1.0f);
                lv_timer_handler();
                delay(100);  // Brief pause to show completion

                if (currentState == WORKING) {
                    transitionToRest();
                } else {
                    transitionToSetting();
                }
                break;
            }

            // Calculate progress
            targetProgress = (float)elapsed / (float)timerDuration;
            currentProgress = smoothValue(currentProgress, targetProgress, 0.1f);

            // Get pulse factor for end warning (breathing effect in final 30%)
            unsigned long remaining = timerDuration - elapsed;
            float pulse = getPulseFactor(remaining, timerDuration);

            // Calculate color based on progress
            uint32_t targetColor;
            if (currentState == WORKING) {
                // Lerp from peachy coral to deep blood red as work progresses
                targetColor = lerpColor(COLOR_TOMATO_START, COLOR_TOMATO_END, currentProgress);
            } else {
                targetColor = COLOR_COOL_WHITE;
            }
            currentLedColor = lerpColor(currentLedColor, targetColor, 0.1f);

            // Update display with pulse for breathing effect
            updateArc(currentProgress, targetColor, pulse);
            updateTimeLabel(elapsed);

            // Update LEDs (also pulsing)
            updateLedComet(currentProgress, currentLedColor, pulse);
            break;
        }

        case PAUSED:
            // Show paused state - LEDs breathing slowly
            float breath = 0.3f + 0.2f * sinf(now / 1000.0f * PI);
            updateLedComet(currentProgress, currentLedColor, breath);
            break;
    }

    // LVGL timer
    lv_timer_handler();

    // 60 FPS
    delay(16);
}
