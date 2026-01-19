#!/bin/bash
# Analyze Claude Code session metrics
# Combines behavior tracking, user feedback, and /cost data
# Usage: ./analyze-sessions.sh [--by-condition]

set -e

METRICS_DIR="$HOME/.claude/metrics"
BEHAVIOR_LOG="$METRICS_DIR/behavior.jsonl"
FEEDBACK_LOG="$METRICS_DIR/feedback.jsonl"
FRUSTRATION_LOG="$METRICS_DIR/frustration.jsonl"
STATS_LOG="$METRICS_DIR/stats.jsonl"
STATS_CACHE="$HOME/.claude/stats-cache.json"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${CYAN}╔════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║   Claude Code Session Quality Report   ║${NC}"
echo -e "${CYAN}╚════════════════════════════════════════╝${NC}"
echo ""

# Check if logs exist
if [[ ! -f "$BEHAVIOR_LOG" && ! -f "$FEEDBACK_LOG" && ! -f "$FRUSTRATION_LOG" ]]; then
    echo -e "${YELLOW}No metrics data found yet.${NC}"
    echo "Run some sessions with hooks enabled to collect data."
    exit 0
fi

# Auto-detected Frustration (from user messages)
echo -e "${GREEN}=== Auto-Detected Frustration ===${NC}"
if [[ -f "$FRUSTRATION_LOG" ]]; then
    TOTAL_OUTBURSTS=$(wc -l < "$FRUSTRATION_LOG" | tr -d ' ')
    AUTO_WTF=$(grep -c '"type":"wtf"' "$FRUSTRATION_LOG" 2>/dev/null) || AUTO_WTF=0
    AUTO_OMFG=$(grep -c '"type":"omfg"' "$FRUSTRATION_LOG" 2>/dev/null) || AUTO_OMFG=0
    AUTO_IDIOT=$(grep -c '"type":"idiot"' "$FRUSTRATION_LOG" 2>/dev/null) || AUTO_IDIOT=0
    AUTO_MFER=$(grep -c '"type":"mfer"' "$FRUSTRATION_LOG" 2>/dev/null) || AUTO_MFER=0
    AUTO_RAGE=$(grep -c '"type":"rage"' "$FRUSTRATION_LOG" 2>/dev/null) || AUTO_RAGE=0

    AUTO_SCORE=$((AUTO_WTF + AUTO_OMFG * 2 + AUTO_IDIOT * 3 + AUTO_MFER * 3 + AUTO_RAGE))

    echo "Total outbursts detected:  $TOTAL_OUTBURSTS"
    echo ""
    [[ $AUTO_WTF -gt 0 ]] && echo -e "  ${YELLOW}WTF:      $AUTO_WTF${NC}" || echo "  WTF:      0"
    [[ $AUTO_OMFG -gt 0 ]] && echo -e "  ${YELLOW}OMFG:     $AUTO_OMFG${NC}" || echo "  OMFG:     0"
    [[ $AUTO_IDIOT -gt 0 ]] && echo -e "  ${RED}IDIOT:    $AUTO_IDIOT${NC}" || echo "  IDIOT:    0"
    [[ $AUTO_MFER -gt 0 ]] && echo -e "  ${RED}MFER:     $AUTO_MFER${NC}" || echo "  MFER:     0"
    [[ $AUTO_RAGE -gt 0 ]] && echo -e "  ${YELLOW}RAGE:     $AUTO_RAGE${NC}" || echo "  RAGE:     0"
    echo ""
    echo "  Auto Frustration Score:  $AUTO_SCORE"

    # Show recent outbursts
    if [[ $TOTAL_OUTBURSTS -gt 0 ]]; then
        echo ""
        echo "Recent outbursts:"
        tail -5 "$FRUSTRATION_LOG" | jq -r '"  \(.date) \(.time): \(.type)"' 2>/dev/null || tail -3 "$FRUSTRATION_LOG"
    fi
else
    echo "No frustration detected yet. (That's good... or you haven't used it much)"
fi

echo ""

# Behavior Metrics
echo -e "${GREEN}=== Behavior Tracking ===${NC}"
if [[ -f "$BEHAVIOR_LOG" ]]; then
    TOTAL_EVENTS=$(wc -l < "$BEHAVIOR_LOG" | tr -d ' ')
    SSH_ATTEMPTS=$(grep -c "ssh_k3s_attempt" "$BEHAVIOR_LOG" 2>/dev/null || echo 0)
    GIT_ADD_ALL=$(grep -c "git_add_all_attempt" "$BEHAVIOR_LOG" 2>/dev/null || echo 0)
    LONG_ONELINERS=$(grep -c "long_one_liner" "$BEHAVIOR_LOG" 2>/dev/null || echo 0)
    SECRETS=$(grep -c "potential_secret" "$BEHAVIOR_LOG" 2>/dev/null || echo 0)
    SENSITIVE=$(grep -c "sensitive_file" "$BEHAVIOR_LOG" 2>/dev/null || echo 0)

    echo "Total tracked events:     $TOTAL_EVENTS"
    echo ""
    echo "Mistake attempts:"
    [[ $SSH_ATTEMPTS -gt 0 ]] && echo -e "  ${RED}SSH to K3s VMs:         $SSH_ATTEMPTS${NC}" || echo "  SSH to K3s VMs:         $SSH_ATTEMPTS ✓"
    [[ $GIT_ADD_ALL -gt 0 ]] && echo -e "  ${RED}git add . / -A:         $GIT_ADD_ALL${NC}" || echo "  git add . / -A:         $GIT_ADD_ALL ✓"
    echo ""
    echo "Warnings:"
    echo "  Long one-liners:        $LONG_ONELINERS"
    echo "  Potential secrets:      $SECRETS"
    echo "  Sensitive file edits:   $SENSITIVE"
else
    echo "No behavior data yet."
fi

echo ""

# Feedback Metrics
echo -e "${GREEN}=== User Feedback ===${NC}"
if [[ -f "$FEEDBACK_LOG" ]]; then
    TOTAL_SESSIONS=$(wc -l < "$FEEDBACK_LOG" | tr -d ' ')

    if [[ $TOTAL_SESSIONS -gt 0 ]]; then
        # Calculate average rating
        AVG_RATING=$(jq -s 'map(.rating) | add / length | . * 10 | round / 10' "$FEEDBACK_LOG" 2>/dev/null || echo "N/A")

        # Count sessions with mistakes
        MISTAKE_SESSIONS=$(grep -c '"mistakes":"y"' "$FEEDBACK_LOG" 2>/dev/null || echo 0)
        MISTAKE_PCT=$((MISTAKE_SESSIONS * 100 / TOTAL_SESSIONS))

        # Frustration totals
        TOTAL_WTF=$(jq -s 'map(.wtf // 0) | add' "$FEEDBACK_LOG" 2>/dev/null || echo 0)
        TOTAL_OMFG=$(jq -s 'map(.omfg // 0) | add' "$FEEDBACK_LOG" 2>/dev/null || echo 0)
        TOTAL_IDIOT=$(jq -s 'map(.idiot // 0) | add' "$FEEDBACK_LOG" 2>/dev/null || echo 0)
        FRUSTRATION_SCORE=$((TOTAL_WTF + TOTAL_OMFG * 2 + TOTAL_IDIOT * 3))

        echo "Total rated sessions:     $TOTAL_SESSIONS"
        echo "Average rating:           $AVG_RATING / 5"
        echo "Sessions with mistakes:   $MISTAKE_SESSIONS ($MISTAKE_PCT%)"
        echo ""
        echo -e "${YELLOW}Frustration Metrics:${NC}"
        echo "  WTF moments (confusion):     $TOTAL_WTF"
        echo "  OMFG moments (frustration):  $TOTAL_OMFG"
        echo "  \"You idiot\" (dumb mistakes): $TOTAL_IDIOT"
        echo "  Frustration Score:           $FRUSTRATION_SCORE (lower = better)"
        echo "  (Score = WTF + 2*OMFG + 3*IDIOT)"

        # By condition if requested
        if [[ "$1" == "--by-condition" ]]; then
            echo ""
            echo -e "${CYAN}By Condition:${NC}"
            for COND in full lean bare; do
                COND_DATA=$(grep "\"condition\":\"$COND\"" "$FEEDBACK_LOG" 2>/dev/null || true)
                COND_COUNT=$(echo "$COND_DATA" | grep -c . 2>/dev/null || echo 0)
                if [[ $COND_COUNT -gt 0 ]]; then
                    COND_AVG=$(echo "$COND_DATA" | jq -s 'map(.rating) | add / length | . * 10 | round / 10' 2>/dev/null || echo "N/A")
                    COND_MISTAKES=$(echo "$COND_DATA" | grep -c '"mistakes":"y"' 2>/dev/null || echo 0)
                    COND_WTF=$(echo "$COND_DATA" | jq -s 'map(.wtf // 0) | add' 2>/dev/null || echo 0)
                    COND_OMFG=$(echo "$COND_DATA" | jq -s 'map(.omfg // 0) | add' 2>/dev/null || echo 0)
                    COND_IDIOT=$(echo "$COND_DATA" | jq -s 'map(.idiot // 0) | add' 2>/dev/null || echo 0)
                    COND_FRUST=$((COND_WTF + COND_OMFG * 2 + COND_IDIOT * 3))
                    echo "  $COND:"
                    echo "    Sessions: $COND_COUNT, Avg Rating: $COND_AVG, Mistakes: $COND_MISTAKES"
                    echo "    Frustration: WTF=$COND_WTF OMFG=$COND_OMFG IDIOT=$COND_IDIOT (Score: $COND_FRUST)"
                fi
            done
        fi
    else
        echo "No feedback data yet."
    fi
else
    echo "No feedback data yet."
fi

echo ""

# Recent events
echo -e "${GREEN}=== Recent Activity ===${NC}"
if [[ -f "$BEHAVIOR_LOG" ]]; then
    echo "Last 5 behavior events:"
    tail -5 "$BEHAVIOR_LOG" | jq -r '"  \(.event) at \(.ts | todate)"' 2>/dev/null || tail -5 "$BEHAVIOR_LOG"
fi

# Token Usage (from stats-cache.json)
echo -e "${GREEN}=== Token Usage (All Time) ===${NC}"
if [[ -f "$STATS_CACHE" ]]; then
    OPUS_IN=$(jq -r '.modelUsage["claude-opus-4-5-20251101"].inputTokens // 0' "$STATS_CACHE")
    OPUS_OUT=$(jq -r '.modelUsage["claude-opus-4-5-20251101"].outputTokens // 0' "$STATS_CACHE")
    SONNET_IN=$(jq -r '.modelUsage["claude-sonnet-4-5-20250929"].inputTokens // 0' "$STATS_CACHE")
    SONNET_OUT=$(jq -r '.modelUsage["claude-sonnet-4-5-20250929"].outputTokens // 0' "$STATS_CACHE")
    TOTAL_SESSIONS=$(jq -r '.totalSessions // 0' "$STATS_CACHE")
    TOTAL_MESSAGES=$(jq -r '.totalMessages // 0' "$STATS_CACHE")

    # Format large numbers
    fmt() { printf "%'d" "$1" 2>/dev/null || echo "$1"; }

    echo "Sessions: $TOTAL_SESSIONS  Messages: $TOTAL_MESSAGES"
    echo ""
    echo "Opus 4.5:   $(fmt $OPUS_IN) in / $(fmt $OPUS_OUT) out"
    echo "Sonnet 4.5: $(fmt $SONNET_IN) in / $(fmt $SONNET_OUT) out"
else
    echo "No stats cache. Run /stats in Claude Code."
fi

echo ""
echo -e "${CYAN}Tip: Run with --by-condition to see breakdown by setup type${NC}"
echo -e "${CYAN}      Run capture-stats.sh to log current stats for tracking${NC}"
