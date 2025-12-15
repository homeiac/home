# features/p2_unknown_person.feature
# Priority: P2 - Security/Awareness
# Use Case: P2-6 Unknown person alert

Feature: Unknown person alert
  As a homeowner
  I want to be alerted when an unknown person is detected
  So that I'm aware of potential security concerns

  Background:
    Given the MQTT broker is running at "mqtt.homelab"
    And Frigate is running with face recognition enabled
    And family members "G" and "Asha" are registered in Frigate
    And all devices are connected and subscribed

  # Detection and Alert
  @security @p2 @happy_path
  Scenario: Unknown person at front door triggers alert
    When a person is detected at "front_door" camera
    And the face does not match any registered family member
    And confidence for recognition < 0.5
    Then Frigate should publish a person event with sub_label: null
    And a presence event should be published with person: "unknown"
    And a critical notification should be published:
      | field    | value                             |
      | priority | critical                          |
      | title    | Unknown person detected           |
      | message  | Unrecognized person at front door |
      | actions  | view_camera, dismiss              |
    And the notification should include:
      | field         | description                          |
      | thumbnail_url | URL to Frigate snapshot              |
      | camera        | front_door                           |
      | timestamp     | Time of detection                    |

  @security @p2 @happy_path
  Scenario: All devices alert on unknown person
    Given an unknown person is detected
    Then all devices should alert:
      | device    | alert_type                     |
      | Puck      | Red LED pulse + display alert  |
      | Voice PE  | Spoken warning + red LED       |
      | AtomS3R   | Spoken warning                 |
      | Cardputer | Vibrate + display notification |

  @puck @p2
  Scenario: Puck shows unknown person alert
    Given an unknown person alert is published
    Then Puck LED should pulse red urgently
    And display should show "⚠ Unknown Person"
    And display should show camera name and time
    And alert should persist until acknowledged

  @voice_pe @p2
  Scenario: Voice PE announces security alert
    Given an unknown person alert is published
    Then Voice PE should immediately speak:
      """
      Security alert: Unknown person detected at front door.
      """
    And the announcement should use elevated volume
    And LED ring should turn solid red

  @atoms3r @p2
  Scenario: AtomS3R provides visual and audio alert
    Given an unknown person alert is published
    And a family member is present in the room
    Then AtomS3R should speak the security alert
    And if AtomS3R has display, should show thumbnail

  # No False Positives for Known People
  @security @p2 @happy_path
  Scenario: Known person does not trigger security alert
    Given "Asha" is a registered family member
    When "Asha" is detected at "front_door" camera
    And face recognition confidence > 0.8
    Then NO critical notification should be published
    And Puck LED should remain green
    And no security announcement should be made

  @security @p2
  Scenario: Known person at different camera
    Given "G" is detected at "living_room" camera
    Then a presence event should be published with person: "G"
    And NO security alert should be triggered
    And this should be normal presence detection

  # Edge Cases
  @security @p2
  Scenario: Low confidence on known person
    Given "G" is detected but confidence is 0.6 (borderline)
    Then the system should NOT trigger security alert
    And presence should be logged as "possibly G"
    And no notification to devices (avoid false alarms)

  @security @p2
  Scenario: Multiple unknown people
    Given 2 unknown people are detected simultaneously
    Then only ONE security alert should be sent (deduplicated)
    And the alert should mention "2 unknown people"
    And thumbnail should show both if possible

  @security @p2
  Scenario: Unknown person in non-critical area
    Given an unknown person is detected in "backyard" camera
    And home_mode is "home" (family present)
    Then alert priority should be "warning" not "critical"
    And verbal announcement should be softer

  # Alert Management
  @security @p2
  Scenario: Acknowledge security alert
    Given a security alert is active on all devices
    When user acknowledges on any device
    Then all devices should clear the alert
    And the event should be logged as "acknowledged"
    And LED should return to normal state

  @security @p2
  Scenario: View camera from alert
    Given a security alert is showing on Puck
    When user selects "view_camera" action
    Then system should open Frigate camera view
    And (on Cardputer) display the camera stream if supported

  # Away Mode
  @security @p2
  Scenario: Enhanced alerting when family away
    Given all family members are marked as "away"
    And an unknown person is detected
    Then alert should be marked as "highest priority"
    And push notification should be sent to phones
    And verbal alerts should repeat every 5 minutes until acknowledged

  @security @p2
  Scenario: Expected visitor does not trigger alert
    Given a visitor "delivery" is expected between 2-4 PM
    And an unknown person is detected at 2:30 PM at front door
    Then alert priority should be "info" not "critical"
    And message should mention "Possible expected delivery"
