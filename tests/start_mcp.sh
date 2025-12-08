#!/bin/bash

# Start script for MCP-compliant server
# This script starts the MCP server with streamable-http transport

echo "========================================"
echo "Starting MCP-Compliant Server"
echo "========================================"
echo ""
echo "Transport: Streamable HTTP (MCP Standard)"
echo "Port: 8009"
echo "Endpoint: http://localhost:8009/mcp"
echo ""
echo "This server is fully MCP-compliant and can be accessed by:"
echo "- Google agents"
echo "- Any MCP-compatible client"
echo "- Remote clients (CORS enabled)"
echo ""
echo "Starting server..."
echo "========================================"

cd "$(dirname "$0")"
python server.py --port 8009