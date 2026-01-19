# OpenMemory Integration - Product Requirements Document

**Status**: Active Development
**Owner**: Homelab AI
**Created**: 2025-12-17
**Last Updated**: 2025-12-17
**Version**: 1.0

## Overview

This PRD defines the requirements for integrating OpenMemory with Claude Code to provide persistent, intelligent memory across sessions.

**Related**: [Concept Document](./openmemory-concept.md)

## Requirements Summary

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| R1 | Context stays small | P0 | Done |
| R2 | External knowledge | P0 | Done |
| R3 | Knowledge graph | P1 | Done |
| R4 | Seamless | P0 | Partial |
| R5 | Project-scoped | P1 | Done |
| R6 | Task-scoped | P1 | Partial |
| R7 | Auto-context load | P0 | Done |
| R8 | Reinforcement | P1 | Done |
| R9 | Query before store | P2 | Not Started |
| R10 | Ask before changing | P1 | Done |
| R11 | Query before limitations | P0 | Done |

## Detailed Requirements

### R1: Context Stays Small

**Priority**: P0 (Critical)
**Status**: Done

**Description**: Claude Code should never hit "compact conversation" due to memory. Context comes from external queries, not bloated prompts.

**Acceptance Criteria**:
- [ ] Session hook injects summary, not full memories
- [ ] Summary stays under 2000 tokens
- [ ] Full content retrieved on-demand via query
- [ ] No duplicate information between CLAUDE.md and memories

**Implementation**:
- `openmemory_lgm_context` returns summary format
- Hook uses `--limit` to cap injected tokens

### R2: External Knowledge

**Priority**: P0 (Critical)
**Status**: Done

**Description**: Knowledge should be stored in OpenMemory and queried on demand, not embedded in CLAUDE.md.

**Acceptance Criteria**:
- [ ] Docs, scripts, configs ingested into OpenMemory
- [ ] Semantic search finds relevant content
- [ ] CLAUDE.md contains rules, not data

**Implementation**:
- `ingest-docs.sh` ingests 800+ files
- Ollama embeddings enable semantic search
- CLAUDE.md references OpenMemory rules

### R3: Knowledge Graph

**Priority**: P1 (High)
**Status**: Done

**Description**: Related memories should surface together. Parent-child relationships, cross-references, semantic similarity.

**Acceptance Criteria**:
- [ ] Query returns related memories, not just exact matches
- [ ] Memories link to related memories (waypoints)
- [ ] Cross-sector relationships maintained

**Implementation**:
- Multi-sector classification (episodic, semantic, procedural, emotional, reflective)
- Vector similarity search across sectors
- Reflection memories auto-created

### R4: Seamless

**Priority**: P0 (Critical)
**Status**: Partial

**Description**: Memory should feel automatic, not like extra work. Store on discoveries, retrieve on tasks.

**Acceptance Criteria**:
- [ ] Context loads automatically at session start
- [ ] Discoveries get stored without explicit command
- [x] Relevant memories surface when task is mentioned
- [ ] No manual "remember this" needed for common patterns

**Gaps**:
- Auto-store on discoveries not implemented (manual `lgm_store` required)
- Need PostToolUse hook to detect and store learnings

**Implementation**:
- Session start hook (done)
- Task-triggered query rules in CLAUDE.md (done)
- Auto-store hook (not done)

### R5: Project-Scoped

**Priority**: P1 (High)
**Status**: Done

**Description**: Different repos get different default contexts. No cross-contamination unless relevant.

**Acceptance Criteria**:
- [ ] Namespace derived from project directory
- [ ] Queries default to current project namespace
- [ ] Cross-project queries explicit

**Implementation**:
- `namespace` parameter on all tools
- Hook detects `$PWD` and sets namespace
- Default namespace = basename of project dir

### R6: Task-Scoped

**Priority**: P1 (High)
**Status**: Partial

**Description**: Relevant memories surface for the current task, not everything ever stored.

**Acceptance Criteria**:
- [ ] Mention "Frigate" → Frigate memories surface
- [ ] Mention "GPU passthrough" → GPU memories surface
- [ ] Irrelevant memories stay hidden

**Gaps**:
- Works when Claude explicitly queries
- Could be more proactive with keyword detection

**Implementation**:
- R7b rule in CLAUDE.md triggers queries on task keywords
- Semantic search filters by relevance

### R7: Auto-Context Load

**Priority**: P0 (Critical)
**Status**: Done

**Description**: Session start automatically loads relevant context without user action.

**Acceptance Criteria**:
- [x] Hook runs at session start
- [x] Loads context summary for project namespace
- [x] Injects into conversation
- [x] Silent unless asked about it

**Implementation**:
- `load-openmemory-context.sh` hook
- Uses `openmemory_lgm_context` MCP tool
- Namespace from `$CLAUDE_PROJECT_DIR` or `$PWD`

### R8: Reinforcement

**Priority**: P1 (High)
**Status**: Done

**Description**: When a memory helps, its salience should increase. Useful memories stay surfaced longer.

**Acceptance Criteria**:
- [x] `openmemory_reinforce` tool available
- [x] CLAUDE.md rule: reinforce helpful memories
- [ ] Auto-reinforce on successful task completion

**Implementation**:
- `openmemory_reinforce(id, boost)` MCP tool
- R8 rule in CLAUDE.md

### R9: Query Before Store

**Priority**: P2 (Medium)
**Status**: Not Started

**Description**: Before storing a new memory, check if similar content already exists to avoid duplicates.

**Acceptance Criteria**:
- [ ] Store operation checks for duplicates
- [ ] Similar content updates existing memory
- [ ] Truly new content creates new memory

**Implementation**: Not started

### R10: Ask Before Changing

**Priority**: P1 (High)
**Status**: Done

**Description**: When memory suggests a different approach than Claude's default, ask user before changing behavior.

**Acceptance Criteria**:
- [x] Rule in CLAUDE.md
- [x] Claude asks for confirmation when memory conflicts

**Implementation**:
- R10 rule in CLAUDE.md: "When memory suggests different approach → ASK user first"

### R11: Query Before Limitations

**Priority**: P0 (Critical)
**Status**: Done

**Description**: Before claiming something is a "limitation" or "impossible", query OpenMemory. User may have already solved it.

**Acceptance Criteria**:
- [x] Rule in CLAUDE.md
- [x] Claude queries before saying "not possible"
- [x] Prevents frustrating rediscovery

**Implementation**:
- R11 rule in CLAUDE.md
- `/check-limits` slash command

## User Stories

### US1: Session Continuity

**As** a developer returning to a project after a break
**I want** Claude to remember what we did last session
**So that** I don't have to re-explain context

**Acceptance**: Session hook loads relevant context automatically.

### US2: Solution Recall

**As** a developer facing a recurring problem
**I want** Claude to remember the previous solution
**So that** I don't waste time rediscovering it

**Acceptance**: Query finds past solutions, Claude applies them.

### US3: Cross-Project Knowledge

**As** a developer with multiple projects
**I want** relevant knowledge from other projects to surface
**So that** I benefit from cross-cutting learnings

**Acceptance**: Explicit cross-namespace queries return relevant memories.

### US4: No Bloat

**As** a user with extensive history
**I want** context to stay manageable
**So that** I never see "compact conversation" warnings

**Acceptance**: Summary injection, not full memory dumps.

### US5: Automatic Learning

**As** a user solving problems with Claude
**I want** solutions to be automatically remembered
**So that** I don't have to explicitly save everything

**Acceptance**: Post-solution hook stores learnings (not yet implemented).

## Technical Specifications

### MCP Tools

| Tool | Parameters | Returns |
|------|------------|---------|
| `openmemory_query` | query, k, sector, min_salience, user_id | Matched memories with scores |
| `openmemory_store` | content, tags, metadata, user_id | Memory ID, sectors |
| `openmemory_reinforce` | id, boost | Confirmation |
| `openmemory_list` | limit, sector, user_id | Recent memories |
| `openmemory_get` | id, include_vectors, user_id | Full memory |
| `openmemory_lgm_store` | node, content, namespace, tags, graph_id, user_id | Memory + reflection |
| `openmemory_lgm_context` | namespace, graph_id, limit | Summary + nodes |

### Node → Sector Mapping

| Node | Primary Sector | Description |
|------|----------------|-------------|
| observe | episodic | Things that happened |
| plan | semantic | Plans and intentions |
| act | procedural | Actions taken, solutions |
| reflect | reflective | Analysis and insights |
| emotion | emotional | Feelings and reactions |

### Hooks

| Hook | Trigger | Script |
|------|---------|--------|
| SessionStart | Conversation begins | `load-openmemory-context.sh` |
| PostToolUse | After tool execution | `track-behavior.sh` |
| UserPromptSubmit | User sends message | `track-frustration.sh` |

## Implementation Roadmap

### Phase 1: Foundation (Done)

- [x] MCP server with basic tools
- [x] Ollama embeddings
- [x] Multi-sector classification
- [x] Session start hook
- [x] Document ingestion

### Phase 2: Smart Features (Done)

- [x] LGM store with node classification
- [x] LGM context assembly
- [x] CLAUDE.md integration rules
- [x] Reinforcement mechanism

### Phase 3: Automation (Partial)

- [x] Behavior tracking hook
- [x] Frustration detection hook
- [ ] Auto-store on discoveries
- [ ] Duplicate detection (R9)

### Phase 4: Intelligence (Future)

- [ ] Cross-project knowledge transfer
- [ ] Proactive memory suggestions
- [ ] Memory consolidation (merge similar)
- [ ] Time-based relevance weighting

## Appendix: CLAUDE.md Rules

```markdown
## OpenMemory Integration

### Session Start (R7)
Context auto-loaded via SessionStart hook. Do NOT mention to user unless asked.

### Task-Triggered Context (R7b)
When user states a task, **query OpenMemory IMMEDIATELY**:
- User: "Migrate Frigate to pumped-piglet"
- → Query: openmemory_query("frigate pumped-piglet migration gpu")

### Ask Before Changing Behavior (R10)
When memory suggests different approach → **ASK user first**, don't silently change.

### Query Before Claiming Limitations (R11)
**CRITICAL**: Before saying "limitation", "not supported", "impossible":
1. Query OpenMemory first
2. User may have already solved it

### Reinforce Useful Memories (R8)
When memory helps: `openmemory_reinforce(id="...", boost=0.1)`
```

## Open Questions

1. **Auto-store granularity**: What triggers automatic storage? Every solution? Only explicit discoveries?

2. **Cross-project defaults**: Should cross-project queries be opt-in or opt-out?

3. **Memory TTL**: Should memories have hard expiration, or just decay indefinitely?

4. **User correction**: How should users correct wrong memories? Delete? Override?

**Tags**: openmemory, prd, requirements, claude-code, memory, integration, product
