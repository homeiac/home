/**
 * Unit Tests for State Manager
 *
 * Tests state transitions, device cycling, and view navigation.
 * Run with: pio test -e native
 */

#include <unity.h>
#include "../include/status_model.h"

// Test fixtures
static PuckState state;

void setUp(void) {
    state_init(&state);
}

void tearDown(void) {
    // Nothing to clean up
}

// ============================================
// Initialization Tests
// ============================================

void test_state_init_sets_defaults(void) {
    TEST_ASSERT_EQUAL(VIEW_CLAUDE_CODE, state.current_view);
    TEST_ASSERT_EQUAL(0, state.current_device_index);
    TEST_ASSERT_EQUAL(0, state.claude_device_count);
    TEST_ASSERT_FALSE(state.refresh_in_progress);
}

void test_state_init_clears_claude_status(void) {
    for (int i = 0; i < 5; i++) {
        TEST_ASSERT_EQUAL(CONN_DISCONNECTED, state.claude_status[i].connection);
        TEST_ASSERT_EQUAL(-1, state.claude_status[i].active_sessions);
        TEST_ASSERT_EQUAL(GIT_UNKNOWN, state.claude_status[i].git_status);
    }
}

void test_state_init_clears_ha_status(void) {
    TEST_ASSERT_EQUAL(CONN_DISCONNECTED, state.ha_status.connection);
    TEST_ASSERT_EQUAL(-999, state.ha_status.cpu_temp);
    TEST_ASSERT_EQUAL(-1, state.ha_status.memory_percent);
    TEST_ASSERT_FALSE(state.ha_status.k8s_healthy);
}

// ============================================
// Device Navigation Tests
// ============================================

void test_next_device_increments_index(void) {
    state.claude_device_count = 3;
    state.current_device_index = 0;

    state_next_device(&state);

    TEST_ASSERT_EQUAL(1, state.current_device_index);
}

void test_next_device_wraps_at_end(void) {
    state.claude_device_count = 3;
    state.current_device_index = 2;  // Last device

    state_next_device(&state);

    TEST_ASSERT_EQUAL(0, state.current_device_index);  // Wrapped to first
}

void test_prev_device_decrements_index(void) {
    state.claude_device_count = 3;
    state.current_device_index = 2;

    state_prev_device(&state);

    TEST_ASSERT_EQUAL(1, state.current_device_index);
}

void test_prev_device_wraps_at_start(void) {
    state.claude_device_count = 3;
    state.current_device_index = 0;  // First device

    state_prev_device(&state);

    TEST_ASSERT_EQUAL(2, state.current_device_index);  // Wrapped to last
}

void test_next_device_no_op_when_empty(void) {
    state.claude_device_count = 0;
    state.current_device_index = 0;

    state_next_device(&state);

    TEST_ASSERT_EQUAL(0, state.current_device_index);  // Unchanged
}

// ============================================
// View Navigation Tests
// ============================================

void test_next_view_claude_to_ha(void) {
    state.current_view = VIEW_CLAUDE_CODE;

    state_next_view(&state);

    TEST_ASSERT_EQUAL(VIEW_HOME_ASSISTANT, state.current_view);
}

void test_next_view_ha_to_claude(void) {
    state.current_view = VIEW_HOME_ASSISTANT;
    state.current_device_index = 2;  // Some non-zero value

    state_next_view(&state);

    TEST_ASSERT_EQUAL(VIEW_CLAUDE_CODE, state.current_view);
    TEST_ASSERT_EQUAL(0, state.current_device_index);  // Reset to first device
}

void test_next_view_settings_stays(void) {
    state.current_view = VIEW_SETTINGS;

    state_next_view(&state);

    TEST_ASSERT_EQUAL(VIEW_SETTINGS, state.current_view);  // Stays in settings
}

// ============================================
// Current Status Access Tests
// ============================================

void test_get_current_claude_returns_correct_device(void) {
    state.claude_device_count = 2;
    state.current_device_index = 1;
    strcpy(state.claude_status[1].device_name, "work");

    ClaudeCodeStatus* current = state_get_current_claude(&state);

    TEST_ASSERT_NOT_NULL(current);
    TEST_ASSERT_EQUAL_STRING("work", current->device_name);
}

void test_get_current_claude_null_when_empty(void) {
    state.claude_device_count = 0;

    ClaudeCodeStatus* current = state_get_current_claude(&state);

    TEST_ASSERT_NULL(current);
}

void test_get_current_claude_null_for_invalid_index(void) {
    state.claude_device_count = 2;
    state.current_device_index = 5;  // Out of bounds

    ClaudeCodeStatus* current = state_get_current_claude(&state);

    TEST_ASSERT_NULL(current);
}

// ============================================
// Test Runner
// ============================================

int main(int argc, char** argv) {
    UNITY_BEGIN();

    // Initialization
    RUN_TEST(test_state_init_sets_defaults);
    RUN_TEST(test_state_init_clears_claude_status);
    RUN_TEST(test_state_init_clears_ha_status);

    // Device navigation
    RUN_TEST(test_next_device_increments_index);
    RUN_TEST(test_next_device_wraps_at_end);
    RUN_TEST(test_prev_device_decrements_index);
    RUN_TEST(test_prev_device_wraps_at_start);
    RUN_TEST(test_next_device_no_op_when_empty);

    // View navigation
    RUN_TEST(test_next_view_claude_to_ha);
    RUN_TEST(test_next_view_ha_to_claude);
    RUN_TEST(test_next_view_settings_stays);

    // Current status access
    RUN_TEST(test_get_current_claude_returns_correct_device);
    RUN_TEST(test_get_current_claude_null_when_empty);
    RUN_TEST(test_get_current_claude_null_for_invalid_index);

    return UNITY_END();
}
