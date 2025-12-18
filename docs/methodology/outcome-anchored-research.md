# Outcome-Anchored Research Methodology

A systematic approach for researching integrations and solutions.
Extract outcomes first. Map discoveries to outcomes. Don't declare done until every outcome has a solution.

---

## Core Principle

> Research is **investigation** (goal-directed), not **exploration** (wandering).
> Outcomes are waypoints. Without them written down and checked, you wander until something looks familiar and declare victory.

---

## Quick Start

Before ANY research:
1. Extract user's desired behavior outcomes as checklist
2. Confirm checklist with user
3. Research with outcomes visible - map every discovery
4. Present outcome→solution mapping BEFORE implementation

---

## Plan-and-Execute Architecture

```
                    Request (with outcomes)
                            │
        ┌───────────────────┼───────────────────┐
        │                   ▼                   │
        │           ┌─────────────┐             │
        │           │    PLAN     │             │
        │           │             │             │
        │           │ • Extract   │             │
        │           │   outcomes  │◄────┐       │
        │           │ • Query     │     │       │
        │           │   OpenMemory│     │       │
        │           │   FIRST     │     │       │
        │           │ • Confirm   │     │       │
        │           │   with user │     │       │
        │           └──────┬──────┘     │       │
        │                  │            │       │
        │                  ▼            │       │
        │           ┌─────────────┐     │       │
        │           │  TASK PLAN  │     │       │
        │           │             │     │       │
        │           │ • Research  │     │ REPLAN│
        │           │   questions │     │ LOOP  │
        │           │ • Skip what │     │       │
        │           │   OpenMemory│     │       │
        │           │   already   │     │       │
        │           │   knows     │     │       │
        │           └──────┬──────┘     │       │
        │                  │            │       │
        │                  ▼            │       │
        │           ┌─────────────┐     │       │
        │           │   EXECUTE   │     │       │
        │           │             │─────┘       │
   ┌────┴────┐      │ • Use tools │             │
   │All Data │◄────►│ • Map to    │             │
   │         │      │   outcomes  │             │
   │ • Docs  │      │ • Check:    │             │
   │ • Code  │      │   "Does this│             │
   │ • APIs  │      │   change    │             │
   │ • OPEN- │      │   the plan?"│             │
   │  MEMORY │      └──────┬──────┘             │
   └─────────┘             │                    │
        │                  ▼                    │
        │           ┌─────────────┐             │
        │           │  RESPONSE   │             │
        │           │             │             │
        │           │ • outcome→  │             │
        │           │   solution  │             │
        │           │   map       │             │
        │     ┌────►│ • STORE in  │             │
        │     │     │   OpenMemory│             │
        │     │     └─────────────┘             │
        │     │                                 │
        └─────┴─────────────────────────────────┘
              │
              ▼
        Future sessions benefit
```

### OpenMemory Integration Points

| Phase | OpenMemory Action | Why |
|-------|------------------|-----|
| PLAN | `openmemory_query` for each outcome | "Has this been solved before?" |
| TASK PLAN | Skip research for known solutions | Don't re-discover what's stored |
| EXECUTE | Include as data source | Past findings inform current research |
| RESPONSE | `openmemory_store` new findings | Future sessions benefit |

### The Replan Loop is Critical

- During EXECUTE, every discovery triggers: "Does this change the plan?"
- If yes → loop back to PLAN, don't just use it
- Prevents "first-fit selection" anti-pattern
- Forces re-evaluation against ALL outcomes, not just the one you're working on

---

## Detailed Steps

### DISCOVERY Phase - The 5-Loop Process

Before extracting outcomes, understand the problem space through iterative refinement.

**Run 5 iterations. Each iteration contains ALL steps:**

```
for iteration in 1..5:
    ┌─────────────────────────────────────────────────────────┐
    │  1. READ existing technical paper (if any)              │
    │     - Input from previous iteration                     │
    │     - First iteration: may not exist                    │
    │                                                         │
    │  2. IDENTIFY nouns AND verbs in the request              │
    │     - Key entities/systems mentioned (nouns)            │
    │     - Key actions/behaviors mentioned (verbs)           │
    │     - Track emergent nouns/verbs across iterations      │
    │     - Later iterations may discover new patterns        │
    │     - ANTI-PATTERNS: What does user want STOPPED?       │
    │       (e.g., "stop using one-liners", "stop jumping     │
    │       to conclusions", "stop ignoring this rule")       │
    │                                                         │
    │  3. RESEARCH each noun                                  │
    │     - What is it?                                       │
    │     - WHY does it exist? What problem does it solve?    │
    │                                                         │
    │     ⚠️  BASELINE BEFORE CUSTOM (Critical):              │
    │     For EACH noun identified in Step 2:                 │
    │     - What does the VENDOR/SOURCE officially provide?   │
    │     - Read THEIR docs first, not community solutions    │
    │     - What LIMITATIONS do official docs acknowledge?    │
    │     - What GAP remains after using official features?   │
    │     - Only THEN consider custom/third-party solutions   │
    │                                                         │
    │     Don't skip any noun. Don't assume. Research ALL.    │
    │                                                         │
    │     Example - "Integrate Foo with Bar":                 │
    │     ❌ BAD: Research Foo, assume Bar works as expected  │
    │     ✅ GOOD: Research Foo baseline + Bar baseline, then │
    │             identify gap that requires custom work      │
    │                                                         │
    │     Example - "Add memory to Claude Code":              │
    │     ❌ BAD: Jump straight to OpenMemory integration     │
    │     ✅ GOOD:                                            │
    │       1. What does Claude Code provide for memory?      │
    │          (CLAUDE.md, project files, etc.)               │
    │       2. What are its acknowledged limitations?         │
    │       3. What does OpenMemory provide?                  │
    │       4. What are OpenMemory's limitations?             │
    │       5. What gap remains for custom work?              │
    │                                                         │
    │     - Read docs, code, APIs (especially "Why" docs)     │
    │     - Query OpenMemory for prior knowledge              │
    │     - VALIDATE with code review (not just docs)         │
    │                                                         │
    │  4. UNDERSTAND goals of all actors                      │
    │     - Extract goals FROM source docs, don't invent      │
    │     - What does each noun/system want to achieve?       │
    │     - What does the consumer/user want?                 │
    │     - ANTI-GOALS: What does user want to STOP?          │
    │       • What corrections has user repeated?             │
    │       • What frustrations appear in hooks/logs?         │
    │       • What rules exist because of past pain?          │
    │                                                         │
    │  5. MAP integration points and gaps                     │
    │     - Where do nouns intersect?                         │
    │     - What's missing between them?                      │
    │                                                         │
    │  6. ARTICULATE why this is a problem                    │
    │     - What pain exists today?                           │
    │     - What's the cost of not solving it?                │
    │                                                         │
    │  7. DETERMINE outcomes to achieve                       │
    │     - Specific, testable behaviors                      │
    │     - Derived from understanding, not assumed           │
    │     - MUST be user experience, NOT tool behavior        │
    │     - VALIDATION: If outcome mentions HOW (API, tech,   │
    │       storage, hook), REWRITE as WHAT user experiences  │
    │                                                         │
    │     Template: "User can <verb> without <pain point>"    │
    │     ❌ BAD:  "SQLite + hook survives compaction"        │
    │     ✅ GOOD: "User can /compact without losing context" │
    │                                                         │
    │  ⚠️  SOLUTION QUARANTINE: If you discover solutions     │
    │      during Discovery, write them in a SEPARATE         │
    │      "Solutions Found" section. Do NOT mix into         │
    │      outcomes. Solutions belong in EXECUTE phase.       │
    │                                                         │
    │  8. WRITE/UPDATE technical paper                        │
    │     - Consolidate findings                              │
    │     - This becomes input for next iteration             │
    └─────────────────────────────────────────────────────────┘
```

**Why 5 iterations?**
- Iteration 1: Initial understanding, likely incomplete
- Iteration 2: Fill gaps discovered in iteration 1
- Iteration 3: Refine based on deeper research
- Iteration 4: Validate understanding, catch edge cases
- Iteration 5: Final polish, confirm outcomes are complete

**Exit early if**: No new information emerges for 2 consecutive iterations.

---

### PLAN Phase

**Step 1: Recognize Trigger**

Activate this methodology when user says:
- "How to best...", "What's the right way to..."
- "Research how to...", "Integrate X with Y"
- Any request with defined behavior outcomes

**Step 2: Extract Outcomes**
- Use findings from Discovery Phase (Step 0)
- List every desired behavior
- Format as checkable list in plan file

**Step 3: Query OpenMemory**
```bash
openmemory_query("<outcome keywords>", k=5)
```
- For EACH outcome, check if already solved
- Mark outcomes with existing solutions
- This prevents re-research

**Step 4: Confirm with User**
- Present checklist: "These are the outcomes I'll research"
- Present OpenMemory hits: "These may already be solved"
- Ask: "Correct? Any additions?"

### TASK PLAN Phase

**Step 5: Create Research Questions**

For each UNSOLVED outcome:
- What APIs/features could enable this?
- Where would this be documented?
- What's the canonical way to achieve this?

**Step 6: Prioritize**
- Dependencies first (some outcomes may unlock others)
- Quick wins early (build momentum)
- Skip outcomes OpenMemory already solved

### EXECUTE Phase

**Step 7: Research with Tools**
- Read docs, code, APIs
- Include OpenMemory as data source
- For each discovery, immediately ask:
  - "Which outcome does this enable?"
  - "Does this change the plan?"

**Step 8: REPLAN CHECK (Critical)**

If discovery changes understanding:
```
STOP → Return to PLAN phase
- Re-extract outcomes if scope changed
- Re-query OpenMemory with new keywords
- Re-confirm with user if major shift
```
Do NOT just use the first thing found.

**Step 9: Map to Outcomes**

Build explicit mapping:
```markdown
| Outcome | Solution | Why It Fits | Source |
|---------|----------|-------------|--------|
| X       | API Y    | Because...  | docs/  |
```

### RESPONSE Phase

**Step 10: Completion Criteria**

Research is DONE when:
- [ ] Every outcome has a mapped solution
- [ ] Can explain WHY each solution fits
- [ ] No orphaned outcomes
- [ ] Replan loop has stabilized (no new changes)

**Step 11: Present Findings**
```markdown
## Research Findings

### Outcome → Solution Mapping
| Outcome | Solution | Why It Fits |
|---------|----------|-------------|
| X       | API Y    | Because...  |

### From OpenMemory (Already Known)
- Outcome A was solved in previous session: [link]

### Gaps
- Outcome Z has no direct solution; alternatives: ...

### Recommended Approach
[Based on mapping]
```

**Step 12: Store in OpenMemory**
```bash
openmemory_store(
  content="<outcome>: <solution> - <why it fits>",
  tags=["research", "<domain>", "outcome-mapping"]
)
```

---

## Replan Loop Triggers

**When to trigger REPLAN**:

| Discovery | Action | Why |
|-----------|--------|-----|
| Found a better API than planned | REPLAN | May change solution for multiple outcomes |
| Outcome can't be achieved as stated | REPLAN | Need to revise outcome with user |
| New capability discovered | REPLAN | May simplify other outcomes |
| Dependency found between outcomes | REPLAN | Affects task order |
| OpenMemory has partial solution | REPLAN | Adjust scope of new research |

**When NOT to replan** (continue EXECUTE):
- Found exactly what you expected
- Discovery maps cleanly to one outcome
- No impact on other outcomes

---

## Anti-Patterns

| Anti-Pattern | Looks Like | Why Wrong | Architecture Fix |
|--------------|------------|-----------|------------------|
| Aimless exploration | "Let me see what APIs exist..." | No anchor to outcomes | PLAN: extract outcomes first |
| First-fit selection | "This stores things, good enough" | Didn't verify meets outcomes | REPLAN: "Does this change the plan?" |
| Rabbit hole diving | 2 hours on tangent | Lost sight of outcomes | EXECUTE: "Which outcome am I solving?" |
| Premature implementation | "Found something, let me build" | Didn't map all outcomes | RESPONSE: wait for all mappings |
| Implicit outcomes | Outcomes in conversation only | Must be explicit checklist | PLAN: write to plan file |
| Re-researching | Investigating already-solved problem | Wasted effort | PLAN: query OpenMemory first |
| Not storing | Didn't save new findings | Future sessions lose knowledge | RESPONSE: store in OpenMemory |
| Solution-shaped outcomes | "SQLite + hook = survives" | Outcomes describe HOW, not WHAT user wants | DISCOVERY: Use template "User can X without Y" |
| Noun-only thinking | Only identify entities, miss behaviors | User pain often verb-shaped: "stop doing X" | DISCOVERY: Step 2 includes verbs AND anti-patterns |
| Missing anti-goals | Only ask what user wants, not what they want STOPPED | Repeated corrections become invisible | DISCOVERY: Step 4 extracts anti-goals from frustrations |
| Skipping baseline | Jump to custom solution without researching vendor's offering | May rebuild what exists or miss known limitations | DISCOVERY: Step 3 requires "Baseline Before Custom" |

---

## Validation Test Case: OpenMemory Integration

This test validates the methodology would have caught a real bug.

### Setup
- Request: "Integrate OpenMemory with Claude Code for persistent memory"
- Outcomes:
  1. Claude Code remembers context across sessions
  2. Semantic search finds relevant past work
  3. Documents and scripts are searchable by content
  4. Large documents should be chunked appropriately

### Key Checkpoints

| Step | What Happened Without Methodology | What Should Happen With Methodology |
|------|----------------------------------|-------------------------------------|
| README read | Skipped, went straight to API | Must read docs, notice "Ingestion Formats" |
| Replan trigger | "I found /memory/add, good enough" | "Does this change the plan?" → YES → investigate |
| Outcome mapping | Assumed /memory/add would work | "Does add handle large docs?" → NO → keep searching |
| API comparison | Never compared | "Which API fits which outcome?" → Found /memory/ingest |

### Test Result

**PASS** if methodology surfaces `/memory/ingest` before implementation.

**Failure Modes**:
- Skipping README
- Not triggering replan on "ingestion" discovery
- Not mapping APIs to outcomes explicitly
- Accepting first-fit without outcome validation

---

## Origin

This methodology was created after an RCA of failed OpenMemory integration research. The 5 Whys root cause: **No outcome-anchored research methodology.** Without explicit outcomes as waypoints, exploration becomes aimless - find *something*, assume it's *the right thing*, declare done.

**Reference**: RCA dated 2025-12-17

---

**Tags**: research, methodology, outcomes, requirements, integration, investigation, design, planning, anti-patterns, rabbit-hole, plan-execute, replan-loop, openmemory, validation
