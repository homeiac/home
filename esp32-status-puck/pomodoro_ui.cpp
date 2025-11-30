// Pomodoro Timer UI - Jony Ive Minimalist Design
// ESP32-S3 Status Puck with 1.28" Round Display (240x240)

#include <lvgl.h>

// ============================================================================
// COLOR CONSTANTS
// ============================================================================
#define COLOR_TOMATO     0xFF6347  // Work sessions
#define COLOR_COOL_WHITE 0xE0F0FF  // Rest sessions
#define COLOR_DARK_GRAY  0x333333  // Background arc
#define COLOR_WHITE      0xFFFFFF  // Time label

// ============================================================================
// STATE MACHINE
// ============================================================================
enum PomodoroState {
    SETTING,   // Choosing preset with encoder
    WORKING,   // Active work session
    RESTING,   // Break period
    PAUSED     // Timer paused (encoder button)
};

// ============================================================================
// PRESET CONFIGURATIONS
// ============================================================================
struct Preset {
    const char* name;
    int workMinutes;
    int restMinutes;
};

const Preset PRESETS[] = {
    { "25 + 5",  25, 5  },  // Classic Pomodoro
    { "45 + 15", 45, 15 },  // Deep Work
    { "15 + 3",  15, 3  },  // Sprint
    { "50 + 10", 50, 10 }   // Extended
};
const int PRESET_COUNT = 4;
const int POMODOROS_UNTIL_LONG_BREAK = 4;

// ============================================================================
// GLOBAL STATE
// ============================================================================
PomodoroState currentState = SETTING;
int currentPresetIndex = 0;
int completedPomodoros = 0;

unsigned long sessionStartTime = 0;
unsigned long sessionDuration = 0;  // In milliseconds
bool isWorkSession = true;

// ============================================================================
// UI OBJECT POINTERS
// ============================================================================
lv_obj_t* arcWidget = nullptr;
lv_obj_t* timeLabel = nullptr;
lv_obj_t* presetLabel = nullptr;
lv_obj_t* progressDots[POMODOROS_UNTIL_LONG_BREAK] = {nullptr};

// ============================================================================
// UI CREATION
// ============================================================================

/**
 * Creates the main Pomodoro UI
 * - Arc widget for progress visualization
 * - Centered time/preset label
 * - Progress dots showing completed pomodoros
 */
void createPomodoroUI(lv_obj_t* screen) {
    // -------------------------------------------------------------------------
    // ARC WIDGET (Progress Ring)
    // -------------------------------------------------------------------------
    arcWidget = lv_arc_create(screen);
    lv_obj_set_size(arcWidget, 220, 220);
    lv_obj_center(arcWidget);

    // Arc configuration
    lv_arc_set_rotation(arcWidget, 270);  // Start at 12 o'clock
    lv_arc_set_bg_angles(arcWidget, 0, 360);
    lv_arc_set_value(arcWidget, 0);

    // Styling
    lv_obj_set_style_arc_width(arcWidget, 12, LV_PART_MAIN);
    lv_obj_set_style_arc_width(arcWidget, 12, LV_PART_INDICATOR);
    lv_obj_set_style_arc_color(arcWidget, lv_color_hex(COLOR_DARK_GRAY), LV_PART_MAIN);
    lv_obj_set_style_arc_color(arcWidget, lv_color_hex(COLOR_TOMATO), LV_PART_INDICATOR);
    lv_obj_set_style_arc_rounded(arcWidget, true, LV_PART_MAIN);
    lv_obj_set_style_arc_rounded(arcWidget, true, LV_PART_INDICATOR);

    // Remove knob
    lv_obj_remove_style(arcWidget, nullptr, LV_PART_KNOB);

    // -------------------------------------------------------------------------
    // TIME LABEL (Centered)
    // -------------------------------------------------------------------------
    timeLabel = lv_label_create(screen);
    lv_obj_set_style_text_font(timeLabel, &lv_font_montserrat_48, 0);
    lv_obj_set_style_text_color(timeLabel, lv_color_hex(COLOR_WHITE), 0);
    lv_label_set_text(timeLabel, "00:00");
    lv_obj_align(timeLabel, LV_ALIGN_CENTER, 0, -10);

    // -------------------------------------------------------------------------
    // PRESET LABEL (Shows selected preset in SETTING state)
    // -------------------------------------------------------------------------
    presetLabel = lv_label_create(screen);
    lv_obj_set_style_text_font(presetLabel, &lv_font_montserrat_20, 0);
    lv_obj_set_style_text_color(presetLabel, lv_color_hex(COLOR_WHITE), 0);
    lv_label_set_text(presetLabel, PRESETS[0].name);
    lv_obj_align(presetLabel, LV_ALIGN_CENTER, 0, 50);

    // -------------------------------------------------------------------------
    // PROGRESS DOTS (Pomodoro completion indicators)
    // -------------------------------------------------------------------------
    const int DOT_SIZE = 8;
    const int DOT_SPACING = 4;
    const int TOTAL_WIDTH = (DOT_SIZE * POMODOROS_UNTIL_LONG_BREAK) +
                            (DOT_SPACING * (POMODOROS_UNTIL_LONG_BREAK - 1));
    const int START_X = (240 - TOTAL_WIDTH) / 2;  // Center horizontally
    const int DOT_Y = 180;  // Below time label

    for (int i = 0; i < POMODOROS_UNTIL_LONG_BREAK; i++) {
        progressDots[i] = lv_obj_create(screen);
        lv_obj_set_size(progressDots[i], DOT_SIZE, DOT_SIZE);
        lv_obj_set_pos(progressDots[i], START_X + (i * (DOT_SIZE + DOT_SPACING)), DOT_Y);

        // Circular shape
        lv_obj_set_style_radius(progressDots[i], LV_RADIUS_CIRCLE, 0);
        lv_obj_set_style_border_width(progressDots[i], 0, 0);

        // Empty state (20% opacity)
        lv_obj_set_style_bg_color(progressDots[i], lv_color_hex(COLOR_TOMATO), 0);
        lv_obj_set_style_bg_opa(progressDots[i], LV_OPA_20, 0);
    }
}

// ============================================================================
// UI UPDATE FUNCTIONS
// ============================================================================

/**
 * Updates time label with elapsed time in MM:SS format
 * @param elapsedMs Elapsed time in milliseconds
 */
void updateTimeLabel(unsigned long elapsedMs) {
    unsigned long totalSeconds = elapsedMs / 1000;
    int minutes = totalSeconds / 60;
    int seconds = totalSeconds % 60;

    char timeStr[6];
    snprintf(timeStr, sizeof(timeStr), "%02d:%02d", minutes, seconds);
    lv_label_set_text(timeLabel, timeStr);
}

/**
 * Updates progress arc based on elapsed time
 * @param elapsedMs Elapsed time in milliseconds
 * @param totalMs Total session duration in milliseconds
 */
void updateProgressArc(unsigned long elapsedMs, unsigned long totalMs) {
    if (totalMs == 0) {
        lv_arc_set_value(arcWidget, 0);
        return;
    }

    int percentage = (elapsedMs * 100) / totalMs;
    if (percentage > 100) percentage = 100;

    lv_arc_set_value(arcWidget, percentage);
}

/**
 * Updates progress dots to show completed pomodoros
 * @param completed Number of completed work sessions (0-4)
 */
void updateProgressDots(int completed) {
    lv_color_t accentColor = isWorkSession ?
        lv_color_hex(COLOR_TOMATO) :
        lv_color_hex(COLOR_COOL_WHITE);

    for (int i = 0; i < POMODOROS_UNTIL_LONG_BREAK; i++) {
        lv_obj_set_style_bg_color(progressDots[i], accentColor, 0);

        if (i < completed) {
            // Filled dot (100% opacity)
            lv_obj_set_style_bg_opa(progressDots[i], LV_OPA_COVER, 0);
        } else {
            // Empty dot (20% opacity)
            lv_obj_set_style_bg_opa(progressDots[i], LV_OPA_20, 0);
        }
    }
}

/**
 * Sets arc color based on session type
 * @param isWork True for work session (tomato), false for rest (cool white)
 */
void setArcColor(bool isWork) {
    lv_color_t color = isWork ?
        lv_color_hex(COLOR_TOMATO) :
        lv_color_hex(COLOR_COOL_WHITE);

    lv_obj_set_style_arc_color(arcWidget, color, LV_PART_INDICATOR);
}

// ============================================================================
// STATE HANDLERS
// ============================================================================

/**
 * SETTING State Handler
 * - Shows current preset name
 * - Encoder rotates through presets
 * - Encoder button starts work session
 */
void handleSettingState() {
    // Update UI to show preset selection
    lv_label_set_text(presetLabel, PRESETS[currentPresetIndex].name);
    lv_obj_clear_flag(presetLabel, LV_OBJ_FLAG_HIDDEN);

    // Reset arc
    lv_arc_set_value(arcWidget, 0);
    setArcColor(true);  // Work color

    // Show 00:00
    updateTimeLabel(0);
}

/**
 * Handles encoder rotation in SETTING state
 * @param direction 1 for clockwise, -1 for counter-clockwise
 */
void onEncoderRotate_Setting(int direction) {
    currentPresetIndex += direction;

    // Wrap around
    if (currentPresetIndex < 0) {
        currentPresetIndex = PRESET_COUNT - 1;
    } else if (currentPresetIndex >= PRESET_COUNT) {
        currentPresetIndex = 0;
    }

    handleSettingState();  // Refresh UI
}

/**
 * Handles encoder button press in SETTING state
 * Starts work session
 */
void onEncoderButton_Setting() {
    // Start work session
    currentState = WORKING;
    isWorkSession = true;
    sessionStartTime = millis();
    sessionDuration = PRESETS[currentPresetIndex].workMinutes * 60 * 1000UL;

    // Hide preset label
    lv_obj_add_flag(presetLabel, LV_OBJ_FLAG_HIDDEN);

    // Reset arc
    lv_arc_set_value(arcWidget, 0);
    setArcColor(true);
}

/**
 * WORKING State Handler
 * - Updates arc and time label with elapsed time
 * - Counts UP from 00:00
 * - Transitions to RESTING when work duration complete
 */
void handleWorkingState() {
    unsigned long elapsed = millis() - sessionStartTime;

    // Check if session complete
    if (elapsed >= sessionDuration) {
        // Work session complete
        completedPomodoros++;

        // Check if it's time for long break
        if (completedPomodoros >= POMODOROS_UNTIL_LONG_BREAK) {
            completedPomodoros = 0;  // Reset counter
        }

        // Transition to rest
        currentState = RESTING;
        isWorkSession = false;
        sessionStartTime = millis();
        sessionDuration = PRESETS[currentPresetIndex].restMinutes * 60 * 1000UL;

        setArcColor(false);  // Rest color
        updateProgressDots(completedPomodoros);
        return;
    }

    // Update UI
    updateTimeLabel(elapsed);
    updateProgressArc(elapsed, sessionDuration);
}

/**
 * RESTING State Handler
 * - Updates arc and time label with elapsed time
 * - Uses cool white color
 * - Transitions to SETTING when rest duration complete
 */
void handleRestingState() {
    unsigned long elapsed = millis() - sessionStartTime;

    // Check if session complete
    if (elapsed >= sessionDuration) {
        // Rest complete, return to SETTING
        currentState = SETTING;
        isWorkSession = true;
        handleSettingState();
        return;
    }

    // Update UI
    updateTimeLabel(elapsed);
    updateProgressArc(elapsed, sessionDuration);
}

/**
 * PAUSED State Handler
 * - Freezes time display
 * - Encoder button resumes
 */
void handlePausedState() {
    // Time display frozen, no updates needed
    // Button press handled by onEncoderButton_Paused()
}

/**
 * Handles encoder button press in WORKING/RESTING state
 * Toggles pause
 */
void onEncoderButton_WorkingOrResting() {
    if (currentState == PAUSED) {
        // Resume
        // Adjust sessionStartTime to account for pause duration
        unsigned long pauseDuration = millis() - sessionStartTime;
        sessionStartTime = millis() - (sessionDuration - pauseDuration);

        currentState = isWorkSession ? WORKING : RESTING;
    } else {
        // Pause
        currentState = PAUSED;
    }
}

// ============================================================================
// MAIN UPDATE LOOP
// ============================================================================

/**
 * Main Pomodoro update function
 * Call this in your main loop() at ~60Hz
 */
void updatePomodoroUI() {
    switch (currentState) {
        case SETTING:
            // UI updates handled by encoder callbacks
            break;

        case WORKING:
            handleWorkingState();
            break;

        case RESTING:
            handleRestingState();
            break;

        case PAUSED:
            handlePausedState();
            break;
    }

    lv_task_handler();  // LVGL update
}

// ============================================================================
// ENCODER INTEGRATION (Call these from your encoder ISR/polling)
// ============================================================================

/**
 * Call when encoder rotates
 * @param direction 1 for CW, -1 for CCW
 */
void pomodoroEncoderRotate(int direction) {
    if (currentState == SETTING) {
        onEncoderRotate_Setting(direction);
    }
    // Ignore rotation in other states
}

/**
 * Call when encoder button pressed
 */
void pomodoroEncoderButton() {
    switch (currentState) {
        case SETTING:
            onEncoderButton_Setting();
            break;

        case WORKING:
        case RESTING:
        case PAUSED:
            onEncoderButton_WorkingOrResting();
            break;
    }
}
