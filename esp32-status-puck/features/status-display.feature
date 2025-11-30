Feature: Status Display
  As a developer monitoring Claude Code sessions
  I want to see meaningful status at a glance on the round display
  So that I know what's happening without opening my laptop

  Background:
    Given the puck is connected to device "home"
    And the ClaudeCodeUI API is reachable

  Scenario: Display active session count
    Given ClaudeCodeUI reports 2 active sessions
    When the status is refreshed
    Then the display should show "2" in the session indicator
    And the session indicator should be green

  Scenario: Display no active sessions
    Given ClaudeCodeUI reports 0 active sessions
    When the status is refreshed
    Then the display should show "0" in the session indicator
    And the session indicator should be gray

  Scenario: Display last task summary
    Given ClaudeCodeUI reports last task "Fixed auth bug in login.ts"
    When the status is refreshed
    Then the display should show truncated task text
    And the full text should be available on touch

  Scenario: Display git status indicator
    Given ClaudeCodeUI reports git status "dirty" with 3 changed files
    When the status is refreshed
    Then the display should show a modified icon
    And show "+3" next to the git indicator

  Scenario: Display clean git status
    Given ClaudeCodeUI reports git status "clean"
    When the status is refreshed
    Then the display should show a checkmark icon
    And the git indicator should be green

  Scenario: Handle API timeout gracefully
    Given the ClaudeCodeUI API is not responding
    When a status refresh is attempted
    Then the display should show a connection error icon
    And the last known status should remain visible
    And an automatic retry should be scheduled in 30 seconds

  Scenario: Display device name on outer ring
    Given the current device is "home"
    When viewing the status screen
    Then "HOME" should be displayed on the top arc of the screen
