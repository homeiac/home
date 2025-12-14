# OpenMemory Integration Test Instructions

Tests both the MCP tools AND the behavioral requirements from CLAUDE.md.

## Prerequisites
- OpenMemory container running at localhost:8080
- Claude Code restarted after container rebuild
- Run `./scripts/openmemory/verify-mcp-backend.sh` first to verify backend

---

## Part 1: Tool Verification (Quick)

### Test 1.1: Tools Available
Ask: "What OpenMemory tools do you have access to?"

Expected: Should list 7 tools including `openmemory_lgm_store` and `openmemory_lgm_context`

### Test 1.2: Basic Store/Retrieve
Ask: "Store a test memory with node='act' about 'Test verification passed' in namespace 'test'"

Expected: Memory stored with reflection created

---

## Part 2: Behavioral Requirements (Critical)

### Test 2.1: R7 - Session Start Context Query
**Start a NEW Claude Code session in the home repo.**

Check if Claude:
- [ ] Queries OpenMemory context automatically (may be silent)
- [ ] Does NOT announce "loading context..." unless asked

To verify, ask: "Did you query OpenMemory at session start?"
Expected: "Yes, I queried for context in the 'home' namespace"

### Test 2.2: R10 - Ask Before Changing Behavior
First, ensure this memory exists:
```
Store memory: node="act", content="SSH to K3s VMs is broken - use qm guest exec via Proxmox host instead", namespace="home"
```

Then in a NEW session, ask: "SSH into k3s-vm-still-fawn"

Expected behavior (PASS):
```
"I recall from a previous session that SSH to K3s VMs was broken.
Should I use qm guest exec via Proxmox host instead, or try SSH first?"
```

FAIL if Claude silently uses qm guest exec without asking.

### Test 2.3: R8 - Reinforce Useful Memories
After a memory helps solve a problem, Claude should:
- [ ] Call `openmemory_reinforce` on that memory
- [ ] Briefly mention: "That workaround helped - I've reinforced that memory"

To test: Ask Claude to solve a problem that uses a stored memory, then check if it reinforces.

### Test 2.4: R9 - Graceful Degradation
Stop OpenMemory: `docker stop openmemory-openmemory-1`

At session end, if Claude has important learnings:
- [ ] Claude offers to persist to CLAUDE.md instead
- [ ] Asks: "OpenMemory is unavailable. Should I add today's key learnings to CLAUDE.md?"

Restart after: `docker start openmemory-openmemory-1`

### Test 2.5: Storage Triggers
Ask Claude to do work that should trigger storage:

| Trigger | Test Action | Expected |
|---------|-------------|----------|
| Issue Resolution | Fix a bug, then check if stored | Memory with node="act" |
| Discovery | Find undocumented behavior | Memory with node="observe" |
| User Request | Say "remember this: X" | Memory stored immediately |
| Session End | End session after learning something | Reflection memory created |

---

## Success Criteria

### Tools (Part 1)
- [ ] 7 MCP tools available
- [ ] Store/retrieve works

### Behavioral (Part 2 - THE IMPORTANT ONES)
- [ ] R7: Session start queries context
- [ ] R10: Asks before changing behavior based on memory
- [ ] R8: Reinforces useful memories
- [ ] R9: Falls back to CLAUDE.md when unavailable
- [ ] Storage triggers work (issue resolution, discovery, user request, session end)

---

## Troubleshooting

**Tools not visible:**
1. `docker ps | grep openmemory`
2. `docker logs openmemory-openmemory-1`
3. Restart Claude Code

**Behavioral requirements not working:**
1. Check CLAUDE.md has "OpenMemory Integration" section
2. Verify the behavioral guidelines are present
3. Claude may need explicit reminder in first session
