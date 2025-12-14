#!/bin/bash
# Verify OpenMemory MCP backend tools are working
# Run this BEFORE testing in Claude Code to ensure the backend is healthy

set -e

MCP_URL="${MCP_URL:-http://localhost:8080/mcp}"
HEADERS='-H "Content-Type: application/json" -H "Accept: application/json, text/event-stream"'

echo "=== OpenMemory MCP Backend Verification ==="
echo "URL: $MCP_URL"
echo ""

# Test 1: Check tools/list
echo "Test 1: Checking available tools..."
TOOLS=$(curl -s -X POST "$MCP_URL" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json, text/event-stream" \
    -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}')

if echo "$TOOLS" | grep -q "openmemory_lgm_store"; then
    echo "  ✅ openmemory_lgm_store found"
else
    echo "  ❌ openmemory_lgm_store NOT found"
    echo "  Response: $TOOLS"
    exit 1
fi

if echo "$TOOLS" | grep -q "openmemory_lgm_context"; then
    echo "  ✅ openmemory_lgm_context found"
else
    echo "  ❌ openmemory_lgm_context NOT found"
    exit 1
fi

# Test 2: Test lgm_context
echo ""
echo "Test 2: Testing openmemory_lgm_context..."
CONTEXT=$(curl -s -X POST "$MCP_URL" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json, text/event-stream" \
    -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"openmemory_lgm_context","arguments":{"namespace":"verify-test","limit":5}}}')

if echo "$CONTEXT" | grep -q 'verify-test'; then
    echo "  ✅ lgm_context returns correct namespace"
else
    echo "  ❌ lgm_context failed"
    echo "  Response: $CONTEXT"
    exit 1
fi

if echo "$CONTEXT" | grep -q 'observe'; then
    echo "  ✅ lgm_context returns node structure"
else
    echo "  ❌ lgm_context missing node structure"
    exit 1
fi

# Test 3: Test lgm_store
echo ""
echo "Test 3: Testing openmemory_lgm_store..."
STORE=$(curl -s -X POST "$MCP_URL" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json, text/event-stream" \
    -d '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"openmemory_lgm_store","arguments":{"node":"act","content":"Verification test memory - safe to delete","namespace":"verify-test","tags":["test","verification"]}}}')

if echo "$STORE" | grep -q 'node.*act'; then
    echo "  ✅ lgm_store created memory with correct node"
else
    echo "  ❌ lgm_store failed"
    echo "  Response: $STORE"
    exit 1
fi

if echo "$STORE" | grep -q 'reflection'; then
    echo "  ✅ Auto-reflection created"
else
    echo "  ⚠️  No auto-reflection (may be disabled)"
fi

# Extract memory ID for reinforce test (find first UUID pattern)
MEMORY_ID=$(echo "$STORE" | grep -oE '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}' | head -1)
echo "  Memory ID: $MEMORY_ID"

# Test 4: Verify retrieval
echo ""
echo "Test 4: Verifying context includes new memory..."
sleep 1  # Give it a moment to index
CONTEXT2=$(curl -s -X POST "$MCP_URL" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json, text/event-stream" \
    -d '{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"openmemory_lgm_context","arguments":{"namespace":"verify-test","limit":10}}}')

if echo "$CONTEXT2" | grep -q "Verification test memory"; then
    echo "  ✅ Memory appears in context"
else
    echo "  ⚠️  Memory not immediately visible in context (may need indexing time)"
fi

# Test 5: Test reinforce
echo ""
echo "Test 5: Testing openmemory_reinforce..."
if [ -n "$MEMORY_ID" ]; then
    REINFORCE=$(curl -s -X POST "$MCP_URL" \
        -H "Content-Type: application/json" \
        -H "Accept: application/json, text/event-stream" \
        -d "{\"jsonrpc\":\"2.0\",\"id\":5,\"method\":\"tools/call\",\"params\":{\"name\":\"openmemory_reinforce\",\"arguments\":{\"id\":\"$MEMORY_ID\",\"boost\":0.1}}}")

    if echo "$REINFORCE" | grep -q "Reinforced"; then
        echo "  ✅ Reinforce successful"
    else
        echo "  ❌ Reinforce failed"
        echo "  Response: $REINFORCE"
    fi
else
    echo "  ⚠️  Skipped (no memory ID)"
fi

echo ""
echo "=== Backend Verification Complete ==="
echo ""
echo "If all tests passed, the MCP backend is working correctly."
echo "Now restart Claude Code and test with the native tools."
