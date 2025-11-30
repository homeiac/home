Feature: Touch Screen Gestures
  As a user who prefers touch interaction
  I want to use touch gestures on the round display
  So that I can interact without using the rotary encoder

  Background:
    Given the puck display supports capacitive touch
    And the puck is showing a status view

  # ============================================
  # Tap Gestures
  # ============================================

  Scenario: Center tap refreshes status
    Given the display is showing Claude Code status
    When I tap the center of the screen
    Then a status refresh should be triggered
    And the display should show a loading indicator

  Scenario: Tap on entity toggles it
    Given the display is showing Home Assistant view
    And "switch.office_lights" is displayed as "OFF"
    When I tap on the office lights entity
    Then a toggle request should be sent to Home Assistant
    And the entity should show pending state
    And update when the response arrives

  Scenario: Tap on truncated text expands it
    Given the last task text is truncated to one line
    When I tap on the task text area
    Then a popup should show the full task text
    And the popup should auto-dismiss after 5 seconds

  Scenario: Tap outside popup dismisses it
    Given a popup is showing full task text
    When I tap outside the popup area
    Then the popup should dismiss
    And the normal view should restore

  # ============================================
  # Swipe Gestures
  # ============================================

  Scenario: Swipe left goes to next view
    Given the display is showing Claude Code view for "home"
    When I swipe left across the screen
    Then the display should transition to the next device or view
    And the transition should animate smoothly

  Scenario: Swipe right goes to previous view
    Given the display is showing Home Assistant view
    When I swipe right across the screen
    Then the display should transition back to Claude Code view
    And the device should be the last viewed Claude Code device

  Scenario: Swipe up scrolls content if scrollable
    Given the display is showing a list of entities
    And there are more entities than fit on screen
    When I swipe up on the screen
    Then the list should scroll up
    And reveal additional entities

  Scenario: Swipe down on status view shows time
    Given the display is showing any status view
    When I swipe down from the top
    Then the current time and date should overlay
    And show "Last updated: X minutes ago"
    And auto-dismiss after 3 seconds

  # ============================================
  # Long Press
  # ============================================

  Scenario: Long press on entity shows details
    Given the display is showing Home Assistant view
    When I long press on the CPU temperature gauge
    Then a detail popup should show:
      | Field        | Example Value      |
      | Current      | 65°C               |
      | Min (24h)    | 42°C               |
      | Max (24h)    | 78°C               |
      | Entity ID    | sensor.server_cpu  |

  Scenario: Long press anywhere enters settings
    Given the display is showing any status view
    When I long press anywhere for 3 seconds
    Then the display should enter settings mode
    And the LED ring should show rainbow animation

  # ============================================
  # Edge Cases
  # ============================================

  Scenario: Accidental touch during rotation is ignored
    Given I am rotating the encoder
    And my palm touches the edge of the screen
    When the touch is detected
    Then no touch action should be triggered
    And only the rotation should be processed

  Scenario: Multi-touch is not supported
    Given I place two fingers on the screen
    When both touches are detected
    Then only the first touch should be processed
    Or no action should be taken (implementation defined)

  Scenario: Touch sensitivity is adjustable
    Given touch sensitivity is set to "high"
    Then light touches should register
    Given touch sensitivity is set to "low"
    Then only firm touches should register

  Scenario: Touch during loading is queued or ignored
    Given a status refresh is in progress
    When I tap the screen
    Then the tap should either be queued until refresh completes
    Or gracefully ignored with no side effects
