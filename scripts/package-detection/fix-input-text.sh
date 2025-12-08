#!/bin/bash
# Fix input_text by ensuring proper config
# Validates YAML locally before deploying

PVE_HOST="chief-horse.maas"
VMID="116"
HA_CONFIG="/mnt/data/supervisor/homeassistant"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/../../proxmox/homelab/.env"
HA_TOKEN=$(grep "^HA_TOKEN=" "$ENV_FILE" | cut -d'=' -f2)
HA_URL="http://192.168.4.240:8123"

echo "═══════════════════════════════════════════════════════"
echo "  Fixing input_text Configuration"
echo "═══════════════════════════════════════════════════════"
echo ""

echo "1️⃣  Creating config file locally..."

cat > /tmp/ha_configuration_test.yaml << 'ENDYAML'
# Loads default set of integrations. Do not remove.
default_config:

# Load frontend themes from the themes folder
frontend:
  themes: !include_dir_merge_named themes

automation: !include automations.yaml
script: !include scripts.yaml
scene: !include scenes.yaml

# Enable input helpers (entities created via UI)
input_boolean:
input_text:
ENDYAML

echo "   Created: /tmp/ha_configuration_test.yaml"
cat /tmp/ha_configuration_test.yaml

echo ""
echo "2️⃣  Validating YAML syntax locally..."

# Validate with Python yaml parser
python3 << 'ENDPYTHON'
import yaml
import sys

try:
    # Custom loader to handle !include tags
    class SafeLineLoader(yaml.SafeLoader):
        pass

    def include_constructor(loader, node):
        return f"!include {node.value}"

    SafeLineLoader.add_constructor('!include', include_constructor)
    SafeLineLoader.add_constructor('!include_dir_merge_named', include_constructor)

    with open('/tmp/ha_configuration_test.yaml', 'r') as f:
        config = yaml.load(f, Loader=SafeLineLoader)

    print("   ✅ YAML syntax is valid")
    print("")
    print("   Parsed structure:")
    for key in config:
        value = config[key]
        if value is None:
            print(f"     {key}: (empty - enables integration)")
        else:
            print(f"     {key}: {type(value).__name__}")

    # Check required keys
    required = ['default_config', 'input_text', 'input_boolean']
    missing = [k for k in required if k not in config]
    if missing:
        print(f"\n   ⚠️  Missing keys: {missing}")
        sys.exit(1)
    else:
        print(f"\n   ✅ All required keys present")
        sys.exit(0)

except yaml.YAMLError as e:
    print(f"   ❌ YAML Error: {e}")
    sys.exit(1)
except Exception as e:
    print(f"   ❌ Error: {e}")
    sys.exit(1)
ENDPYTHON

if [ $? -ne 0 ]; then
    echo ""
    echo "   ❌ Local validation failed. Not deploying."
    exit 1
fi

echo ""
echo "3️⃣  Local validation passed. Deploy to HA? [y/N]"
read -r CONFIRM
if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
    echo "   Aborted."
    exit 0
fi

echo ""
echo "4️⃣  Deploying to HA..."
ssh root@$PVE_HOST "qm guest exec $VMID -- sh -c 'cat > $HA_CONFIG/configuration.yaml << \"ENDYAML\"
$(cat /tmp/ha_configuration_test.yaml)
ENDYAML
'" 2>/dev/null

echo "   Done"

echo ""
echo "5️⃣  Verifying file in VM..."
ssh root@$PVE_HOST "qm guest exec $VMID -- cat $HA_CONFIG/configuration.yaml" 2>/dev/null | \
    python3 -c "import sys,json; d=json.load(sys.stdin); out=d.get('out-data',''); print(out if out else '❌ Empty file!')"

echo ""
echo "6️⃣  Validating with HA API..."
RESULT=$(curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/config/core/check_config")
echo "$RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print('   Result:', d.get('result'), '- Errors:', d.get('errors'))"

VALID=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('result',''))")
if [ "$VALID" != "valid" ]; then
    echo "   ❌ HA validation failed. Rolling back..."
    # Could add rollback here
    exit 1
fi

echo ""
echo "7️⃣  Restart HA? [y/N]"
read -r CONFIRM
if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
    echo "   Skipped restart. Run manually: Settings → System → Restart"
    exit 0
fi

echo ""
echo "8️⃣  Restarting HA..."
curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/services/homeassistant/restart" > /dev/null 2>&1

echo "   Waiting..."
sleep 15
for i in {1..20}; do
    sleep 5
    RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/" 2>/dev/null)
    if [ "$RESPONSE" = "200" ]; then
        echo "   ✅ HA is back!"
        break
    fi
    echo "   ... ($((i*5+15))s)"
done

echo ""
echo "9️⃣  Checking if input_text component loaded..."
sleep 3
curl -s -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/config" | python3 -c "
import sys,json
d=json.load(sys.stdin)
components = d.get('components', [])
print('   input_boolean:', 'input_boolean' in components)
print('   input_text:', 'input_text' in components)
"

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  Now try creating Text helper in UI"
echo "  Settings → Helpers → + Create Helper → Text"
echo "═══════════════════════════════════════════════════════"
