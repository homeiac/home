# features/failure_handling.feature
# Priority: Critical - All implementations must handle failures gracefully

Feature: Graceful failure handling
  As a system
  I must handle failures gracefully
  So that devices remain useful even when things go wrong

  Background:
    Given the MQTT broker is running at "mqtt.homelab"

  # Malformed Data
  @resilience @all_devices
  Scenario: Device handles malformed JSON
    Given Puck is connected and displaying status
    When a malformed JSON message is published to "claude/home/status":
      """
      {"server":"home", BROKEN JSON HERE
      """
    Then Puck should NOT crash
    And Puck should display "⚠ Parse error" or continue showing last valid data
    And Puck should log the error for debugging
    And Puck should continue processing subsequent valid messages

  @resilience @all_devices
  Scenario: Device handles empty payload
    Given Puck is connected
    When an empty message is published to "claude/home/status"
    Then Puck should NOT crash
    And Puck should ignore the message
    And display should remain unchanged

  @resilience @all_devices
  Scenario: Device handles missing required fields
    Given Puck is connected
    When a message missing required fields is published:
      """
      {"server":"home","online":true}
      """
    Then Puck should reject the message (missing sessions, git_dirty)
    And Puck should display previous valid status
    And Puck should NOT crash

  @resilience @all_devices
  Scenario: Device handles unknown field values
    Given Puck is connected
    When a message with unknown server is published:
      """
      {"server":"staging","online":true,"sessions":1,"git_dirty":0,"last_activity":"2025-12-14T10:00:00Z"}
      """
    Then Puck should ignore the unknown server
    And Puck should NOT crash or display corrupted data

  # Stale Data
  @resilience @all_devices
  Scenario: Device shows stale indicator for old data
    Given the retained status message is 24 hours old
    When Puck connects and receives the retained message
    Then Puck should display the status with a "⏰" or "?" stale indicator
    And Puck should show "Last update: 24h ago"
    And LED should be amber (not green) to indicate uncertainty

  @resilience @all_devices
  Scenario: Device handles extremely old data
    Given the retained message has timestamp from 2020
    When Puck receives this message
    Then Puck should display "Status stale - requesting refresh"
    And Puck should automatically publish a refresh command
    And if no fresh data within 30s, display "Server unreachable"

  # Server Offline
  @resilience @all_devices @happy_path
  Scenario: Device handles work server offline gracefully
    Given claude/work/status shows online: false
    When user rotates Puck to view work server
    Then Puck should display "Work: Offline"
    And Puck should display last known activity time
    And LED should be dim white (not red - offline is expected)
    And there should be no error beep or alarming indication

  @resilience @all_devices
  Scenario: Device handles home server going offline
    Given Puck was showing home server status
    When home server publishes online: false
    Then Puck should display "Home: Offline"
    And LED should change to dim amber
    And if critical notification was active, it should remain visible

  # Network Resilience
  @resilience @all_devices @happy_path
  Scenario: Device reconnects after broker restart
    Given Puck is connected and receiving messages
    When the MQTT broker restarts
    Then Puck should detect disconnection within 5 seconds
    And Puck should display "Reconnecting..."
    And LED should show breathing amber
    And Puck should reconnect within 10 seconds
    And Puck should resubscribe to all topics
    And Puck should receive retained messages again
    And Puck should publish "devices/puck/status" with status: "connected"

  @resilience @all_devices
  Scenario: Device handles repeated connection failures
    Given the MQTT broker is unreachable
    When Puck attempts to connect 5 times
    Then Puck should use exponential backoff (2s, 4s, 8s, 16s, 32s)
    And Puck should display "Broker unreachable - retrying"
    And Puck should continue retrying indefinitely
    And Puck should remain responsive to button input

  @resilience @all_devices
  Scenario: Device handles WiFi disconnect
    Given Puck is connected via WiFi
    When WiFi connection is lost
    Then Puck should detect within 10 seconds
    And Puck should attempt WiFi reconnection
    And display should show "WiFi reconnecting..."
    And on WiFi restore, MQTT should auto-reconnect

  # Message Flood
  @resilience @all_devices
  Scenario: Device handles message flood
    Given Puck is connected
    When 100 task messages are published in 1 second
    Then Puck should NOT crash
    And Puck should process messages (may skip intermediate ones)
    And Puck should show latest status accurately
    And Puck should remain responsive to button input
    And memory usage should remain stable

  @resilience @all_devices
  Scenario: Device handles large payload
    Given Puck is connected
    When a message with 10KB payload is published
    Then Puck should either:
      | option | behavior                    |
      | A      | Truncate and parse partial  |
      | B      | Reject with size error      |
    And Puck should NOT crash or hang
    And Puck should continue processing normal messages

  # QoS and Delivery
  @resilience @mqtt
  Scenario: Critical notifications use QoS 1
    Given Puck has 500ms network latency
    When a critical notification is published with QoS 1
    Then the message should be delivered despite latency
    And Puck should acknowledge receipt
    And if ACK fails, broker should retry delivery

  @resilience @mqtt
  Scenario: Status messages handle QoS 1 retained
    Given Puck was offline for 1 hour
    When Puck reconnects
    Then Puck should receive retained status immediately
    And the status should reflect last known state

  # Graceful Degradation
  @resilience @graceful_degradation
  Scenario: Device works without optional features
    Given AtomS3R camera is malfunctioning
    When presence detection fails
    Then AtomS3R should still:
      | feature                | status    |
      | Receive notifications  | Working   |
      | Speak alerts           | Working   |
      | MQTT connection        | Working   |
    And AtomS3R should report camera: "unavailable"

  @resilience @graceful_degradation
  Scenario: System works with partial device availability
    Given Puck is offline
    And Voice PE is online
    When a critical notification is published
    Then Voice PE should still announce the alert
    And system should not fail due to Puck being offline

  # Recovery
  @resilience @recovery
  Scenario: Device recovers state after crash
    Given Puck crashed and rebooted
    When Puck reconnects to MQTT
    Then Puck should request current status via refresh command
    And Puck should restore last known view (home/work)
    And any pending acknowledgments should be re-evaluated

  @resilience @recovery
  Scenario: Devices sync state after network partition
    Given network partition caused 5 minutes of isolation
    When network is restored
    Then all devices should receive retained messages
    And devices should reconcile any missed notifications
    And system should reach consistent state within 30 seconds
