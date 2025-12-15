# features/p0_task_notifications.feature
# Priority: P0 - Foundation
# Use Case: P0-2 Know when Claude is done

Feature: Know when Claude is done
  As a user who started a task
  I want to be notified when it completes or fails
  So that I don't have to keep checking my laptop

  Background:
    Given the MQTT broker is running at "mqtt.homelab"
    And all devices are connected and subscribed to task events

  # Task Completion
  @all_devices @p0 @happy_path
  Scenario: Task completion notifies all devices
    Given a task "pytest tests/" is running with id "task_1234"
    When the task completes successfully after 45 seconds
    Then a message should be published to "claude/home/task/task_1234" with:
      | field       | value                      |
      | event       | completed                  |
      | description | pytest tests/ - 42 passed  |
      | duration_ms | 45000                      |
    And a notification should be published with priority "info"
    And all subscribed devices should receive within 2 seconds

  @puck @p0 @happy_path
  Scenario: Puck shows task completion
    Given Puck is displaying home server status
    When a task "pytest" completes successfully
    Then Puck LED should flash green for 2 seconds
    And Puck display should show "✓ pytest (45s)"
    And after 10 seconds, display should return to normal status

  @voice_pe @p0 @happy_path
  Scenario: Voice PE announces task completion
    Given Voice PE is connected to Home Assistant
    When a task "pytest" completes successfully with 42 passed tests
    Then Voice PE should speak "Claude finished pytest, all tests passed"
    And the LED ring should pulse green briefly

  @atoms3r @p0
  Scenario: AtomS3R announces if user present
    Given AtomS3R detected a person within the last 5 minutes
    When a task completes
    Then AtomS3R should speak the completion notification
    And if no presence detected, AtomS3R should stay silent

  @cardputer @p0
  Scenario: Cardputer shows notification
    Given Cardputer is displaying idle screen
    When a task completes
    Then Cardputer should vibrate briefly
    And the display should show task completion for 10 seconds
    And then return to previous screen

  # Task Failure
  @all_devices @p0 @happy_path
  Scenario: Task failure triggers critical alert
    Given a task "kubectl apply" is running with id "deploy_001"
    When the task fails with error "ImagePullBackOff"
    Then a message should be published to "claude/home/task/deploy_001" with:
      | field | value                                              |
      | event | failed                                             |
      | error | Error: ImagePullBackOff - registry.homelab/app:latest |
    And a notification should be published with priority "critical"

  @puck @p0 @happy_path
  Scenario: Puck shows task failure prominently
    Given a task "deploy" fails
    Then Puck LED should pulse red continuously
    And Puck display should show "✗ deploy: ImagePullBackOff"
    And the red pulse should continue until user acknowledges

  @voice_pe @p0
  Scenario: Voice PE announces critical failure
    Given Voice PE is idle
    When a critical task failure notification is published
    Then Voice PE should immediately speak the failure
    And the LED ring should turn solid red
    And volume should be elevated for critical alerts

  # Notification Acknowledgment
  @puck @p0
  Scenario: User acknowledges notification on Puck
    Given Puck is showing a failure notification
    When user long-presses the encoder
    Then an acknowledgment should be published
    And the red LED should stop pulsing
    And the display should return to normal status

  @all_devices @p0
  Scenario: Acknowledgment syncs across devices
    Given a critical notification is displayed on all devices
    When user acknowledges on Puck
    Then all devices should receive the ack message
    And all devices should clear the notification

  # Long-running Tasks
  @puck @p0
  Scenario: Display updates for long-running task
    Given a task "build docker image" is running
    And the task has been running for 5 minutes
    Then Puck should show "Building... 5m"
    And LED should show breathing amber (in progress)

  @atoms3r @p0
  Scenario: Proactive update for very long task
    Given a task has been running for 15 minutes
    And user enters the room
    Then AtomS3R should proactively say "Still building. 15 minutes elapsed."
