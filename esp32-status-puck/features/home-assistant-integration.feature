Feature: Home Assistant Integration
  As a homelab operator
  I want to see Home Assistant status alongside Claude Code status
  So that I have a unified view of my environments

  Background:
    Given the puck is connected to WiFi
    And Home Assistant is configured at "http://homeassistant.local:8123"
    And a valid HA long-lived access token is configured

  Scenario: Display HA entity status in secondary ring
    Given Home Assistant has entity "sensor.server_cpu_temp" with value "65"
    When the status is refreshed
    Then the outer ring should show a temperature arc
    And the arc should represent 65 degrees

  Scenario: Rotate to HA status view
    Given the puck is showing Claude Code status for "home"
    When I rotate clockwise past all Claude Code devices
    Then the display should switch to Home Assistant view
    And show configured HA dashboard entities

  Scenario: Touch to toggle HA switch entity
    Given the display is showing HA entity "switch.office_lights" as "off"
    When I touch the entity on screen
    Then a toggle request should be sent to Home Assistant
    And the display should show a pending state
    And update when HA confirms the new state

  Scenario: Display HA notification badge
    Given Home Assistant has 3 unread notifications
    When viewing any status screen
    Then a notification badge should appear
    And show "3" in the badge

  Scenario: Handle HA authentication failure
    Given the HA access token is expired
    When a status refresh is attempted
    Then the display should show an auth error icon
    And prompt to reconfigure via settings
