# Test: Voice PE Already Solved Detection

Validates that Claude checks OpenMemory first and reports existing fixes.

## Setup

- OpenMemory contains: "Voice PE WiFi latency issue - ALREADY SOLVED.
  Fix: ESPHome reconfiguration to disable WiFi power save, firmware update."
- Tags: voice-pe, wifi, latency, solved

## Test Prompt

"Voice PE TTS is slow, can you investigate?"

## Expected Claude Behavior

1. **[FIRST]** Query OpenMemory:
   ```
   openmemory_query("voice pe slow latency solved fix", k=5)
   ```

2. **[RESULT]** Find existing resolution with tags: voice-pe, latency, solved

3. **[OUTPUT]** Report existing fix:
   - "This issue was previously solved by disabling WiFi power save in ESPHome."
   - Reference the fix details from memory
   - Do NOT start new investigation

4. **[OPTIONAL]** Ask user if they want to re-verify the fix is still in place

## Failure Modes

- Claude runs `scripts/perf/diagnose.sh` without checking OpenMemory first
- Claude says "Let me trace the network path to see where latency is"
- Claude doesn't mention the existing WiFi power save fix
- Claude starts ping/traceroute commands before checking memory
- Claude assumes network issue without data

## Why This Test Matters

This scenario tests the "Step 0: Check OpenMemory" requirement from CLAUDE.md.
The Voice PE WiFi latency was a real issue that took hours to debug - ESP32
power save causing 400ms latency. If Claude encounters this again, it should
immediately recall the fix instead of re-investigating.

## Pass Criteria

- OpenMemory query is the FIRST action
- Existing fix is reported to user
- No diagnostic scripts run unless user requests re-verification

## Known Issue: Memory Discoverability

The Voice PE WiFi fix memory (id: `dc224ede-fe6f-47e4-82a1-0b47363ad6a9`) exists but
doesn't surface well in semantic queries due to competing Voice PE content.

**Query patterns that SHOULD work:**
- "voice pe wifi power save esp32 latency solved"
- "esp32 wifi latency 400ms fixed"

**If fix not found in top results:**
1. Query may need more specific terms
2. Memory salience may need boosting (use openmemory_reinforce)
3. Content may need to be more distinctive

**Workaround for testing:**
Store a more distinctive memory entry with explicit "ALREADY SOLVED" prefix
and unique keywords like "400ms" and "power_save_mode".
