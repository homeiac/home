# USE Method - INCIDENT Flow

> **Parent doc**: [use-method-design.md](./use-method-design.md)
> **Prerequisite**: [use-method-prep-loop.md](./use-method-prep-loop.md) must be operational

## Goal

**"Do what Brendan Gregg would do: Walk the checklist systematically until the data tells you where to look deeper."**

No guessing. No shortcuts. No "probably". Just methodical elimination until the evidence speaks.

His reputation is at stake.

### The Bar: Zero Expertise Required

From Brendan's own site, on applying USE Method to the Apollo Lunar Module guidance system:

> "Looking for a fun example, I thought of a system in which I have no expertise at all, and no idea where to start: the Apollo Lunar Module guidance system. **The USE Method provides a simple procedure to try.**"

The methodology works even with zero domain knowledge:
1. Find the resources (functional block diagram)
2. For each resource: check E → U → S
3. Let the data speak

If it works for 1969 spacecraft avionics, it works for homelab.

See [Philosophy](./use-method-design.md#philosophy) in parent doc for Method R principles and USE → RED handoff.

## Status

**IN PROGRESS** - Designing the INCIDENT flowchart.

## Expected Content

The INCIDENT flow will cover:

1. **Context Gathering** - Claude translates vague user input to actionable targets
2. **USE Method Execution** - Systematic E→U→S check for all resources
3. **Layered Analysis** - Check both workload and host layers
4. **Deep Dive** - When issues found, drill down
5. **Network Ladder** - When external latency suspected
6. **Reporting** - Findings WITH DATA, not guesses
7. **Post-Incident** - RCA and runbook creation

## Related Docs

- [use-method-design.md](./use-method-design.md) - Main USE Method architecture
- [use-method-prep-loop.md](./use-method-prep-loop.md) - PREP phase (prerequisite)
