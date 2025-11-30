Feature: Haptic and Audio Feedback
  As a user interacting with the puck
  I want tactile and audio confirmation of my actions
  So that I have confidence my inputs are registered

  Background:
    Given the puck is powered on
    And sound is enabled in settings
    And haptics are enabled in settings

  # ============================================
  # Encoder Rotation Feedback
  # ============================================

  Scenario: Encoder detent produces click sound
    When I rotate the encoder by one detent
    Then the buzzer should play a short click (1000Hz, 10ms)
    And the vibration motor should not activate

  Scenario: Fast rotation produces rapid clicks
    When I rotate the encoder quickly through 5 detents
    Then 5 clicks should play in rapid succession
    And the clicks should not overlap or distort

  Scenario: Sound disabled skips audio feedback
    Given sound is disabled in settings
    When I rotate the encoder by one detent
    Then no sound should play
    And the visual feedback should still occur

  # ============================================
  # Button Press Feedback
  # ============================================

  Scenario: Short press produces confirmation beep
    When I press and release the encoder button within 500ms
    Then the buzzer should play a confirmation tone
    And the vibration motor should pulse once lightly

  Scenario: Long press produces distinct feedback
    When I hold the encoder button for 3 seconds
    Then at 3 seconds the buzzer should play a long tone
    And the vibration motor should pulse once strongly
    And visual feedback should indicate long press registered

  Scenario: Side button press feedback
    When I press the side button
    Then the buzzer should play a click sound
    And visual feedback should indicate the action

  # ============================================
  # Alert Notifications
  # ============================================

  Scenario: Critical alert produces strong haptic burst
    Given Home Assistant reports a P1 critical alert
    When the alert is received
    Then the vibration motor should pulse 3 times strongly
    And the buzzer should play an alert tone
    And the timing should be: pulse-pause-pulse-pause-pulse

  Scenario: High priority alert produces moderate haptic
    Given there are 4 active alerts (P2 high)
    When the alert threshold is exceeded
    Then the vibration motor should pulse 2 times moderately
    And the buzzer should play a warning tone

  Scenario: Low priority notifications are silent
    Given Home Assistant has new notifications (P4 low)
    When the notification is received
    Then no vibration should occur
    And no sound should play
    And only visual indication (LED flash) should occur

  # ============================================
  # Connection State Feedback
  # ============================================

  Scenario: WiFi connected plays success tone
    Given the puck was connecting to WiFi
    When WiFi connection succeeds
    Then the buzzer should play ascending tone (1000Hz → 2000Hz)
    And the vibration motor should pulse once gently

  Scenario: WiFi disconnected plays failure tone
    Given the puck was connected to WiFi
    When WiFi connection is lost
    Then the buzzer should play descending tone (2000Hz → 1000Hz)
    And the LED ring should indicate connection error

  Scenario: API error produces error feedback
    Given a status refresh is in progress
    When the HTTP request fails
    Then the buzzer should play a low error tone
    And the vibration motor should double-pulse

  # ============================================
  # Settings Feedback
  # ============================================

  Scenario: Settings saved produces confirmation
    When I change a setting and it saves
    Then the vibration motor should pulse once gently
    And the buzzer should play a soft confirmation

  Scenario: Factory reset warning feedback
    Given I am in settings mode
    When I triple-press the side button
    Then the buzzer should play a warning pattern
    And the display should show confirmation prompt
    And no action should be taken until confirmed

  # ============================================
  # Accessibility Options
  # ============================================

  Scenario: Haptics disabled skips vibration
    Given haptics are disabled in settings
    When an alert is received
    Then no vibration should occur
    And audio feedback should still play
    And LED feedback should still occur

  Scenario: Silent mode disables all audio
    Given the puck is in silent mode
    When I interact with any control
    Then no audio should play
    And haptic feedback should still work
    And LED feedback should still work

  Scenario: Volume levels are configurable
    Given click volume is set to 30%
    And alert volume is set to 100%
    When I rotate the encoder
    Then the click should play at 30% volume
    When an alert is received
    Then the alert should play at 100% volume
