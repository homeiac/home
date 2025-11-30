/**
 * Unit Tests for Encoder Handler
 *
 * Tests rotary encoder event detection and debouncing.
 * Uses mocked hardware abstraction layer.
 * Run with: pio test -e native
 */

#include <unity.h>
#include "../include/hardware_abstraction.h"

// ============================================
// Mock Hardware State
// ============================================

// Mock state for encoder simulation
static int32_t mock_encoder_position = 0;
static bool mock_switch_pressed = false;
static uint32_t mock_press_start_time = 0;
static uint32_t mock_current_time = 0;

// Mock implementations (native build only)
#ifdef NATIVE_BUILD

int32_t encoder_get_position(void) {
    return mock_encoder_position;
}

void encoder_reset_position(void) {
    mock_encoder_position = 0;
}

uint32_t system_millis(void) {
    return mock_current_time;
}

#endif

// ============================================
// Encoder Logic Under Test
// ============================================

// Simplified encoder handler for testing
typedef struct {
    int32_t last_position;
    bool switch_state;
    uint32_t switch_press_time;
    int rotation_threshold;  // Detents needed for event
} EncoderHandler;

void encoder_handler_init(EncoderHandler* handler) {
    handler->last_position = 0;
    handler->switch_state = false;
    handler->switch_press_time = 0;
    handler->rotation_threshold = 4;  // Typical encoder has 4 steps per detent
}

EncoderEvent encoder_handler_update(EncoderHandler* handler,
                                     int32_t current_pos,
                                     bool switch_pressed,
                                     uint32_t current_time) {
    EncoderEvent event = ENCODER_NONE;

    // Check rotation
    int32_t delta = current_pos - handler->last_position;

    if (delta >= handler->rotation_threshold) {
        event = ENCODER_CW;
        handler->last_position = current_pos;
    } else if (delta <= -handler->rotation_threshold) {
        event = ENCODER_CCW;
        handler->last_position = current_pos;
    }

    // Check switch - only return press events, rotation takes priority
    if (event == ENCODER_NONE) {
        if (switch_pressed && !handler->switch_state) {
            // Switch just pressed
            handler->switch_press_time = current_time;
            handler->switch_state = true;
        } else if (!switch_pressed && handler->switch_state) {
            // Switch just released
            uint32_t press_duration = current_time - handler->switch_press_time;
            handler->switch_state = false;

            if (press_duration >= 3000) {
                event = ENCODER_LONG_PRESS;
            } else if (press_duration >= 50) {  // Debounce
                event = ENCODER_PRESS;
            }
        }
    }

    return event;
}

// ============================================
// Test Fixtures
// ============================================

static EncoderHandler handler;

void setUp(void) {
    encoder_handler_init(&handler);
    mock_encoder_position = 0;
    mock_switch_pressed = false;
    mock_current_time = 0;
}

void tearDown(void) {
    // Nothing to clean up
}

// ============================================
// Rotation Tests
// ============================================

void test_no_rotation_returns_none(void) {
    EncoderEvent event = encoder_handler_update(&handler, 0, false, 0);
    TEST_ASSERT_EQUAL(ENCODER_NONE, event);
}

void test_clockwise_rotation_detected(void) {
    // Simulate 4 steps clockwise (one detent)
    EncoderEvent event = encoder_handler_update(&handler, 4, false, 0);
    TEST_ASSERT_EQUAL(ENCODER_CW, event);
}

void test_counter_clockwise_rotation_detected(void) {
    // Simulate 4 steps counter-clockwise
    EncoderEvent event = encoder_handler_update(&handler, -4, false, 0);
    TEST_ASSERT_EQUAL(ENCODER_CCW, event);
}

void test_small_rotation_ignored(void) {
    // Less than threshold should be ignored (prevents jitter)
    EncoderEvent event = encoder_handler_update(&handler, 2, false, 0);
    TEST_ASSERT_EQUAL(ENCODER_NONE, event);
}

void test_multiple_rotations_tracked(void) {
    encoder_handler_update(&handler, 4, false, 0);  // First CW
    EncoderEvent event = encoder_handler_update(&handler, 8, false, 0);  // Second CW
    TEST_ASSERT_EQUAL(ENCODER_CW, event);
}

void test_rotation_direction_change(void) {
    encoder_handler_update(&handler, 4, false, 0);  // CW

    // Now go CCW past the starting point
    EncoderEvent event = encoder_handler_update(&handler, 0, false, 0);  // Back to 0
    TEST_ASSERT_EQUAL(ENCODER_CCW, event);
}

// ============================================
// Switch/Press Tests
// ============================================

void test_short_press_detected(void) {
    // Press down
    encoder_handler_update(&handler, 0, true, 0);

    // Release after 100ms
    EncoderEvent event = encoder_handler_update(&handler, 0, false, 100);

    TEST_ASSERT_EQUAL(ENCODER_PRESS, event);
}

void test_long_press_detected(void) {
    // Press down
    encoder_handler_update(&handler, 0, true, 0);

    // Release after 3500ms
    EncoderEvent event = encoder_handler_update(&handler, 0, false, 3500);

    TEST_ASSERT_EQUAL(ENCODER_LONG_PRESS, event);
}

void test_very_short_press_debounced(void) {
    // Press down
    encoder_handler_update(&handler, 0, true, 0);

    // Release after only 20ms (too short, debounced)
    EncoderEvent event = encoder_handler_update(&handler, 0, false, 20);

    TEST_ASSERT_EQUAL(ENCODER_NONE, event);
}

void test_press_during_rotation_ignored(void) {
    // If rotating and pressing simultaneously, rotation wins
    // Press down
    encoder_handler_update(&handler, 0, true, 0);

    // Rotate while pressed
    EncoderEvent event = encoder_handler_update(&handler, 4, true, 100);

    TEST_ASSERT_EQUAL(ENCODER_CW, event);  // Rotation, not press
}

void test_press_only_triggers_on_release(void) {
    // Press down - no event yet
    EncoderEvent event1 = encoder_handler_update(&handler, 0, true, 0);
    TEST_ASSERT_EQUAL(ENCODER_NONE, event1);

    // Still pressed - no event
    EncoderEvent event2 = encoder_handler_update(&handler, 0, true, 50);
    TEST_ASSERT_EQUAL(ENCODER_NONE, event2);

    // Release - now we get the event
    EncoderEvent event3 = encoder_handler_update(&handler, 0, false, 100);
    TEST_ASSERT_EQUAL(ENCODER_PRESS, event3);
}

// ============================================
// Edge Cases
// ============================================

void test_handler_init_resets_state(void) {
    handler.last_position = 100;
    handler.switch_state = true;

    encoder_handler_init(&handler);

    TEST_ASSERT_EQUAL(0, handler.last_position);
    TEST_ASSERT_FALSE(handler.switch_state);
}

void test_long_press_boundary_3000ms(void) {
    encoder_handler_update(&handler, 0, true, 0);

    // Exactly 3000ms - should be long press
    EncoderEvent event = encoder_handler_update(&handler, 0, false, 3000);

    TEST_ASSERT_EQUAL(ENCODER_LONG_PRESS, event);
}

void test_short_press_boundary_2999ms(void) {
    encoder_handler_update(&handler, 0, true, 0);

    // 2999ms - just under threshold, should be short press
    EncoderEvent event = encoder_handler_update(&handler, 0, false, 2999);

    TEST_ASSERT_EQUAL(ENCODER_PRESS, event);
}

// ============================================
// Test Runner
// ============================================

int main(int argc, char** argv) {
    UNITY_BEGIN();

    // Rotation tests
    RUN_TEST(test_no_rotation_returns_none);
    RUN_TEST(test_clockwise_rotation_detected);
    RUN_TEST(test_counter_clockwise_rotation_detected);
    RUN_TEST(test_small_rotation_ignored);
    RUN_TEST(test_multiple_rotations_tracked);
    RUN_TEST(test_rotation_direction_change);

    // Switch tests
    RUN_TEST(test_short_press_detected);
    RUN_TEST(test_long_press_detected);
    RUN_TEST(test_very_short_press_debounced);
    RUN_TEST(test_press_during_rotation_ignored);
    RUN_TEST(test_press_only_triggers_on_release);

    // Edge cases
    RUN_TEST(test_handler_init_resets_state);
    RUN_TEST(test_long_press_boundary_3000ms);
    RUN_TEST(test_short_press_boundary_2999ms);

    return UNITY_END();
}
