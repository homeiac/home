#!/bin/bash
# Compare two Ollama models head-to-head for Voice PE use case
# Usage: compare-models.sh [model_a] [model_b]
#
# Tests realistic Voice PE prompts:
#   1. Conversation (quick Q&A - the main voice assistant use case)
#   2. Time parsing (reminder extraction)
#   3. Entity control (smart home commands)
#   4. Reasoning (multi-step home automation logic)
#
# Each test runs 3 iterations and reports avg speed + quality

set -e

KUBECONFIG="${KUBECONFIG:-$HOME/kubeconfig}"
export KUBECONFIG

OLLAMA_NS="${OLLAMA_NS:-ollama}"
MODEL_A="${1:-qwen3.5:4b}"
MODEL_B="${2:-gemma4:e2b}"
ITERATIONS=3
TMPDIR_WORK=$(mktemp -d)
trap 'rm -rf "$TMPDIR_WORK"' EXIT

# Get Ollama URL
OLLAMA_IP=$(kubectl get svc -n "$OLLAMA_NS" -o jsonpath='{.items[0].status.loadBalancer.ingress[0].ip}' 2>/dev/null)
OLLAMA_PORT=$(kubectl get svc -n "$OLLAMA_NS" -o jsonpath='{.items[0].spec.ports[0].port}' 2>/dev/null)
OLLAMA_URL="http://${OLLAMA_IP}:${OLLAMA_PORT:-80}"

# Voice PE system prompt (matches HA config)
SYSTEM_PROMPT="You are a helpful home assistant. Be concise - voice responses should be short and natural. Do not use markdown or special formatting."

# Test prompts that match real Voice PE usage
TEST_NAMES=(
    "Quick Q&A (voice conversation)"
    "Time parsing (reminders)"
    "Entity control (smart home)"
    "Multi-step reasoning"
)
TEST_PROMPTS=(
    "What is the weather usually like in April?"
    "Remind me to take out the trash in 2 hours and 30 minutes. What time would that be if it is currently 6:15 PM?"
    "Turn off all the lights in the living room and set the bedroom to 30 percent brightness"
    "The garage door has been open for 20 minutes and it is after 10 PM. What should I do?"
)

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

echo -e "${BOLD}========================================${NC}"
echo -e "${BOLD}  Ollama Model Comparison for Voice PE${NC}"
echo -e "${BOLD}========================================${NC}"
echo ""
echo -e "  Model A: ${CYAN}$MODEL_A${NC}"
echo -e "  Model B: ${CYAN}$MODEL_B${NC}"
echo -e "  URL:     $OLLAMA_URL"
echo -e "  Iters:   $ITERATIONS per test"
echo ""

# Check API is reachable
if ! curl -s --connect-timeout 5 "$OLLAMA_URL/api/tags" > /dev/null 2>&1; then
    echo -e "${RED}ERROR: Ollama API unreachable at $OLLAMA_URL${NC}"
    exit 1
fi

run_test() {
    local model="$1"
    local prompt="$2"
    local system="$3"
    local outfile="$4"

    # Build JSON payload safely via python
    python3 -c "
import json
print(json.dumps({
    'model': '${model}',
    'prompt': $(python3 -c "import json; print(json.dumps('''${prompt}'''))"),
    'system': $(python3 -c "import json; print(json.dumps('''${system}'''))"),
    'stream': False,
    'options': {'num_predict': 256}
}))
" > "$TMPDIR_WORK/payload.json"

    curl -s --connect-timeout 30 --max-time 120 \
        -X POST "$OLLAMA_URL/api/generate" \
        -H "Content-Type: application/json" \
        -d @"$TMPDIR_WORK/payload.json" > "$outfile" 2>/dev/null
}

parse_result() {
    local file="$1"
    python3 << 'PYEOF' "$file"
import json, sys
try:
    with open(sys.argv[1]) as f:
        d = json.load(f)
    load_s = d.get('load_duration', 0) / 1e9
    prompt_s = d.get('prompt_eval_duration', 0) / 1e9
    eval_s = d.get('eval_duration', 0) / 1e9
    total_s = d.get('total_duration', 0) / 1e9
    tokens = d.get('eval_count', 0)
    tps = tokens / eval_s if eval_s > 0 else 0
    ttft = load_s + prompt_s
    print(f'{total_s:.2f}|{tps:.1f}|{tokens}|{ttft:.2f}|{eval_s:.2f}')
except Exception as e:
    print(f'0|0|0|0|0')
PYEOF
}

extract_response() {
    local file="$1"
    python3 << 'PYEOF' "$file"
import json, sys
try:
    with open(sys.argv[1]) as f:
        d = json.load(f)
    r = d.get('response', 'ERROR').strip()
    if len(r) > 300:
        r = r[:300] + '...'
    print(r)
except:
    print('ERROR: Could not parse response')
PYEOF
}

ensure_model() {
    local model="$1"
    echo -ne "  Checking ${model}... "

    local exists
    exists=$(curl -s "$OLLAMA_URL/api/tags" | python3 -c "
import json, sys
d = json.load(sys.stdin)
names = [m['name'] for m in d.get('models', [])]
print('yes' if '$model' in names or '${model}:latest' in names else 'no')
" 2>/dev/null)

    if [[ "$exists" == "yes" ]]; then
        echo -e "${GREEN}available${NC}"
        return 0
    fi

    echo -e "${YELLOW}pulling (this may take a few minutes)...${NC}"
    curl -s --max-time 600 -X POST "$OLLAMA_URL/api/pull" \
        -d "{\"name\":\"$model\",\"stream\":false}" > "$TMPDIR_WORK/pull_result.json" 2>/dev/null

    if grep -q "success" "$TMPDIR_WORK/pull_result.json" 2>/dev/null; then
        echo -e "  ${GREEN}Pull complete${NC}"
        return 0
    else
        echo -e "  ${RED}Pull failed$(cat "$TMPDIR_WORK/pull_result.json" 2>/dev/null)${NC}"
        return 1
    fi
}

warmup_model() {
    local model="$1"
    echo -ne "  Warming up ${model}... "
    python3 -c "import json; print(json.dumps({'model':'$model','prompt':'hi','stream':False,'options':{'num_predict':1}}))" \
        | curl -s --max-time 60 -X POST "$OLLAMA_URL/api/generate" -H "Content-Type: application/json" -d @- > /dev/null 2>&1
    echo "done"
}

# Ensure both models are available
echo -e "${BOLD}--- Ensuring Models Available ---${NC}"
ensure_model "$MODEL_A" || exit 1
ensure_model "$MODEL_B" || exit 1
echo ""

# Results storage
declare -a RESULTS_A_TOTAL=()
declare -a RESULTS_A_TPS=()
declare -a RESULTS_B_TOTAL=()
declare -a RESULTS_B_TPS=()

for t in "${!TEST_NAMES[@]}"; do
    test_name="${TEST_NAMES[$t]}"
    test_prompt="${TEST_PROMPTS[$t]}"

    echo -e "${BOLD}--- Test $((t+1)): ${test_name} ---${NC}"
    echo -e "  Prompt: \"${test_prompt:0:80}\""
    echo ""

    # --- Model A ---
    echo -e "  ${CYAN}[$MODEL_A]${NC}"
    warmup_model "$MODEL_A"

    a_total_sum=0
    a_tps_sum=0

    for i in $(seq 1 $ITERATIONS); do
        outfile="$TMPDIR_WORK/result_a_${t}_${i}.json"
        run_test "$MODEL_A" "$test_prompt" "$SYSTEM_PROMPT" "$outfile"
        parsed=$(parse_result "$outfile")
        total=$(echo "$parsed" | cut -d'|' -f1)
        tps=$(echo "$parsed" | cut -d'|' -f2)
        tokens=$(echo "$parsed" | cut -d'|' -f3)
        ttft=$(echo "$parsed" | cut -d'|' -f4)

        a_total_sum=$(python3 -c "print($a_total_sum + $total)")
        a_tps_sum=$(python3 -c "print($a_tps_sum + $tps)")

        echo -e "    Run $i: ${total}s total, ${tps} tok/s, ${tokens} tokens, TTFT ${ttft}s"
    done

    a_last_response=$(extract_response "$TMPDIR_WORK/result_a_${t}_${ITERATIONS}.json")
    a_avg_total=$(python3 -c "print(f'{$a_total_sum / $ITERATIONS:.2f}')")
    a_avg_tps=$(python3 -c "print(f'{$a_tps_sum / $ITERATIONS:.1f}')")
    RESULTS_A_TOTAL+=("$a_avg_total")
    RESULTS_A_TPS+=("$a_avg_tps")

    echo -e "    ${GREEN}Avg: ${a_avg_total}s, ${a_avg_tps} tok/s${NC}"
    echo -e "    Response: ${a_last_response:0:200}"
    echo ""

    # --- Model B ---
    echo -e "  ${CYAN}[$MODEL_B]${NC}"
    warmup_model "$MODEL_B"

    b_total_sum=0
    b_tps_sum=0

    for i in $(seq 1 $ITERATIONS); do
        outfile="$TMPDIR_WORK/result_b_${t}_${i}.json"
        run_test "$MODEL_B" "$test_prompt" "$SYSTEM_PROMPT" "$outfile"
        parsed=$(parse_result "$outfile")
        total=$(echo "$parsed" | cut -d'|' -f1)
        tps=$(echo "$parsed" | cut -d'|' -f2)
        tokens=$(echo "$parsed" | cut -d'|' -f3)
        ttft=$(echo "$parsed" | cut -d'|' -f4)

        b_total_sum=$(python3 -c "print($b_total_sum + $total)")
        b_tps_sum=$(python3 -c "print($b_tps_sum + $tps)")

        echo -e "    Run $i: ${total}s total, ${tps} tok/s, ${tokens} tokens, TTFT ${ttft}s"
    done

    b_last_response=$(extract_response "$TMPDIR_WORK/result_b_${t}_${ITERATIONS}.json")
    b_avg_total=$(python3 -c "print(f'{$b_total_sum / $ITERATIONS:.2f}')")
    b_avg_tps=$(python3 -c "print(f'{$b_tps_sum / $ITERATIONS:.1f}')")
    RESULTS_B_TOTAL+=("$b_avg_total")
    RESULTS_B_TPS+=("$b_avg_tps")

    echo -e "    ${GREEN}Avg: ${b_avg_total}s, ${b_avg_tps} tok/s${NC}"
    echo -e "    Response: ${b_last_response:0:200}"
    echo ""
done

# Summary
echo -e "${BOLD}========================================"
echo -e "  SUMMARY: Voice PE Model Comparison"
echo -e "========================================${NC}"
echo ""
printf "  %-35s  %15s  %15s\n" "Test" "$MODEL_A" "$MODEL_B"
printf "  %-35s  %15s  %15s\n" "---" "---" "---"

for t in "${!TEST_NAMES[@]}"; do
    printf "  %-35s  %7ss %5st/s  %7ss %5st/s\n" \
        "${TEST_NAMES[$t]}" \
        "${RESULTS_A_TOTAL[$t]}" "${RESULTS_A_TPS[$t]}" \
        "${RESULTS_B_TOTAL[$t]}" "${RESULTS_B_TPS[$t]}"
done

echo ""

# Final analysis
python3 << PYEOF
a_tps = [${RESULTS_A_TPS[0]:-0}, ${RESULTS_A_TPS[1]:-0}, ${RESULTS_A_TPS[2]:-0}, ${RESULTS_A_TPS[3]:-0}]
b_tps = [${RESULTS_B_TPS[0]:-0}, ${RESULTS_B_TPS[1]:-0}, ${RESULTS_B_TPS[2]:-0}, ${RESULTS_B_TPS[3]:-0}]
a_total = [${RESULTS_A_TOTAL[0]:-0}, ${RESULTS_A_TOTAL[1]:-0}, ${RESULTS_A_TOTAL[2]:-0}, ${RESULTS_A_TOTAL[3]:-0}]
b_total = [${RESULTS_B_TOTAL[0]:-0}, ${RESULTS_B_TOTAL[1]:-0}, ${RESULTS_B_TOTAL[2]:-0}, ${RESULTS_B_TOTAL[3]:-0}]

a_avg_tps = sum(a_tps) / len(a_tps)
b_avg_tps = sum(b_tps) / len(b_tps)
a_avg_total = sum(a_total) / len(a_total)
b_avg_total = sum(b_total) / len(b_total)

model_a = "${MODEL_A}"
model_b = "${MODEL_B}"

print(f'  Overall Average:')
print(f'    {model_a}: {a_avg_total:.2f}s, {a_avg_tps:.1f} tok/s')
print(f'    {model_b}: {b_avg_total:.2f}s, {b_avg_tps:.1f} tok/s')
print()

speed_diff = ((b_avg_tps - a_avg_tps) / a_avg_tps * 100) if a_avg_tps > 0 else 0
time_diff = ((a_avg_total - b_avg_total) / a_avg_total * 100) if a_avg_total > 0 else 0

if b_avg_tps > a_avg_tps:
    print(f'  --> {model_b} is {speed_diff:.0f}% faster ({time_diff:.0f}% less latency)')
else:
    print(f'  --> {model_a} is {-speed_diff:.0f}% faster ({-time_diff:.0f}% less latency)')

print()
print(f'  Voice PE Threshold (>10 tok/s for acceptable voice latency):')
print(f'    {model_a}: {"PASS" if a_avg_tps > 10 else "FAIL"} ({a_avg_tps:.1f} tok/s)')
print(f'    {model_b}: {"PASS" if b_avg_tps > 10 else "FAIL"} ({b_avg_tps:.1f} tok/s)')
print()

if b_avg_tps < 10:
    print(f'  RECOMMENDATION: KEEP {model_a} - {model_b} too slow for Voice PE')
elif b_avg_tps > a_avg_tps * 0.9:
    print(f'  RECOMMENDATION: SWITCH to {model_b} - comparable or better speed with newer model')
else:
    print(f'  RECOMMENDATION: KEEP {model_a} - speed advantage outweighs {model_b} quality gains')
PYEOF
echo ""
