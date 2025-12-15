# features/p1_glanceable_status.feature
# Priority: P1 - Ambient Intelligence
# Use Case: P1-5 Glanceable status

Feature: Glanceable status on Puck
  As a user glancing at my desk
  I want to see Claude Code status at a glance
  So that I know the system state without interaction

  Background:
    Given the MQTT broker is running at "mqtt.homelab"
    And Puck is connected and subscribed to:
      | topic                   | qos |
      | claude/home/status      | 1   |
      | claude/work/status      | 1   |
      | claude/+/task/+         | 0   |
      | claude/+/notification   | 1   |

  # Initial State
  @puck @p1 @happy_path
  Scenario: Puck displays status on boot
    Given Puck is powered on
    And retained messages exist:
      | topic               | sessions | git_dirty |
      | claude/home/status  | 2        | 1         |
      | claude/work/status  | 0        | 0         |
    When Puck connects to MQTT broker
    Then within 1 second, Puck should receive retained messages
    And display should show "Home: 2 sessions, 1 dirty"
    And LED should be amber (dirty repos present)

  # LED Status Mapping
  @puck @p1 @happy_path
  Scenario Outline: LED color indicates system health
    Given claude/home/status is:
      | field     | value             |
      | git_dirty | <dirty>           |
      | sessions  | <sessions>        |
    And notification priority is "<notification>"
    Then Puck LED should be <led_color>

    Examples:
      | dirty | sessions | notification | led_color     |
      | 0     | 0        | none         | dim white     |
      | 0     | 2        | none         | solid green   |
      | 1     | 1        | none         | amber         |
      | 3     | 1        | none         | amber bright  |
      | 0     | 1        | warning      | amber pulse   |
      | 0     | 1        | critical     | red pulse     |
      | 5     | 0        | critical     | red pulse     |

  # Multi-Server View
  @puck @p1 @happy_path
  Scenario: Rotate to switch between servers
    Given Puck is displaying home server status
    And work server is online
    When I rotate the encoder clockwise
    Then display should switch to work server status
    And LED ring should briefly show work server color (blue)
    And haptic click should confirm rotation

  @puck @p1
  Scenario: Work server offline indicator
    Given work server shows online: false
    When I rotate to work server view
    Then display should show "Work: Offline"
    And display should show last activity timestamp
    And LED should be dim white (not red - offline is not an error)

  @puck @p1
  Scenario: Return to home server after timeout
    Given Puck is displaying work server
    And no interaction for 30 seconds
    Then Puck should automatically return to home view
    And display should show home server status

  # Real-time Updates
  @puck @p1 @happy_path
  Scenario: Display updates instantly on status change
    Given Puck is displaying "1 session, 0 dirty"
    When claude/home/status is published with sessions: 2, git_dirty: 1
    Then within 500ms, display should update to "2 sessions, 1 dirty"
    And LED should change from green to amber

  @puck @p1
  Scenario: Task progress shown in real-time
    Given Puck is displaying normal status
    When a task "pytest" starts
    Then display should show "Running: pytest..."
    And LED should show breathing pattern (activity)

  @puck @p1
  Scenario: Task completion updates display
    Given Puck shows "Running: pytest..."
    When the task completes with 42 passed
    Then display should flash "✓ pytest (45s)"
    And LED should flash green
    And after 5 seconds, return to normal status

  # Notification Display
  @puck @p1
  Scenario: Critical notification overrides normal display
    Given Puck is showing normal status
    When a critical notification is published
    Then display should immediately show the notification
    And LED should pulse red
    And normal status should be temporarily hidden

  @puck @p1
  Scenario: Dismiss notification to return to status
    Given Puck is showing a critical notification
    When I long-press the encoder
    Then notification should be dismissed
    And display should return to normal status
    And LED should return to appropriate color for current status

  # Touch Interaction
  @puck @p1
  Scenario: Tap to refresh
    Given Puck is displaying status
    When I tap the display
    Then a refresh command should be published
    And display should show loading indicator
    And updated status should appear within 2 seconds

  @puck @p1
  Scenario: Swipe for quick actions
    Given Puck is displaying a task notification
    When I swipe right
    Then the notification should be acknowledged
    When I swipe left
    Then action menu should appear (retry, dismiss, details)

  # Stale Data Handling
  @puck @p1
  Scenario: Stale indicator for old data
    Given the retained status message has last_activity > 1 hour ago
    When Puck displays the status
    Then a stale indicator "?" should appear
    And LED should include slow pulse pattern
    And user should see how long ago data was updated

  @puck @p1
  Scenario: Connection lost indicator
    Given Puck loses MQTT connection
    Then display should show "Reconnecting..."
    And LED should show breathing amber
    And on reconnect, display should update immediately
