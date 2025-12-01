#ifndef APP_FRAMEWORK_H
#define APP_FRAMEWORK_H

/**
 * ESP32 Status Puck - Lightweight App Framework
 *
 * Function pointer based architecture for minimal overhead.
 * Long press (1s) globally opens app menu from any app.
 */

#include <stdint.h>

// ============================================
// Button Event Types
// ============================================
enum ButtonEvent {
    BTN_NONE = 0,
    BTN_CLICK,
    BTN_DOUBLE,
    BTN_TRIPLE,
    BTN_LONG
};

// ============================================
// Alert Priority Levels
// ============================================
enum AlertPriority {
    ALERT_NONE = 0,
    ALERT_INFO,      // Blue flash
    ALERT_WARNING,   // Amber pulse
    ALERT_CRITICAL   // Red pulse, interrupts any app
};

// ============================================
// App Definition - Function Pointer Style
// ============================================
typedef void (*AppInitFn)(void);
typedef void (*AppDeinitFn)(void);
typedef void (*AppUpdateFn)(void);
typedef void (*AppEncoderFn)(int direction);
typedef void (*AppButtonFn)(ButtonEvent event);

typedef struct {
    const char* name;
    AppInitFn init;
    AppDeinitFn deinit;
    AppUpdateFn update;
    AppEncoderFn handleEncoder;
    AppButtonFn handleButton;
} AppDefinition;

// ============================================
// Framework State (extern declarations)
// ============================================
extern int currentAppIndex;
extern int appCount;
extern AppDefinition* apps;
extern bool showingAppMenu;

// Alert state
extern AlertPriority pendingAlertPriority;
extern const char* pendingAlertMessage;
extern bool alertOverlayVisible;

// ============================================
// Framework Functions
// ============================================

// Initialize framework with app list
void framework_init(AppDefinition* appList, int count);

// Switch to app by index (calls deinit/init)
void framework_switchApp(int index);

// App menu functions
void framework_showMenu(void);
void framework_hideMenu(void);
void framework_handleMenuEncoder(int direction);
void framework_handleMenuButton(ButtonEvent event);
void framework_updateMenu(void);

// Alert functions
void framework_raiseAlert(AlertPriority priority, const char* message);
void framework_dismissAlert(void);
void framework_updateAlertOverlay(void);

// Process raw button state into ButtonEvent
ButtonEvent framework_processButtonEvent(void);

#endif // APP_FRAMEWORK_H
