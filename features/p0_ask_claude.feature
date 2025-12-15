# features/p0_ask_claude.feature
# Priority: P0 - Foundation
# Use Case: P0-1 Ask Claude from anywhere

Feature: Ask Claude from anywhere
  As a user away from my laptop
  I want to ask Claude questions via voice or text
  So that I can get information without opening my computer

  Background:
    Given the MQTT broker is running at "mqtt.homelab"
    And claude-code-webui is connected and subscribed to "claude/command"
    And the home server status shows 3 uncommitted files

  # Voice PE Integration
  @voice_pe @p0 @happy_path
  Scenario: Ask git status via Voice PE
    Given Voice PE is connected to Home Assistant
    When I say "Hey Claude, what is the git status?"
    Then a command should be published to "claude/command" with:
      | field   | value                     |
      | source  | voice_pe                  |
      | server  | home                      |
      | type    | chat                      |
      | message | what is the git status?   |
    And claude-code-webui should receive the command within 1 second
    And within 5 seconds, a response should be published to "claude/home/response"
    And the response should contain "uncommitted files"
    And Voice PE should speak the response via TTS

  @voice_pe @p0
  Scenario: Ask about specific task
    Given Voice PE is connected to Home Assistant
    When I say "Claude, what are you working on?"
    Then a command should be published with type "chat"
    And within 5 seconds, a response should describe the active task or "idle"

  # Cardputer Integration
  @cardputer @p0 @happy_path
  Scenario: Ask git status via Cardputer
    Given Cardputer is connected to MQTT broker
    And Cardputer is displaying the command input screen
    When I type "git status" and press Enter
    Then a command should be published to "claude/command" with:
      | field   | value       |
      | source  | cardputer   |
      | server  | home        |
      | type    | chat        |
    And the Cardputer display should show "Sending..."
    And within 5 seconds, the display should show the response
    And the response should not use TTS

  @cardputer @p0
  Scenario: Send multi-word command via Cardputer
    Given Cardputer is connected to MQTT broker
    When I type "deploy frigate to k8s" and press Enter
    Then the full message should be published correctly
    And punctuation and spaces should be preserved

  # Puck Integration
  @puck @p0 @happy_path
  Scenario: Refresh status via Puck button press
    Given Puck is connected and displaying home server status
    And the displayed status shows 1 session
    When I press the encoder button
    Then a command should be published to "claude/command" with:
      | field  | value   |
      | source | puck    |
      | type   | refresh |
    And the LED ring should show breathing white (loading)
    And within 2 seconds, the display should update with fresh data
    And the LED should return to solid green if healthy

  @puck @p0
  Scenario: Long press for acknowledgment
    Given Puck is displaying a task notification
    And the notification has task_id "task_1234"
    When I long-press the encoder for 2 seconds
    Then a command should be published with:
      | field   | value      |
      | source  | puck       |
      | type    | ack        |
      | task_id | task_1234  |
    And the notification should be dismissed from display

  # AtomS3R Integration
  @atoms3r @p0
  Scenario: Ask Claude via AtomS3R wake word
    Given AtomS3R is in the living room
    And wake word detection is enabled
    When I say "Hey Claude, check the k8s cluster"
    Then AtomS3R should capture the audio
    And a command should be published with source "atoms3r"
    And AtomS3R should speak the response

  # Server Selection
  @multi_server @p0
  Scenario: Command targets home server by default
    Given both home and work servers are online
    When I send a command without specifying server
    Then the command should target server "home"

  @multi_server @p0
  Scenario: Explicitly target work server
    Given work server is online
    When I say "Claude work, what's the build status?"
    Then the command should be published with server "work"

  @multi_server @p0
  Scenario: Fallback when work server offline
    Given work server is offline
    When I try to send a command to work server
    Then the device should display "Work server offline"
    And the command should NOT be published
