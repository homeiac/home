# Package Detection Debug Plan

## User Symptoms
1. Getting alerts for "person detected" even when no package
2. LED has NEVER turned blue (not once)

## Hypothesis Tree

### H1: The `person_left` trigger never fires
- **Evidence needed**: Check HA logs for `SPAN_START:package_check` - if never appears, trigger isn't firing
- **Test**: Walk to door, wait, walk away - check logs for `person_left` events
- **Why this matters**: If trigger doesn't fire, package check never runs

### H2: LLM Vision is always saying "NO" to packages
- **Evidence needed**: Check logs for `EVENT:llm_response | result=` in `package_check` span
- **Test**: Manually call LLM Vision with a known package image
- **Why this matters**: If LLM always says NO, LED logic never executes

### H3: LED service call is failing silently
- **Evidence needed**: Check if `EVENT:led_on` log ever appears
- **Test**: Run `./test-voice-pe-led.sh blue 10` and physically observe LED
- **Why this matters**: Hardware/integration issue vs logic issue

### H4: Notification logic is wrong (confirmed)
- **Root cause**: `person_arrived` ALWAYS sends notification
- **User wants**: Notification ONLY when package detected
- **Fix**: Remove or conditionalize the `person_arrived` notification

## Debug Sequence

### Step 1: Verify LED hardware works
```bash
./scripts/package-detection/test-voice-pe-led.sh blue 10
```
Expected: LED turns blue for 10 seconds

### Step 2: Check historical logs for package_check
```bash
# Get recent package detection logs
curl -s -H "Authorization: Bearer $HA_TOKEN" \
  "http://192.168.4.240:8123/api/logbook" | \
  jq '.[] | select(.name == "Package Detection")' | \
  grep -E "package_check|llm_response"
```
Expected: See if person_left ever triggered and what LLM returned

### Step 3: Query current input_text states
```bash
# Check what's stored
curl -s -H "Authorization: Bearer $HA_TOKEN" \
  "http://192.168.4.240:8123/api/states/input_text.pending_notification_type"
curl -s -H "Authorization: Bearer $HA_TOKEN" \
  "http://192.168.4.240:8123/api/states/input_boolean.has_pending_notification"
```

### Step 4: Test LLM Vision manually with package image
- Take a photo with a visible package
- Call LLM Vision directly
- See if it returns "YES"

### Step 5: Fix notification logic
If user confirms they want PACKAGE-ONLY alerts:
- Remove the notification from `person_arrived` branch
- Only notify in `person_left` when package detected
- Consider a different alert for "person detected, checking for package..."

## Critique Questions for This Plan

1. Am I assuming the automation is deployed correctly? Should verify which version is active in HA.
2. Am I assuming the logbook API will have enough history? Might need to check trace files instead.
3. Am I assuming input_boolean and input_text helpers exist? Should verify.
4. The `person_left` trigger has a 3-second delay - is this enough for delivery drivers who drop and run?
5. The LLM prompt says "on this porch/doorstep" - what if the package is visible but not exactly "on" the porch?
6. Should I check if the automation is even ENABLED?
7. Is the LED entity ID correct and is the device online?
