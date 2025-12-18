# Outcome-Anchored Research: A Plan-and-Act Methodology for Claude Code

**Date**: 2025-12-18
**Author**: Homelab AI
**Tags**: claude-code, methodology, research, outcomes, plan-execute, context-engineering

---

## The Problem

When you ask Claude Code to "integrate X with Y," what happens?

**Without methodology:**
1. Claude finds *something* that looks relevant
2. Assumes it's *the right thing*
3. Starts implementing
4. You discover 3 sessions later it was wrong
5. "WTF, we already solved this!" frustration

This is **aimless exploration** - wandering until something looks familiar and declaring victory.

---

## The Solution: Outcome-Anchored Research

A systematic Plan-and-Act methodology where:
- **Outcomes are waypoints** - without them written down and checked, you wander
- **Research is investigation** (goal-directed), not exploration (wandering)
- **Every discovery triggers**: "Does this change the plan?"

### The Core Loop

```
DISCOVERY → PLAN → EXECUTE → REPLAN (if needed) → RESPONSE
     ↑                                              |
     └──────────────────────────────────────────────┘
                    Store in OpenMemory
```

---

## Key Innovations

### 1. Baseline Before Custom

Before building custom solutions, research what the vendor provides:

```
For EACH noun identified:
- What does the VENDOR/SOURCE officially provide?
- What LIMITATIONS do official docs acknowledge?
- What GAP remains after using official features?
- Only THEN consider custom solutions
```

**Example**: Before building OpenMemory integration for Claude Code, research:
- What does Claude Code already provide? (CLAUDE.md, Skills, Subagents, Plugins, MCP, Hooks)
- Where does it fall short? (Static persistence, no queryable memory)
- What gap remains? (Dynamic, semantic, learning memory)

### 2. Verbs and Anti-Goals (Not Just Nouns)

Traditional research identifies **nouns** (entities, systems). But user pain is often **verb-shaped**:

```
IDENTIFY nouns AND verbs:
- Nouns: OpenMemory, Claude Code, sessions
- Verbs: remember, repeat, correct, ignore
- ANTI-PATTERNS: What does user want STOPPED?
  "stop using one-liners"
  "stop jumping to conclusions"
  "stop ignoring this rule"
```

### 3. Quality Check for Precision

Outcomes can fail by being **too broad**:

```
QUALITY CHECK: For each outcome, ask:
- "What if user gets TOO MUCH of this?"
- "What's the failure mode of imprecision?"

Example:
- Outcome: "User can load context automatically"
- Quality check: "What if all 800 memories load?"
- Refined: "User gets task-relevant context only"
```

### 4. User Experience Framing

Outcomes must describe what **user experiences**, not what **tool does**:

```
Template: "User can <verb> without <pain point>"

❌ BAD:  "SQLite + hook survives compaction"
✅ GOOD: "User can /compact without losing context"

❌ BAD:  "MCP connects OpenMemory to Claude Code"
✅ GOOD: "User asks about past solutions without re-explaining"
```

### 5. Consolidation and Scenarios

Before finalizing outcomes:
- **Deduplicate**: Group similar outcomes
- **Prioritize**: By user pain severity
- **Scenarios**: Before/after for each outcome

```
Scenario - Task-Relevant Context:
- Before: User mentions Frigate, all 800 memories load, hits /compact
- After: User mentions Frigate, only Frigate memories load, context stays small
```

---

## The Discovery Phase: 5-Loop Process

Run 5 iterations. Each iteration contains ALL steps:

1. **READ** existing technical paper (if any)
2. **IDENTIFY** nouns AND verbs, anti-patterns
3. **RESEARCH** each noun - Baseline Before Custom
4. **UNDERSTAND** goals AND anti-goals of all actors
5. **MAP** integration points and gaps
6. **ARTICULATE** why this is a problem
7. **DETERMINE** outcomes with quality check, consolidation, scenarios
8. **WRITE/UPDATE** technical paper

Exit early if no new information emerges for 2 consecutive iterations.

---

## Anti-Patterns Caught

| Anti-Pattern | Looks Like | Fix |
|--------------|------------|-----|
| Aimless exploration | "Let me see what APIs exist..." | Extract outcomes first |
| First-fit selection | "This stores things, good enough" | Replan check: "Does this change the plan?" |
| Skipping baseline | Jump to custom without researching vendor | Baseline Before Custom |
| Noun-only thinking | Miss verb-shaped pain ("stop doing X") | Identify verbs AND anti-patterns |
| Missing quality dimension | "Load context" without precision | Quality check for "too much" |
| Solution-shaped outcomes | "SQLite + hook = works" | User experience template |
| No consolidation | 10 outcomes, 3 duplicates, core buried | Dedupe, prioritize by pain |

---

## Validation: It Works Without Cheating

We tested this methodology on "OpenMemory + Claude Code integration":

**Without methodology fixes:**
- Subagents produced 10 outcomes
- 3 were duplicates
- Core value ("/compact avoidance") buried at #8
- "Task-specific context without junk" completely missed

**With methodology fixes:**
- Quality check surfaced precision outcomes
- Consolidation deduplicated and prioritized
- Top 3 emerged correctly:
  1. User can work indefinitely without /compact
  2. User can correct Claude once and never repeat it
  3. User gets task-specific context without irrelevant junk

The subagents derived these by following the methodology - no hints required.

---

## Integration with Claude Code

This methodology is designed to trigger automatically when you ask:
- "How should I integrate X with Y?"
- "Research how to..."
- "What's the best way to..."

Claude Code will:
1. Run Discovery iterations (can use subagents)
2. Extract top 3-5 outcomes
3. Ask for confirmation before proceeding
4. Store findings in OpenMemory for future sessions

---

## The Top 3 Outcomes (OpenMemory + Claude Code)

After applying the full methodology:

| # | Outcome |
|---|---------|
| 1 | **User can work indefinitely without /compact** |
| 2 | **User can correct Claude once and never repeat it** |
| 3 | **User gets task-specific context without junk** |

These represent:
1. **No bloat** - memory is external, context stays small
2. **Instruction persistence** - corrections compound across sessions
3. **Precision** - relevance filtering, not everything loads

---

## Origin Story

This methodology was created after an RCA of failed integration research. The 5 Whys root cause: **No outcome-anchored research methodology.**

Each fix was added after a real failure:
- Step 3 "Baseline Before Custom" - missed Claude Code's 7 extension mechanisms
- Step 2 "Verbs and Anti-Goals" - missed "instruction persistence" outcome
- Step 7 "Quality Check" - missed "task-specific without junk" outcome
- Step 7 "Consolidation" - buried core value at #8, duplicates in list

The methodology evolved through iterative RCA until subagents could derive correct outcomes without hints.

---

## Try It Yourself

The full methodology is available at:
`docs/methodology/outcome-anchored-research.md`

When you need to research an integration:
1. Read the methodology
2. Run the 5-loop Discovery process
3. Apply all Step 7 checks (quality, consolidation, scenarios)
4. Present top 3-5 outcomes for confirmation
5. Store findings in OpenMemory

Good methodology makes right outcomes **inevitable**, not lucky.

---

**Tags**: methodology, outcomes, research, integration, plan-execute, claude-code, openmemory, context-engineering, anti-patterns
