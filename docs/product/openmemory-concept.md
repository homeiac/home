# OpenMemory Integration - Concept Document

**Status**: Active Development
**Owner**: Homelab AI
**Created**: 2025-12-17
**Last Updated**: 2025-12-17

## Executive Summary

OpenMemory provides persistent memory for Claude Code sessions, enabling context retention across conversations without bloating CLAUDE.md. This integration transforms Claude Code from a stateless assistant into a knowledge-accumulating partner that learns from each session.

## Problem Statement

### Current Pain Points

1. **Context Loss**: Every new Claude Code session starts from zero. Previous discoveries, solutions, and learnings are lost.

2. **CLAUDE.md Bloat**: To preserve context, users add more to CLAUDE.md, eventually hitting token limits and "compact conversation" warnings.

3. **Re-Discovery**: Same problems get re-investigated. Same solutions get re-discovered. Time wasted on known issues.

4. **Manual Memory**: Users must explicitly remind Claude of past work: "Remember when we fixed the SSH issue..."

5. **Project Silos**: Knowledge from one project doesn't benefit another, even when relevant.

### Impact

- Developer frustration ("WTF we already fixed this!")
- Wasted tokens re-explaining context
- Inconsistent solutions to recurring problems
- Knowledge decay over time

## Vision

> **Claude Code with OpenMemory remembers everything you've done together and surfaces relevant knowledge exactly when you need it.**

### Success State

1. Start a new session - relevant context is already loaded
2. Mention "Frigate" - past Frigate solutions appear
3. Solve a new problem - it's automatically stored
4. Next week, same issue - Claude already knows the fix
5. Different project - cross-cutting knowledge transfers

## Target Users

| User | Need | Current Workaround |
|------|------|-------------------|
| Homelab maintainer | Remember past fixes | Grep through docs |
| Daily Claude user | Context across sessions | Copy-paste from old chats |
| Multi-project developer | Cross-project knowledge | Manual CLAUDE.md updates |

## Core Principles

### P1: Context Stays Small
Never hit "compact conversation". External memory, not bigger prompts.

### P2: Seamless Integration
Shouldn't feel like extra work. Auto-store on discoveries, auto-retrieve on tasks.

### P3: Knowledge Graph
Related things surface together. Not just keyword search - semantic understanding.

### P4: Project Scope
Different repos get different default contexts. No cross-contamination unless relevant.

### P5: Task Scope
Relevant memories surface for the current task, not everything ever stored.

### P6: Decay and Reinforcement
Useful memories get reinforced and stay salient. Unused memories naturally fade.

## Solution Approach

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Claude Code                               │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────────┐ │
│  │ Session Hook │  │  MCP Tools   │  │   CLAUDE.md Rules      │ │
│  │ (auto-load)  │  │ (query/store)│  │ (when to use memory)   │ │
│  └──────┬───────┘  └──────┬───────┘  └────────────────────────┘ │
│         │                 │                                      │
└─────────┼─────────────────┼──────────────────────────────────────┘
          │                 │
          ▼                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                      OpenMemory Backend                          │
│                                                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │   MCP API   │  │  REST API   │  │   Ollama Embeddings     │  │
│  │ (7 tools)   │  │ (/memory/*) │  │   (semantic search)     │  │
│  └──────┬──────┘  └──────┬──────┘  └───────────┬─────────────┘  │
│         │                │                     │                 │
│         └────────────────┴─────────────────────┘                 │
│                          │                                       │
│                          ▼                                       │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                    SQLite + Vector Store                   │  │
│  │  • Memories table (content, sectors, salience, decay)     │  │
│  │  • Vector embeddings per sector (Ollama nomic-embed-text) │  │
│  │  • Reflection/waypoint graph                              │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### Key Capabilities

| Capability | Implementation | Status |
|------------|----------------|--------|
| Semantic search | Ollama embeddings + vector similarity | Done |
| Multi-sector memory | episodic, semantic, procedural, emotional, reflective | Done |
| Node-based storage | observe, plan, act, reflect, emotion → sector mapping | Done |
| Auto context assembly | `/lgm/context` summarizes relevant memories | Done |
| Session hook | Auto-loads context at session start | Done |
| Salience decay | Unused memories fade over time | Done |
| Reinforcement | Useful memories get boosted | Done |
| Document ingestion | Bulk ingest with chunking | Done |

## Current State (What Exists)

### MCP Tools (7)

| Tool | Purpose | Node Type |
|------|---------|-----------|
| `openmemory_query` | Semantic search | - |
| `openmemory_store` | Basic storage | - |
| `openmemory_reinforce` | Boost salience | - |
| `openmemory_list` | List recent | - |
| `openmemory_get` | Get by ID | - |
| `openmemory_lgm_store` | Smart storage | observe/plan/act/reflect/emotion |
| `openmemory_lgm_context` | Auto-assembled summary | - |

### Hooks

| Hook | Trigger | Purpose |
|------|---------|---------|
| `load-openmemory-context.sh` | Session start | Auto-inject relevant context |
| `track-behavior.sh` | Post tool use | Track Claude behavior for metrics |
| `track-frustration.sh` | User prompt | Detect frustration keywords |
| `session-feedback.sh` | Session end | Collect user feedback |

### Ingestion

| Script | Purpose |
|--------|---------|
| `ingest-docs.sh` | Bulk ingest docs, scripts, configs |
| `ingest-file.sh` | Single file ingestion |

### CLAUDE.md Integration

Rules added for:
- R7: Auto-context load at session start
- R7b: Task-triggered queries
- R8: Reinforce useful memories
- R10: Ask before changing behavior
- R11: Query before claiming limitations

## Gaps (What's Missing)

See PRD for detailed requirements.

## Success Metrics

| Metric | Target | How to Measure |
|--------|--------|----------------|
| Context reuse | 50% of sessions use stored memory | Hook telemetry |
| Re-discovery reduction | 80% fewer "we already solved this" | Frustration tracking |
| Token efficiency | Never hit compact | Session length tracking |
| User satisfaction | No "MFER" frustrations about memory | Frustration keywords |

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Stale memories mislead | Medium | Decay mechanism, user correction |
| Memory bloat | Low | Chunking, salience filtering |
| Wrong context loaded | Medium | Namespace isolation, relevance scoring |
| Secrets in memories | High | Never store credentials, scrub on ingest |

## Related Documents

- [PRD: OpenMemory Integration](./openmemory-prd.md)
- [Methodology: Outcome-Anchored Research](../methodology/outcome-anchored-research.md)
- [Reference: Performance Diagnosis Runbook](../methodology/performance-diagnosis-runbook.md)

**Tags**: openmemory, concept, product, claude-code, memory, integration, ai-first
