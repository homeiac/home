#!/bin/bash
# Add a project to OpenMemory
# Usage: ./add-project.sh

set -e

# Color output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

prompt() {
    echo -en "${CYAN}$1${NC} "
    read -r REPLY
    echo "$REPLY"
}

echo -e "${GREEN}=== Add Project to OpenMemory ===${NC}\n"

# Get project details
NAME=$(prompt "Project name:")
echo ""

echo "Categories: home, hobby, business, work"
CATEGORY=$(prompt "Category:")
echo ""

echo "Status: not_started, in_progress, blocked"
STATUS=$(prompt "Status [not_started]:")
STATUS=${STATUS:-not_started}
echo ""

echo "Priority: high, medium, low"
PRIORITY=$(prompt "Priority [medium]:")
PRIORITY=${PRIORITY:-medium}
echo ""

URL=$(prompt "URL (optional):")
ISSUE=$(prompt "GitHub Issue (optional):")
WHY=$(prompt "Why (one-liner on value):")
NEXT=$(prompt "Next action (optional):")

# Build content
CONTENT="PROJECT: $NAME
CATEGORY: $CATEGORY
STATUS: $STATUS
PRIORITY: $PRIORITY"

[[ -n "$URL" ]] && CONTENT="$CONTENT
URL: $URL"

[[ -n "$ISSUE" ]] && CONTENT="$CONTENT
ISSUE: $ISSUE"

[[ -n "$WHY" ]] && CONTENT="$CONTENT
WHY: $WHY"

[[ -n "$NEXT" ]] && CONTENT="$CONTENT
NEXT: $NEXT"

# Build tags
TAGS="project,project:$CATEGORY,status:$STATUS,priority:$PRIORITY"

echo -e "\n${YELLOW}--- Preview ---${NC}"
echo "$CONTENT"
echo -e "${YELLOW}Tags: $TAGS${NC}"
echo ""

CONFIRM=$(prompt "Add to OpenMemory? [y/N]:")
if [[ "$CONFIRM" =~ ^[Yy] ]]; then
    opm add "$CONTENT" --tags "$TAGS"

    # Reinforce high priority projects
    if [[ "$PRIORITY" == "high" ]]; then
        echo -e "${GREEN}Reinforcing high-priority project...${NC}"
        # Note: Would need memory ID to reinforce, skip for now
    fi

    echo -e "\n${GREEN}Project added!${NC}"
else
    echo "Cancelled."
fi
