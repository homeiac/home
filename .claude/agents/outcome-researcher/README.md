# Outcome Researcher Agent

Deep research agent for integration and architecture questions.

## When to Use

Invoke `@outcome-researcher` when user asks:
- "How should I integrate X with Y?"
- "Research how to..."
- "What's the best way to..."
- "Design X for Y"

## What It Does

1. **Extracts outcomes** from vague request (doesn't ask clarifying questions)
2. **Queries OpenMemory** to check if already solved
3. **Researches baseline** before custom solutions
4. **Presents top 3 outcomes** for user confirmation
5. **Maps solutions to outcomes**
6. **Stores findings** in OpenMemory

## Key Features

- **No clarifying questions** - Discovery is the agent's job
- **Baseline Before Custom** - Research vendor solutions first
- **Quality checks** - "What if too much?" for precision
- **Anti-pattern prevention** - No first-fit selection

## Example

```
User: How should I integrate Frigate with Ollama?

Agent: Based on my research, here are the top 3 outcomes:

1. **User can detect packages without manual review**
   - Current gap: Frigate detects motion, not package contents

2. **User gets AI reasoning without blocking cameras**
   - Current gap: Ollama API is synchronous

3. **User sees results in Home Assistant without custom code**
   - Current gap: No native integration exists

Confirm these outcomes, or adjust?
```

## Reference

Full methodology: `docs/methodology/outcome-anchored-research.md`
