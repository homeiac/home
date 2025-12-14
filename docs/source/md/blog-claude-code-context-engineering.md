# Context Engineering for Claude Code: A Self-Reinforcing Memory Architecture

**Published**: 2025-12-14
**Tags**: claude-code, context-engineering, openmemory, knowledge-graph, behavior-expectations, architecture

---

## The Problem: Context Amnesia and Weak Enforcement

Working with Claude Code on a complex homelab presents a recurring challenge: **context amnesia across sessions**. You teach Claude that "SSH to K3s VMs doesn't work, use `qm guest exec` instead," and it works perfectly. The next day, in a fresh session, Claude confidently tries SSH again, hits the same error, and you're back to square one.

The naive solution is to document everything in `CLAUDE.md`: "Don't SSH to K3s VMs." But here's the brutal truth:

**INFORMATION ≠ ENFORCEMENT**

Claude reading "don't do X" in documentation is **weak enforcement**. It's a suggestion, not a constraint. When Claude's training data overwhelmingly says "SSH is how you access Linux systems," a paragraph in `CLAUDE.md` gets drowned out by billions of parameters saying otherwise.

This is where **context engineering** comes in: building an architecture that doesn't just inform Claude, but actively shapes its behavior through multiple enforcement layers.

---

## The Architecture: Layered Enforcement with Self-Reinforcing Memory

The solution is a three-tier enforcement hierarchy, leveraging both Claude Code's built-in capabilities and OpenMemory's knowledge graph:

### Enforcement Hierarchy

```
┌─────────────────────────────────────────────────────────────┐
│  HARD ENFORCEMENT                                            │
│  Tool deny patterns in settings.json                         │
│  - Physically blocks command execution                       │
│  - Cannot be bypassed by reasoning                           │
│  - Example: "Bash(ssh*k3s-vm*)" → command rejected           │
└─────────────────────────────────────────────────────────────┘
         ↓ Fallback for non-blockable behaviors
┌─────────────────────────────────────────────────────────────┐
│  MEDIUM ENFORCEMENT                                          │
│  SessionStart hooks + OpenMemory query                       │
│  - Injects context at session start                          │
│  - Task-triggered memory queries (R7b)                       │
│  - Folder-aware context loading                              │
└─────────────────────────────────────────────────────────────┘
         ↓ Fallback for edge cases
┌─────────────────────────────────────────────────────────────┐
│  WEAK ENFORCEMENT                                            │
│  CLAUDE.md documentation                                     │
│  - Human-readable reference                                  │
│  - Easily ignored under context pressure                     │
│  - Better than nothing, worse than everything else           │
└─────────────────────────────────────────────────────────────┘
```

The key insight: **use the strongest enforcement mechanism available for each behavior**.

---

## Behavior Expectations Framework (BE-XXX)

Instead of scattering fixes across sessions, we formalize each behavior problem as a **Behavior Expectation**:

### BE-001: K3s VM SSH Block

```
Trigger: User asks to run/diagnose anything on k3s-vm-*
Current Bad Behavior: Claude attempts ssh ubuntu@k3s-vm-* (always fails)
Expected Behavior: Claude uses scripts/k3s/exec-*.sh or qm guest exec
Enforcement Mechanism: HARD - Bash tool deny pattern
Test Case: "check CPU on k3s-vm-still-fawn" → verify no SSH executed
Status: VERIFIED WORKING
```

**Enforcement implementation** (`~/.claude/settings.json`):

```json
{
  "permissions": {
    "deny": [
      "Bash(ssh*k3s-vm*)",
      "Bash(ssh*ubuntu@k3s-vm*)"
    ]
  }
}
```

This **physically prevents** Claude from executing the command. Not a suggestion, not a guideline—an actual block at the tool invocation layer.

---

## Leveraging OpenMemory's Knowledge Graph

OpenMemory provides a pre-built knowledge graph infrastructure that we exploit without reimplementing:

### What OpenMemory Gives Us for Free

1. **Waypoints** - Temporal structure (episodic, semantic, procedural)
2. **Sectors** - Memory categorization (observe, plan, act, reflect, emotion)
3. **Salience** - Automatic decay for stale memories
4. **Embeddings** - Semantic similarity search across memories
5. **Tagging** - Multi-dimensional memory organization

### What We Build On Top

Instead of creating custom linking logic, we:

1. **Store well-tagged memories**:
   ```python
   openmemory_lgm_store(
     node="act",  # procedural knowledge
     content="SSH to K3s VMs broken - use qm guest exec instead",
     namespace="home",
     tags=["k3s", "ssh", "workaround", "qm-guest-exec"]
   )
   ```

2. **Query before claiming limitations** (R11):
   ```python
   # Before saying "that's not supported"
   memories = openmemory_query("k3s vm access ssh")
   # Check if we already solved this exact problem
   ```

3. **Reinforce helpful memories** (R8):
   ```python
   # When a memory solves a problem
   openmemory_reinforce(id=memory_id, boost=0.1)
   # Increases salience, prevents premature decay
   ```

4. **Task-triggered context loading** (R7b):
   ```python
   # User says: "Let's migrate Frigate to pumped-piglet"
   # IMMEDIATELY query: "frigate pumped-piglet migration gpu coral"
   # Present relevant memories BEFORE starting
   ```

The knowledge graph handles the hard part (semantic linking, decay, retrieval). We just need to store quality memories and query intelligently.

---

## SessionStart Hook: Folder-Aware Context Loading

At the start of every session, context is automatically injected via a bash hook:

**`~/.claude/hooks/load-openmemory-context.sh`** (excerpt):

```bash
#!/bin/bash
# Extract keywords from current working directory
extract_keywords() {
    local path="$1"
    local keywords=""

    [[ "$path" == *"haos"* ]] && keywords="home-assistant haos access"
    [[ "$path" == *"frigate"* ]] && keywords="frigate coral vaapi gpu"
    [[ "$path" == *"k3s"* ]] && keywords="kubernetes k3s ssh qm-guest-exec"
    [[ "$path" == *"proxmox"* ]] && keywords="proxmox nodes infrastructure"

    echo "$keywords"
}

KEYWORDS=$(extract_keywords "$PWD")

# Query 1: Folder-relevant memories (semantic search)
RELEVANT=$(curl -X POST "http://localhost:8080/mcp" \
    -d "{\"method\": \"tools/call\", \"params\": {
        \"name\": \"openmemory_query\",
        \"arguments\": {\"query\": \"$KEYWORDS\", \"k\": 8}
    }}")

# Query 2: Recent memories (for session continuity)
RECENT=$(curl -X POST "http://localhost:8080/mcp" \
    -d "{\"method\": \"tools/call\", \"params\": {
        \"name\": \"openmemory_list\",
        \"arguments\": {\"limit\": 5}
    }}")

# Inject as additionalContext for SessionStart
jq -n --arg ctx "$RELEVANT\n\n$RECENT" \
    '{"hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": $ctx
    }}'
```

**Key features**:
- Directory-aware: `~/code/home/scripts/frigate/` → queries "frigate coral vaapi gpu"
- Dual queries: folder-relevant + recent memories
- Graceful degradation: if OpenMemory is down, session continues without context
- Zero user notification: context loads silently in background

**Configured in `~/.claude/settings.json`**:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup",
        "hooks": [
          {
            "type": "command",
            "command": "~/.claude/hooks/load-openmemory-context.sh"
          }
        ]
      }
    ]
  }
}
```

---

## Principal-Subagent Architecture: Keeping Context Low

Complex tasks spawn **subagents** via the `Task` tool. This keeps the principal session's context focused:

### How It Works

**Principal (Architect) session**:
- Analyzes behavior problems
- Documents as `BE-XXX` specifications
- Delegates implementation to subagents
- Verifies results

**Subagent (Implementer) session**:
- Receives focused prompt with specific task
- Has isolated context (doesn't inherit principal's full history)
- Returns structured results
- Self-terminates after completion

**Example delegation**:

```python
# Principal session identifies problem, delegates fix
Task(
  description="Implement SSH deny patterns",
  prompt="""
You are implementing behavior expectations BE-001 and BE-002.

**Task**: Add Bash tool deny patterns to block SSH to K3s VMs and HAOS.

**File to modify**: ~/.claude/settings.json

**Patterns to deny**:
- ssh*k3s-vm* - K3s VMs don't have working SSH
- ssh*homeassistant* - HAOS has no SSH

**Return**:
- What you found about deny pattern syntax
- The changes you made
- How to verify it works
  """,
  subagent_type="general-purpose"
)
```

**Subagent returns**:
- Research findings on deny pattern syntax
- Implementation changes made
- Verification procedure
- `agentId` for resuming if needed

The principal session's context remains focused on architecture decisions, not implementation details.

---

## The Self-Reinforcing Loop

Putting it all together, we get a system that learns from its own successes:

```
┌─────────────────────────────────────────────────────────────┐
│  1. QUERY - Before Task Execution                           │
│     User: "Migrate Frigate to pumped-piglet"                │
│     Claude: openmemory_query("frigate pumped-piglet gpu")   │
│     Result: "pumped-piglet uses NVENC not VAAPI"            │
└─────────────────────────────────────────────────────────────┘
         ↓
┌─────────────────────────────────────────────────────────────┐
│  2. USE - Apply Memory to Task                              │
│     Claude: "Before migrating, I found that pumped-piglet   │
│             uses NVENC. Should I proceed with that config?" │
│     User: "Yes, good catch"                                 │
└─────────────────────────────────────────────────────────────┘
         ↓
┌─────────────────────────────────────────────────────────────┐
│  3. LEARN - Discover New Knowledge During Task              │
│     Issue encountered: Coral USB needs physical replug      │
│     New finding: libedgetpu 16.0 required for Frigate 0.14  │
└─────────────────────────────────────────────────────────────┘
         ↓
┌─────────────────────────────────────────────────────────────┐
│  4. STORE - Persist New Knowledge                           │
│     openmemory_lgm_store(                                   │
│       node="observe",                                       │
│       content="Coral USB did not claim interface 0 error    │
│                requires physical unplug/replug",            │
│       tags=["coral", "usb", "troubleshooting"]              │
│     )                                                       │
└─────────────────────────────────────────────────────────────┘
         ↓
┌─────────────────────────────────────────────────────────────┐
│  5. REINFORCE - Boost Helpful Memories                      │
│     Memory helped solve issue → openmemory_reinforce()      │
│     Salience increased, decay timer reset                   │
│     Memory more likely to surface in future queries         │
└─────────────────────────────────────────────────────────────┘
         ↓ (next time user asks about Coral USB issues)
        QUERY (step 1, with reinforced memory now top result)
```

**The magic**: Each successful use of a memory makes it stronger. Unused memories naturally decay. The system organically learns what's useful vs what's trivia.

---

## Critical Rule: Ask Before Changing Behavior (R10)

A memory suggesting a different approach is **NOT** permission to silently change behavior:

**WRONG** (silent behavior change):
```
User: "SSH into k3s-vm-still-fawn"

Claude: *queries memory, finds "SSH broken, use qm guest exec"*
         "I'll use qm guest exec instead..."
         *runs qm guest exec without asking*
```

**CORRECT** (ask first):
```
User: "SSH into k3s-vm-still-fawn"

Claude: *queries memory, finds "SSH broken, use qm guest exec"*
         "I recall from a previous session that SSH to K3s VMs
          was broken. Should I use qm guest exec via Proxmox
          host instead, or try SSH first?"
```

**Why this matters**: The user might have fixed SSH since the memory was stored. Always confirm before deviating from the requested approach.

---

## Anti-Pattern: Confident Incorrect Claims (R11)

Before claiming something is a "limitation" or "not supported", **query OpenMemory first**:

**WRONG** (confident bullshit):
```
User: "AMD GPU not showing in Frigate dashboard"

Claude: "That's a Frigate limitation - it only supports Intel
         VAAPI display. You could open a feature request or
         build a custom Grafana dashboard."
```

**CORRECT** (query first):
```
Claude: *queries OpenMemory: "frigate amd gpu vaapi display"*
        *finds: "LIBVA_DRIVER_NAME=radeonsi env var fixes AMD VAAPI"*

        "I found a previous solution - this needs
         LIBVA_DRIVER_NAME=radeonsi env var. Let me check
         if that's set in the current deployment."
```

**The failure mode** isn't "I don't know"—it's "I confidently tell you it's impossible when you already solved it months ago." OpenMemory prevents this.

---

## Results: Verified Behavior Changes

### BE-001: K3s SSH Block - VERIFIED WORKING

**Before**:
```
User: "Check CPU on k3s-vm-still-fawn"
Claude: ssh ubuntu@k3s-vm-still-fawn "top -bn1"
Result: Connection refused (every single time)
```

**After** (with deny pattern):
```
User: "Check CPU on k3s-vm-still-fawn"
Claude: *attempts ssh → blocked by permissions*
        *falls back to qm guest exec approach*
Result: Successful execution without wasted SSH attempts
```

**Enforcement**: HARD block via `Bash(ssh*k3s-vm*)` deny pattern

### Subagent Delegation - REDUCES PRINCIPAL CONTEXT

**Before** (single session):
- Principal session context: 40K+ tokens
- Lost in implementation details
- Difficult to maintain architectural focus

**After** (with subagents):
- Principal session context: ~15K tokens (focused on decisions)
- Subagent context: isolated to specific task
- Clear separation between architecture and implementation

---

## Key Insights

### 1. Deny Patterns Actually Work
Tool-level deny patterns in `settings.json` provide **hard enforcement** that cannot be reasoned around. This is the most reliable enforcement mechanism for blocking specific commands.

### 2. Subagents Keep Principal Context Low
Delegating implementation to subagents prevents context pollution in the principal session. The architect stays focused on high-level decisions, implementers handle specifics.

### 3. Knowledge Graph Linking Is Free
OpenMemory's semantic similarity search, salience decay, and memory sectors provide sophisticated linking without custom code. Just store well-tagged memories and query intelligently.

### 4. Store Metadata, Not Implementation
OpenMemory stores **what** and **why** (metadata). Scripts and tooling store **how** (implementation). This separation keeps memories lightweight and durable.

Example:
- **Memory**: "K3s VMs don't have working SSH, use qm guest exec"
- **Script**: `scripts/k3s/exec-on-vm.sh` (actual implementation)
- **CLAUDE.md**: References both memory and script

### 5. Self-Reinforcing Framework Validated
The query → use → learn → store → reinforce loop creates organic knowledge evolution. Useful memories strengthen, stale memories fade, no manual curation needed.

---

## Implementation Summary

### Files Modified

1. **`~/.claude/settings.json`**
   - Added deny patterns for SSH to K3s VMs and HAOS
   - Configured SessionStart hook for OpenMemory context loading

2. **`~/.claude/hooks/load-openmemory-context.sh`**
   - Folder-aware keyword extraction
   - Dual query (relevant + recent memories)
   - Graceful degradation if OpenMemory unavailable

3. **OpenMemory Behavior Expectations**
   - R7: Session start context loading
   - R7b: Task-triggered memory queries
   - R8: Reinforce helpful memories
   - R10: Ask before changing behavior
   - R11: Query before claiming limitations

### Code Examples

**Store a procedural memory**:
```python
openmemory_lgm_store(
  node="act",
  content="SSH to K3s VMs broken - use qm guest exec instead",
  namespace="home",
  tags=["k3s", "ssh", "workaround", "qm-guest-exec"]
)
```

**Task-triggered context query**:
```python
# User: "Migrate Frigate to pumped-piglet"
memories = openmemory_query("frigate pumped-piglet migration gpu coral")
# Present relevant findings before starting task
```

**Reinforce helpful memory**:
```python
# Memory helped solve a problem
openmemory_reinforce(id="mem_xyz123", boost=0.1)
```

---

## Measuring Success: Behavior First, Context Second

Success in context engineering has a clear priority order:

### Primary Metric: Claude Behavior Compliance

The **primary** measure is whether Claude follows established rules without manual intervention. A session that follows rules but uses more context is preferable to one that ignores rules "efficiently."

| Metric | Target | Why It Matters |
|--------|--------|----------------|
| BE-XXX test pass rate | 100% | Core behaviors must work |
| "Confident wrong claim" incidents | 0 (when memory exists) | R11 prevents hallucinated limitations |
| Silent behavior changes | 0 | R10 ensures user control |
| SSH-to-K3s attempts | 0 | BE-001 must actually block |
| Scripts vs one-liners | >90% scripts | Reusable artifacts over ephemeral commands |

**How to verify**: Run the test case for each BE-XXX. If Claude attempts SSH to k3s-vm-still-fawn, the entire framework has failed regardless of context efficiency.

### Secondary Metric: Context Efficiency

The **secondary** measure is session duration before hitting context limits (the dreaded `/compact`):

| Metric | Target | Why It Matters |
|--------|--------|----------------|
| Turns before compaction | >50 | Longer productive sessions |
| Complex task completion | Single session | No mid-task context loss |
| Principal token usage | <50k for complex tasks | Room for actual work |
| Subagent delegation rate | >70% for diagnostics | Keep principal context focused |

**Why secondary**: Context efficiency enables longer conversations. But if Claude is efficiently doing the wrong things, efficiency is meaningless.

### The Priority Relationship

```
IF behavior compliance failing:
    → Fix enforcement first (deny patterns, hooks, memories)
    → Context efficiency doesn't matter yet

IF behavior compliance passing:
    → Then optimize context efficiency
    → Improve delegation, reduce redundant queries
```

**Anti-pattern to avoid**: Optimizing for context efficiency while ignoring behavior compliance. A 10k-token session that tries SSH to K3s VMs is a failure.

---

## Conclusion: From Information to Enforcement

Context engineering isn't about writing more documentation—it's about **architecting enforcement mechanisms** that shape behavior through constraints, not suggestions.

The three-tier hierarchy (HARD deny patterns, MEDIUM hooks, WEAK docs) ensures we use the strongest enforcement available for each behavior. OpenMemory's knowledge graph provides semantic linking and salience decay without custom infrastructure. The self-reinforcing loop creates organic knowledge evolution.

**Result**: Claude Code sessions that learn from past mistakes, avoid repeating solved problems, and continuously improve without manual curation.

---

## Architecture Documentation

Full architecture details: `/Users/10381054/code/home/AI_FIRST_HOMELAB_ARCHITECTURE.md`

OpenMemory integration: `~/.claude/CLAUDE.md` (OpenMemory Integration section)

Behavior expectations: Stored in OpenMemory namespace `home` with tag `behavior-expectation`

---

**Tags**: claude-code, context-engineering, openmemory, knowledge-graph, behavior-expectations, self-reinforcing-learning, enforcement-hierarchy, session-management, homelab-ai
