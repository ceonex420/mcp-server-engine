#!/bin/bash

echo "========================================"
echo "Testing MCP Server Endpoints"
echo "========================================"
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Generate session ID
SESSION_ID=$(uuidgen)
echo "Session ID: $SESSION_ID"
echo ""

# Function to parse SSE response
parse_sse() {
    # Extract data lines and parse JSON
    grep "^data: " | head -1 | sed 's/^data: //'
}

# Function to parse SSE response for tools/call (gets last result)
parse_sse_result() {
    # Extract all data lines, get the last one (which should be the result)
    grep "^data: " | tail -1 | sed 's/^data: //'
}

echo "1. Testing INITIALIZE endpoint..."
echo "--------------------------------"
RESPONSE=$(curl -s -X POST http://localhost:8009/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "Mcp-Session-Id: $SESSION_ID" \
  -d '{
    "jsonrpc": "2.0",
    "method": "initialize",
    "params": {
      "clientInfo": {
        "name": "test-client",
        "version": "1.0.0"
      },
      "protocolVersion": "2025-03-26",
      "capabilities": {}
    },
    "id": 1
  }' | parse_sse)

if echo "$RESPONSE" | grep -q '"result"'; then
    echo -e "${GREEN}✓ Initialize successful${NC}"
    PROTOCOL=$(echo "$RESPONSE" | python -c "import sys, json; print(json.load(sys.stdin)['result']['protocolVersion'])" 2>/dev/null)
    echo "  Protocol: $PROTOCOL"
else
    echo -e "${RED}✗ Initialize failed${NC}"
fi

echo ""
echo "2. Testing TOOLS/LIST endpoint..."
echo "--------------------------------"
RESPONSE=$(curl -s -X POST http://localhost:8009/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "Mcp-Session-Id: $SESSION_ID" \
  -d '{
    "jsonrpc": "2.0",
    "method": "tools/list",
    "params": {},
    "id": 2
  }' | parse_sse)

if echo "$RESPONSE" | grep -q '"result"'; then
    echo -e "${GREEN}✓ Tools/List successful${NC}"
    TOOLS_COUNT=$(echo "$RESPONSE" | python -c "import sys, json; print(len(json.load(sys.stdin)['result']['tools']))" 2>/dev/null)
    echo "  Found $TOOLS_COUNT tools"
else
    echo -e "${RED}✗ Tools/List failed${NC}"
fi

echo ""
echo "3. Testing RESOURCES/LIST endpoint..."
echo "------------------------------------"
RESPONSE=$(curl -s -X POST http://localhost:8009/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "Mcp-Session-Id: $SESSION_ID" \
  -d '{
    "jsonrpc": "2.0",
    "method": "resources/list",
    "params": {},
    "id": 3
  }' | parse_sse)

if echo "$RESPONSE" | grep -q '"result"'; then
    echo -e "${GREEN}✓ Resources/List successful${NC}"
    RESOURCES_COUNT=$(echo "$RESPONSE" | python -c "import sys, json; print(len(json.load(sys.stdin)['result']['resources']))" 2>/dev/null)
    echo "  Found $RESOURCES_COUNT resources"
else
    echo -e "${RED}✗ Resources/List failed${NC}"
fi

echo ""
echo "4. Testing TOOLS/CALL endpoint..."
echo "--------------------------------"
RESPONSE=$(curl -s -X POST http://localhost:8009/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "Mcp-Session-Id: $SESSION_ID" \
  -d '{
    "jsonrpc": "2.0",
    "method": "tools/call",
    "params": {
      "name": "fetch_by_sku",
      "arguments": {
        "sku": "LAPTOP-001"
      }
    },
    "id": 4
  }' | parse_sse_result)

# Tools/call may return multiple messages (progress, result)
if echo "$RESPONSE" | grep -q '"result"'; then
    echo -e "${GREEN}✓ Tools/Call successful${NC}"
    echo "  Tool executed: fetch_by_sku"
else
    echo -e "${RED}✗ Tools/Call failed${NC}"
fi

echo ""
echo "========================================"
echo "Test completed!"
echo "========================================"