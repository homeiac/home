/**
 * Unit Tests for Status Parser
 *
 * Tests JSON parsing for ClaudeCodeUI and Home Assistant responses.
 * Run with: pio test -e native
 */

#include <unity.h>
#include "../include/status_model.h"

// External function declarations
extern bool parse_claude_status(const char* json, ClaudeCodeStatus* status);
extern bool parse_ha_status(const char* json, HomeAssistantStatus* status);

// Test fixtures
static ClaudeCodeStatus claude_status;
static HomeAssistantStatus ha_status;

void setUp(void) {
    memset(&claude_status, 0, sizeof(ClaudeCodeStatus));
    memset(&ha_status, 0, sizeof(HomeAssistantStatus));
}

void tearDown(void) {
    // Nothing to clean up
}

// ============================================
// Claude Code Status Parsing Tests
// ============================================

void test_parse_claude_full_response(void) {
    const char* json = R"({
        "sessions": 2,
        "agents": 1,
        "lastTask": "Fixed auth bug in login.ts",
        "lastTaskTime": "2024-01-15T10:30:00Z",
        "gitDirty": 3,
        "timestamp": "2024-01-15T10:35:00Z"
    })";

    bool result = parse_claude_status(json, &claude_status);

    TEST_ASSERT_TRUE(result);
    TEST_ASSERT_EQUAL(2, claude_status.active_sessions);
    TEST_ASSERT_EQUAL(1, claude_status.running_agents);
    TEST_ASSERT_EQUAL_STRING("Fixed auth bug in login.ts", claude_status.last_task);
    TEST_ASSERT_EQUAL(GIT_DIRTY, claude_status.git_status);
    TEST_ASSERT_EQUAL(3, claude_status.git_changed_files);
    TEST_ASSERT_EQUAL(CONN_CONNECTED, claude_status.connection);
}

void test_parse_claude_clean_git(void) {
    const char* json = R"({
        "sessions": 0,
        "agents": 0,
        "lastTask": null,
        "gitDirty": 0,
        "timestamp": "2024-01-15T10:35:00Z"
    })";

    bool result = parse_claude_status(json, &claude_status);

    TEST_ASSERT_TRUE(result);
    TEST_ASSERT_EQUAL(GIT_CLEAN, claude_status.git_status);
    TEST_ASSERT_EQUAL(0, claude_status.git_changed_files);
}

void test_parse_claude_missing_fields_uses_defaults(void) {
    const char* json = R"({
        "sessions": 1,
        "timestamp": "2024-01-15T10:35:00Z"
    })";

    bool result = parse_claude_status(json, &claude_status);

    TEST_ASSERT_TRUE(result);
    TEST_ASSERT_EQUAL(1, claude_status.active_sessions);
    TEST_ASSERT_EQUAL(0, claude_status.running_agents);  // Default
    TEST_ASSERT_EQUAL(GIT_CLEAN, claude_status.git_status);  // gitDirty=0 default
}

void test_parse_claude_invalid_json(void) {
    const char* json = "not valid json at all";

    bool result = parse_claude_status(json, &claude_status);

    TEST_ASSERT_FALSE(result);
    TEST_ASSERT_EQUAL(CONN_ERROR, claude_status.connection);
    TEST_ASSERT_GREATER_THAN(0, strlen(claude_status.error_message));
}

void test_parse_claude_null_inputs(void) {
    TEST_ASSERT_FALSE(parse_claude_status(NULL, &claude_status));
    TEST_ASSERT_FALSE(parse_claude_status("{}", NULL));
}

void test_parse_claude_truncates_long_task(void) {
    // Create a task longer than MAX_TASK_SUMMARY
    char long_task[128];
    memset(long_task, 'A', 127);
    long_task[127] = '\0';

    char json[256];
    snprintf(json, sizeof(json), R"({"sessions": 1, "lastTask": "%s"})", long_task);

    bool result = parse_claude_status(json, &claude_status);

    TEST_ASSERT_TRUE(result);
    TEST_ASSERT_LESS_THAN(MAX_TASK_SUMMARY, strlen(claude_status.last_task));
}

// ============================================
// Home Assistant Status Parsing Tests
// ============================================

void test_parse_ha_full_response(void) {
    const char* json = R"({
        "cpu_temp": 65,
        "memory_pct": 72,
        "k8s_healthy": true,
        "alerts": 2,
        "notifications": 3,
        "office_lights": true,
        "timestamp": "2024-01-15T10:35:00Z"
    })";

    bool result = parse_ha_status(json, &ha_status);

    TEST_ASSERT_TRUE(result);
    TEST_ASSERT_EQUAL(65, ha_status.cpu_temp);
    TEST_ASSERT_EQUAL(72, ha_status.memory_percent);
    TEST_ASSERT_TRUE(ha_status.k8s_healthy);
    TEST_ASSERT_EQUAL(2, ha_status.active_alerts);
    TEST_ASSERT_EQUAL(3, ha_status.notification_count);
    TEST_ASSERT_TRUE(ha_status.office_lights);
    TEST_ASSERT_EQUAL(CONN_CONNECTED, ha_status.connection);
}

void test_parse_ha_all_good_scenario(void) {
    const char* json = R"({
        "cpu_temp": 45,
        "memory_pct": 30,
        "k8s_healthy": true,
        "alerts": 0,
        "notifications": 0,
        "office_lights": false
    })";

    bool result = parse_ha_status(json, &ha_status);

    TEST_ASSERT_TRUE(result);
    TEST_ASSERT_EQUAL(45, ha_status.cpu_temp);
    TEST_ASSERT_EQUAL(0, ha_status.active_alerts);
    TEST_ASSERT_TRUE(ha_status.k8s_healthy);
}

void test_parse_ha_cluster_down_scenario(void) {
    const char* json = R"({
        "cpu_temp": 85,
        "memory_pct": 95,
        "k8s_healthy": false,
        "alerts": 5,
        "notifications": 10,
        "office_lights": false
    })";

    bool result = parse_ha_status(json, &ha_status);

    TEST_ASSERT_TRUE(result);
    TEST_ASSERT_FALSE(ha_status.k8s_healthy);
    TEST_ASSERT_EQUAL(5, ha_status.active_alerts);
    TEST_ASSERT_EQUAL(85, ha_status.cpu_temp);
}

void test_parse_ha_missing_fields_uses_defaults(void) {
    const char* json = R"({
        "cpu_temp": 50
    })";

    bool result = parse_ha_status(json, &ha_status);

    TEST_ASSERT_TRUE(result);
    TEST_ASSERT_EQUAL(50, ha_status.cpu_temp);
    TEST_ASSERT_EQUAL(-1, ha_status.memory_percent);  // Default for missing
    TEST_ASSERT_FALSE(ha_status.k8s_healthy);  // Default false
}

void test_parse_ha_invalid_json(void) {
    const char* json = "{malformed: json";

    bool result = parse_ha_status(json, &ha_status);

    TEST_ASSERT_FALSE(result);
    TEST_ASSERT_EQUAL(CONN_ERROR, ha_status.connection);
}

// ============================================
// Test Runner
// ============================================

int main(int argc, char** argv) {
    UNITY_BEGIN();

    // Claude Code parsing
    RUN_TEST(test_parse_claude_full_response);
    RUN_TEST(test_parse_claude_clean_git);
    RUN_TEST(test_parse_claude_missing_fields_uses_defaults);
    RUN_TEST(test_parse_claude_invalid_json);
    RUN_TEST(test_parse_claude_null_inputs);
    RUN_TEST(test_parse_claude_truncates_long_task);

    // Home Assistant parsing
    RUN_TEST(test_parse_ha_full_response);
    RUN_TEST(test_parse_ha_all_good_scenario);
    RUN_TEST(test_parse_ha_cluster_down_scenario);
    RUN_TEST(test_parse_ha_missing_fields_uses_defaults);
    RUN_TEST(test_parse_ha_invalid_json);

    return UNITY_END();
}
