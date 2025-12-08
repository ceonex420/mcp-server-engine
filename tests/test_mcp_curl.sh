#!/bin/bash

echo "Testing MCP Server with curl"
echo "============================="

# Generate session ID
SESSION_ID=$(uuidgen)
echo "Session ID: $SESSION_ID"

# Test 1: Initialize session
echo -e "\n1. Initialize MCP session:"
curl -X POST http://localhost:8009/mcp \
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
  }' 2>/dev/null | sed 's/^data: //' | python -m json.tool

echo -e "\n2. List available tools:"
curl -X POST http://localhost:8009/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "Mcp-Session-Id: $SESSION_ID" \
  -d '{
    "jsonrpc": "2.0",
    "method": "tools/list",
    "params": {},
    "id": 2
  }' 2>/dev/null | sed 's/^data: //' | python -m json.tool

echo -e "\n3. Call fuzzy_search_smart tool:"
curl -X POST http://localhost:8009/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "Mcp-Session-Id: $SESSION_ID" \
  -d '{
    "jsonrpc": "2.0",
    "method": "tools/call",
    "params": {
      "name": "fuzzy_search_smart",
      "arguments": {
        "query": "cargador",
        "limit": 3
      }
    },
    "id": 3
  }' 2>/dev/null | sed 's/^data: //' | python -m json.tool