# Voice PE + Ollama Debugging Scripts

Scripts for debugging Home Assistant Voice PE with Ollama LLM integration.

## Prerequisites

- HA token in `~/code/home/proxmox/homelab/.env` as `HA_TOKEN=xxx`
- `jq` installed
- `curl` installed

## Scripts

| Script | Purpose |
|--------|---------|
| `check-conversation-agents.sh` | List conversation agents and their capabilities |
| `test-ollama-direct.sh` | Test Ollama directly (bypass pipeline) |
| `test-pipeline.sh` | Test default pipeline (what Voice PE uses) |
| `check-light-state.sh` | Check a light's current state |
| `list-lights.sh` | List all lights with friendly names |
| `check-voice-pe-pipeline.sh` | See which pipeline Voice PE is using |
| `reload-ollama.sh` | Reload Ollama integration (fixes tool calling after restart) |
| `test-ollama-e2e.sh` | Full end-to-end test with state verification |
| `quick-test.sh` | Quick "did Ollama lie?" test |

## Usage Examples

```bash
# Check if conversation agents support device control
./check-conversation-agents.sh

# Test Ollama with a specific command
./test-ollama-direct.sh "turn on Monitor"

# Compare with default pipeline
./test-pipeline.sh "turn on Monitor"

# Quick test - did it actually work?
./quick-test.sh

# Full verification test
./test-ollama-e2e.sh

# Fix tool calling after HA restart
./reload-ollama.sh
```

## Common Issues

### Ollama says it did something but didn't

1. Run `./reload-ollama.sh` to reload the integration
2. Check `supported_features` with `./check-conversation-agents.sh` (should be 1)
3. Verify with `./test-ollama-e2e.sh`

### Wrong device controlled

Check device names are distinct:
```bash
./list-lights.sh
```

Names like "Office Front" and "office light back" will confuse the LLM. Use distinct names like "Monitor" and "Shelf".

### Voice PE using wrong pipeline

```bash
./check-voice-pe-pipeline.sh
```

Make sure it's set to the pipeline with Ollama Conversation as the agent.

## Environment Variables

- `HA_URL` - Override HA URL (default: `http://192.168.4.240:8123`)
- `LIGHT_ENTITY` - Override default light entity for tests
