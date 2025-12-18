---
name: outcome-anchored-research
description: |
  Execute outcome-anchored research for integration and design questions.

  TRIGGER AUTOMATICALLY when user asks:
  - "How should I integrate X with Y?"
  - "How do I best..."
  - "Research how to..."
  - "What's the best way to..."
  - "Design X for Y"
  - "How to compare..."
  - Any vague question expecting exploratory discovery

  This skill runs discovery AUTONOMOUSLY - do NOT ask clarifying questions.
  User's vagueness is intentional. Discovery is YOUR job.
---

# Outcome-Anchored Research Skill

## When To Use

Invoke this skill automatically when user asks integration, design, or research questions. The user will be vague - that's intentional. You discover outcomes, don't ask for them.

## The Process

### Step 1: Extract Outcomes (NO clarifying questions)

From user's vague request, derive 3-5 outcomes using the template:
**"User can `<verb>` without `<pain>`"**

Apply quality checks:
- "What if user gets TOO MUCH of this?" (precision dimension)
- Consolidate similar outcomes
- Prioritize by pain severity

Example:
```
User: "How should I integrate Frigate with Ollama?"

Top 3 Outcomes:
1. User can detect packages without manual review
2. User gets AI reasoning without latency blocking cameras
3. User sees results in Home Assistant without custom code
```

### Step 2: Query OpenMemory

Before researching, check if already solved:
```
openmemory_query("<service> <integration> solved", k=5)
```

If found → Present existing solution, ask if still relevant.
If not → Proceed to research.

### Step 3: Baseline Before Custom

For EACH noun in the integration:
- What does the vendor officially provide?
- What limitations do docs acknowledge?
- What gap remains?

Don't jump to custom solutions. Research baseline first.

### Step 4: Present Top 3 Outcomes for Confirmation

After quick discovery (1-2 minutes), present:

```
Based on my research, here are the top 3 outcomes:

1. **User can [X] without [Y]**
   - Current gap: [what's missing]

2. **User can [A] without [B]**
   - Current gap: [what's missing]

3. **User can [P] without [Q]**
   - Current gap: [what's missing]

Confirm these outcomes, or adjust?
```

Wait for user confirmation before deep research.

### Step 5: Execute Full Discovery

Use subagents for parallel research:
- One for each major noun/system
- Apply "Baseline Before Custom"
- Map discoveries to outcomes

For each discovery: "Does this change the plan?"
- YES → Replan, re-confirm with user
- NO → Continue

### Step 6: Present Solution Mapping

```
## Outcome → Solution Mapping

| Outcome | Solution | Source |
|---------|----------|--------|
| User can X without Y | Use API Z | docs/... |
| User can A without B | Configure C | vendor docs |
| User can P without Q | [GAP - needs custom] | - |
```

### Step 7: Store in OpenMemory

```
openmemory_lgm_store(
  node="act",
  content="<integration> - SOLVED. Top outcomes: [list]. Solutions: [mapping]",
  namespace="home",
  tags=["integration", "<service1>", "<service2>", "solved"]
)
```

## Anti-Patterns (DO NOT)

- Do NOT ask "What are your specific requirements?"
- Do NOT ask "How important is latency?"
- Do NOT ask "Which approach do you prefer?"
- Do NOT ask for details that you should discover

User's vague question is the CONSTRAINT. You discover outcomes through research.

## Reference

Full methodology: `docs/methodology/outcome-anchored-research.md`
