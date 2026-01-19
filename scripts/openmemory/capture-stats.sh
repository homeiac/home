#!/bin/bash
# Capture Claude Code /stats for historical tracking
# Usage: ./capture-stats.sh
#
# Reads from ~/.claude/stats-cache.json (updated by /stats command)

set -e

METRICS_DIR="$HOME/.claude/metrics"
STATS_LOG="$METRICS_DIR/stats.jsonl"
STATS_CACHE="$HOME/.claude/stats-cache.json"

mkdir -p "$METRICS_DIR"

if [[ ! -f "$STATS_CACHE" ]]; then
    echo "No stats cache found. Run /stats in Claude Code first."
    exit 1
fi

TIMESTAMP=$(date +%s)
DATE=$(date +%Y-%m-%d)
CACHE_DATE=$(jq -r '.lastComputedDate' "$STATS_CACHE")

# Model usage
OPUS_IN=$(jq -r '.modelUsage["claude-opus-4-5-20251101"].inputTokens // 0' "$STATS_CACHE")
OPUS_OUT=$(jq -r '.modelUsage["claude-opus-4-5-20251101"].outputTokens // 0' "$STATS_CACHE")
OPUS_CACHE_READ=$(jq -r '.modelUsage["claude-opus-4-5-20251101"].cacheReadInputTokens // 0' "$STATS_CACHE")

SONNET_IN=$(jq -r '.modelUsage["claude-sonnet-4-5-20250929"].inputTokens // 0' "$STATS_CACHE")
SONNET_OUT=$(jq -r '.modelUsage["claude-sonnet-4-5-20250929"].outputTokens // 0' "$STATS_CACHE")
SONNET_CACHE_READ=$(jq -r '.modelUsage["claude-sonnet-4-5-20250929"].cacheReadInputTokens // 0' "$STATS_CACHE")

# Totals
TOTAL_SESSIONS=$(jq -r '.totalSessions // 0' "$STATS_CACHE")
TOTAL_MESSAGES=$(jq -r '.totalMessages // 0' "$STATS_CACHE")

# Today's activity (if available)
TODAY_MESSAGES=$(jq -r --arg d "$CACHE_DATE" '.dailyActivity[] | select(.date == $d) | .messageCount // 0' "$STATS_CACHE" 2>/dev/null || echo 0)
TODAY_TOOLS=$(jq -r --arg d "$CACHE_DATE" '.dailyActivity[] | select(.date == $d) | .toolCallCount // 0' "$STATS_CACHE" 2>/dev/null || echo 0)

# Build JSON record
cat >> "$STATS_LOG" << EOF
{"ts":$TIMESTAMP,"date":"$DATE","cache_date":"$CACHE_DATE","opus_in":$OPUS_IN,"opus_out":$OPUS_OUT,"opus_cache":$OPUS_CACHE_READ,"sonnet_in":$SONNET_IN,"sonnet_out":$SONNET_OUT,"sonnet_cache":$SONNET_CACHE_READ,"total_sessions":$TOTAL_SESSIONS,"total_messages":$TOTAL_MESSAGES,"today_messages":$TODAY_MESSAGES,"today_tools":$TODAY_TOOLS}
EOF

echo "Stats captured for $CACHE_DATE"
echo "  Opus:   ${OPUS_IN} in / ${OPUS_OUT} out"
echo "  Sonnet: ${SONNET_IN} in / ${SONNET_OUT} out"
echo "  Total:  ${TOTAL_SESSIONS} sessions, ${TOTAL_MESSAGES} messages"
