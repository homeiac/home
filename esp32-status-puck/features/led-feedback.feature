Feature: LED Ring Feedback
  As a user monitoring multiple environments
  I want the RGB LED ring to show status at a glance
  So that I can see system health without looking at the screen

  Background:
    Given the puck has a 5-LED WS2812 ring
    And the puck is powered on and connected

  # ============================================
  # Status Indication
  # ============================================

  Scenario: All systems healthy shows green ring
    Given all Claude Code devices report 0 dirty repos
    And Home Assistant reports K8s cluster healthy
    And CPU temperature is below 70°C
    When the status is refreshed
    Then all 5 LEDs should be solid green
    And the brightness should match the configured level

  Scenario: Minor issues show amber LEDs proportionally
    Given 2 Claude Code devices have dirty git repos
    When the status is refreshed
    Then 2 LEDs should be amber
    And 3 LEDs should be green

  Scenario: Critical alert triggers red pulsing
    Given Home Assistant reports K8s cluster is down
    When the status is refreshed
    Then all 5 LEDs should pulse red
    And the pulse rate should be 1Hz

  Scenario: High CPU temperature shows red alert
    Given Home Assistant reports CPU temperature 92°C
    When the status is refreshed
    Then all 5 LEDs should pulse red
    And the alert priority should be P1

  # ============================================
  # Device Identity
  # ============================================

  Scenario: Device switch shows accent color briefly
    Given device "home" has accent color blue
    And device "work" has accent color orange
    And the current device is "home"
    When I rotate the knob clockwise
    Then the LED ring should flash orange briefly
    And then return to status indication colors

  Scenario: Each device has a unique accent color
    Given 3 devices are configured
    When I cycle through all devices
    Then each device should show a distinct accent color flash
    And the colors should be visually distinguishable

  # ============================================
  # Activity States
  # ============================================

  Scenario: Loading state shows breathing white
    Given a status refresh is in progress
    Then the LED ring should show breathing white animation
    And the animation should be smooth (no flickering)

  Scenario: WiFi connecting shows slow blue pulse
    Given the puck is connecting to WiFi
    Then the LED ring should pulse blue slowly
    And the pulse rate should be 0.5Hz

  Scenario: Settings mode shows rainbow chase
    When I enter settings mode
    Then the LED ring should show rainbow chase animation
    And the animation should cycle through all colors

  Scenario: WiFi setup shows solid blue
    Given the puck is in WiFi setup mode
    Then all 5 LEDs should be solid blue
    And they should remain steady (no animation)

  # ============================================
  # Idle and Power Saving
  # ============================================

  Scenario: LEDs dim after inactivity timeout
    Given the dim timeout is set to 60 seconds
    And 60 seconds have passed with no interaction
    Then the LED brightness should reduce to dim level
    And the status colors should still be visible

  Scenario: Interaction wakes LEDs from dim state
    Given the LEDs are in dim state
    When I rotate the encoder
    Then the LEDs should return to full brightness immediately
    And the dim timeout should reset

  Scenario: LEDs turn off in full sleep mode
    Given the sleep timeout is set to 5 minutes
    And 5 minutes have passed with no interaction
    Then all LEDs should turn off
    And power consumption should be minimized
