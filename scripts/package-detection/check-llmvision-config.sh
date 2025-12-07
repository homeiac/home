#!/bin/bash
# Check LLM Vision integration configuration

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/../../proxmox/homelab/.env"

HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2)
HA_URL="http://192.168.4.240:8123"

echo "=== LLM Vision Configuration ==="
curl -s -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/config/config_entries/entry" | \
    python3 -c "
import sys, json
d = json.load(sys.stdin)
llmvision = [e for e in d if e.get('domain') == 'llmvision']
print(f'Found {len(llmvision)} LLM Vision provider(s):')
for c in llmvision:
    print(f'  Provider: {c.get(\"title\", \"unknown\")}')
    print(f'  Entry ID: {c.get(\"entry_id\", \"unknown\")}')
    print()
"

echo "=== Ollama Model Status ==="
OLLAMA_URL="http://192.168.4.81"
curl -s "$OLLAMA_URL/api/tags" | \
    python3 -c "
import sys, json
d = json.load(sys.stdin)
models = d.get('models', [])
print(f'Available models ({len(models)}):')
for m in models:
    name = m['name']
    size_gb = m.get('size', 0) / (1024**3)
    is_vision = any(v in name.lower() for v in ['llava', 'moondream', 'bakllava', 'vision'])
    marker = ' 👁️ VISION' if is_vision else ''
    print(f'  - {name} ({size_gb:.1f}GB){marker}')
"
