# ============================================================================
# Odiseo MCP Server Dockerfile
# ============================================================================
# Multi-stage build for production-ready MCP server
#
# Features:
#   - Python 3.11 slim base for minimal image size
#   - Non-root user for security (UID 1001)
#   - Multi-stage build for optimized layers
#   - Health check endpoint integration
#   - Configurable via environment variables
#
# Usage:
#   docker build -t mcp-server:latest .
#   docker run -p 8009:8009 --env-file .env mcp-server:latest
#
# Author: Odiseo Team
# Version: 1.0.0
# ============================================================================

# ============================================================================
# Base stage - Common configuration
# ============================================================================
FROM python:3.11-slim AS base

# Python optimization flags
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Create non-root user for security
RUN groupadd -r mcpserver && \
    useradd -r -g mcpserver -u 1001 mcpserver

WORKDIR /app

# ============================================================================
# Dependencies stage - Install Python packages
# ============================================================================
FROM base AS dependencies

# Install build dependencies for psycopg2
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev \
        python3-dev && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# ============================================================================
# Production stage - Final optimized image
# ============================================================================
FROM base AS production

# Install runtime dependencies for psycopg2
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libpq5 && \
    rm -rf /var/lib/apt/lists/*

# Copy installed packages from dependencies stage
COPY --from=dependencies /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=dependencies /usr/local/bin /usr/local/bin

# Copy application code with proper ownership
COPY --chown=mcpserver:mcpserver . /app/

# Create logs directory
RUN mkdir -p /app/logs && \
    chown -R mcpserver:mcpserver /app

# Set Python path for imports
ENV PYTHONPATH=/app

# Switch to non-root user
USER mcpserver

# Health check using the /health endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${MCP_PORT:-8009}/health', timeout=5)" || exit 1

# Default port (can be overridden by MCP_PORT env var)
EXPOSE ${MCP_PORT:-8009}

# Default command: run MCP server with streamable-http transport
CMD ["python", "server.py"]
