Feature: Rotary Navigation
  As a developer with multiple Claude Code environments
  I want to rotate the knob to switch between devices
  So that I can quickly check status across home and work machines

  Background:
    Given the puck is connected to WiFi
    And the following devices are configured:
      | name   | url                          |
      | home   | http://192.168.1.100:3000    |
      | work   | http://192.168.1.101:3000    |

  Scenario: Rotate clockwise to next device
    Given the current device is "home"
    When I rotate the knob clockwise
    Then the display should show "work" device status
    And the device indicator should update to "work"

  Scenario: Rotate counter-clockwise to previous device
    Given the current device is "work"
    When I rotate the knob counter-clockwise
    Then the display should show "home" device status
    And the device indicator should update to "home"

  Scenario: Wrap around at end of device list
    Given the current device is "work"
    And "work" is the last device in the list
    When I rotate the knob clockwise
    Then the display should show "home" device status

  Scenario: Press to refresh current device status
    Given the current device is "home"
    And the status was fetched 5 minutes ago
    When I press the knob
    Then a new status request should be sent to "home"
    And the display should show a loading indicator
    And the display should update with fresh status

  Scenario: Long press to enter settings mode
    Given the puck is showing device status
    When I press and hold the knob for 3 seconds
    Then the display should enter settings mode
    And show WiFi configuration options
