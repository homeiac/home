# Ollama Home Assistant Integration - Agent Reference

This document contains verified findings about the HA Ollama conversation integration. Use this when working on Ollama-based voice assistant features.

## Verified Findings (2025-12-13)

### Entity State Reading - Query Phrasing Matters

**CRITICAL**: The ability to read entity states depends on query phrasing, NOT a bug in Ollama.

| Query Pattern | Works? | Example |
|---------------|--------|---------|
| "what is the state of [entity_name]" | ✓ YES | "what is the state of pending_notification_message" |
| "what is [full_entity_id]" | ✗ NO | "what is input_text.pending_notification_message" |
| "what is my [entity_name]" | ✓ YES | "what is my notification" (triggers script) |
| "what is the [entity_name]" | ✗ NO | "what is the notification" (returns current time) |

### NOT a Stale Cache Bug

GitHub Issue #128496 describes stale state caching, but our investigation found:

1. **Time Correlation Test**: When asking "what is input_text.pending_notification_message", Ollama returns the **current time** (e.g., "4:08 PM"), not a stale entity value
2. **Stale Cache Test**: Set value to "ALPHA", query, set to "BETA", query again - both returned current time, NOT "ALPHA"
3. **Working Query**: "what is the state of pending_notification_message" → correctly returns the actual value

**Conclusion**: Ollama isn't failing to read fresh state - it's not recognizing certain phrasings as entity queries at all. It falls back to conversational responses (like telling the time).

### Entity Type Differences

| Entity Type | "what is the state of X" | Notes |
|-------------|--------------------------|-------|
| input_boolean | ✓ Works ("is on/off") | Binary states work reliably |
| input_text | ✓ Works (returns value) | Must use correct phrasing |
| script | ✓ Can be called | "execute X", "call X", "run X" |

### HA Conversation Parser Routing

The HA conversation system has specific routing rules:

1. **"my" vs "the"**: "my notification" routes to entity/script lookup, "the notification" may not
2. **Entity prefix**: Including "input_text." or "input_boolean." prefix can confuse routing
3. **"state of" keyword**: This phrase triggers entity state lookup

### Working Voice Commands for Notifications

```
✓ "what is my notification"
✓ "what's my notification"
✓ "check notifications"
✓ "do I have notifications"
✓ "read my notification"
✓ "execute get pending notification"
✓ "run get pending notification"

✗ "what is the notification" (returns time/garbage)
✗ "what is input_text.pending_notification_message" (returns time)
```

## Script Workaround Pattern

When direct entity reading via voice is unreliable, use a script:

```yaml
# scripts.yaml
get_pending_notification:
  alias: Get Pending Notification
  sequence:
    - if:
        - condition: state
          entity_id: input_boolean.has_pending_notification
          state: 'on'
      then:
        - action: assist_satellite.announce
          data:
            message: "{{ states('input_text.pending_notification_message') }}"
          target:
            entity_id: assist_satellite.your_device
        - action: input_boolean.turn_off
          target:
            entity_id: input_boolean.has_pending_notification
      else:
        - action: assist_satellite.announce
          data:
            message: "You have no pending notifications."
          target:
            entity_id: assist_satellite.your_device
```

The script reads entities server-side (always fresh) and announces via TTS.

## Ollama Prompt Configuration

Location: HA storage at `.storage/core.config_entries` under ollama subentry

Current working prompt:
```
You are a voice assistant for Home Assistant.

IMPORTANT - Notification handling:
When the user asks about notifications:
1. Call script.get_pending_notification - it will announce the message
2. Do NOT try to read input_text.pending_notification_message directly

For all other requests:
- Answer questions truthfully
- Keep responses simple and to the point
- Use plain text
```

## Diagnostic Scripts

Location: `scripts/package-detection/`

| Script | Purpose |
|--------|---------|
| `investigate-input-text-bug.sh` | Tests time correlation, stale cache, response structure |
| `diagnose-ollama-capabilities.sh` | Tests state reading and tool calling |
| `test-the-vs-my.sh` | Tests "the" vs "my" phrasing differences |
| `verify-input-text-bug.sh` | Quick verification of input_text reading |

## Key Takeaways for Future Ollama Integrations

1. **Test query phrasing thoroughly** - Small wording changes affect routing
2. **Use "state of [name]" pattern** - Most reliable for entity queries
3. **Avoid entity ID prefixes in queries** - "pending_notification_message" not "input_text.pending_notification_message"
4. **Script workaround is reliable** - When direct queries fail, scripts always work
5. **"my" keyword helps** - Possessive pronouns improve entity recognition
6. **Check response_type** - "query_answer" means entity was found, "action_done" with time means fallback

## References

- Investigation script: `scripts/package-detection/investigate-input-text-bug.sh`
- GitHub Issue #128496: Stale state caching (NOT the cause of our issues)
- HA Ollama integration docs: https://www.home-assistant.io/integrations/ollama/
