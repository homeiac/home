# features/p1_proactive_briefing.feature
# Priority: P1 - Ambient Intelligence
# Use Case: P1-3 Proactive briefing on room entry

Feature: Proactive briefing on room entry
  As a user entering a room
  I want to be briefed on pending alerts automatically
  So that I'm aware of issues without needing to ask

  Background:
    Given the MQTT broker is running at "mqtt.homelab"
    And AtomS3R is in the living room
    And Frigate is running with face recognition enabled

  # Basic Briefing
  @atoms3r @p1 @happy_path
  Scenario: Briefing when recognized family member enters
    Given no presence has been detected in the last 10 minutes
    And there are retained messages:
      | topic                      | payload_summary                              |
      | claude/home/status         | git_dirty: 2, sessions: 1                    |
      | claude/home/notification   | priority: warning, title: K8s pod restarted  |
    When Frigate detects a person in "living_room" camera
    And AtomS3R camera identifies "G" with confidence > 0.9
    Then AtomS3R should publish to "presence/atoms3r/detected":
      | field      | value       |
      | person     | G           |
      | confidence | 0.95        |
      | camera     | living_room |
    And within 2 seconds, AtomS3R should speak:
      """
      Welcome back. You have 2 uncommitted files, and there's a K8s warning: pod restarted.
      """

  @atoms3r @p1
  Scenario: Briefing prioritizes critical alerts
    Given there are multiple notifications:
      | priority | title                |
      | critical | K8s CrashLoopBackOff |
      | warning  | Uncommitted changes  |
      | info     | Task completed       |
    When G enters the living room
    Then the briefing should mention the critical alert first
    And the info notification should NOT be mentioned (low priority)

  @atoms3r @p1
  Scenario: All healthy - brief acknowledgment only
    Given claude/home/status shows:
      | field     | value |
      | git_dirty | 0     |
      | sessions  | 0     |
    And there are no pending notifications
    When G enters the room
    Then AtomS3R should speak "Welcome back. All systems healthy."
    And the briefing should be short (< 5 seconds)

  # Cooldown and Deduplication
  @atoms3r @p1 @happy_path
  Scenario: No repeat briefing within cooldown period
    Given G was detected 2 minutes ago
    And a briefing was already spoken
    When G is detected again in the same room
    Then AtomS3R should NOT speak a briefing
    And no duplicate presence event should be published

  @atoms3r @p1
  Scenario: New briefing after cooldown expires
    Given G was detected 15 minutes ago
    And a new critical notification has arrived since then
    When G enters the room
    Then AtomS3R should speak a new briefing
    And the briefing should only mention new information

  @atoms3r @p1
  Scenario: Different room triggers new briefing
    Given G was detected in living_room 5 minutes ago
    And office has different alerts
    When G is detected in office
    Then AtomS3R in office should provide office-specific briefing
    And the cooldown is per-room, not global

  # Multiple Family Members
  @atoms3r @p1
  Scenario: Different briefings for different people
    Given user preferences:
      | person | interests                    |
      | G      | k8s, claude, infrastructure  |
      | Asha   | home automation, calendar    |
    When Asha enters the room
    Then the briefing should focus on Asha's interests
    And should not mention k8s details unless critical

  @atoms3r @p1
  Scenario: Guest mode - minimal briefing
    Given a person is detected but not recognized
    And confidence < 0.5
    When the unknown person is in the room
    Then AtomS3R should NOT provide a system briefing
    But should still log the presence event

  # Voice PE Integration
  @voice_pe @p1
  Scenario: Voice PE can provide briefing if AtomS3R unavailable
    Given AtomS3R is offline in living room
    And Voice PE is online in kitchen
    When G enters the kitchen
    Then Voice PE should provide the briefing via Home Assistant automation
    And the briefing content should be equivalent

  # Time-Aware Briefing
  @atoms3r @p1
  Scenario: Morning briefing includes overnight events
    Given the time is 7:00 AM
    And there were 3 events overnight
    When G enters the room for first time today
    Then the briefing should summarize overnight activity
    And mention any tasks that completed while away

  @atoms3r @p1
  Scenario: Late night - quieter briefing
    Given the time is 11:00 PM
    And there are non-critical notifications
    When G enters the room
    Then AtomS3R should speak at reduced volume
    And only mention critical issues

  # Context Awareness
  @atoms3r @p1
  Scenario: Briefing includes recently started task
    Given claude/home/status shows active_task: "Running pytest"
    And the task started 5 minutes ago
    When G enters the room
    Then the briefing should mention "pytest is still running, started 5 minutes ago"

  @atoms3r @p1
  Scenario: Briefing adapts to task completion
    Given a task was running when G left
    And the task completed while G was away
    When G enters the room
    Then the briefing should mention the task completed
    And include the result (success/failure)
