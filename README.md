# Odiseo MCP Server - AI-Powered Product Search, Booking & User Management

![Python Version](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![MCP Protocol](https://img.shields.io/badge/MCP-1.21.0-purple)
![Code Style](https://img.shields.io/badge/code%20style-ruff-black)
[![Pydantic v2](https://img.shields.io/badge/pydantic-v2-E92063.svg)](https://docs.pydantic.dev/)
![Status](https://img.shields.io/badge/status-production--ready-brightgreen)
![Tools](https://img.shields.io/badge/MCP%20Tools-12-orange)

Production-ready Model Context Protocol (MCP) server implementing Anthropic's official specification. Features **12 MCP tools** across two domains: AI-powered product search (semantic + fuzzy) and booking/appointment management with Google Calendar integration. Built with PostgreSQL + pgvector, asyncpg for async database operations, and Google Gemini embeddings. Includes concurrency control and rate limiting for production workloads.

## Description

This MCP server provides a comprehensive AI assistant backend with two integrated domains:

### Product Search (4 tools)
- **Semantic Search**: AI-powered conceptual search using 1536-dimensional Gemini embeddings (~490ms)
- **Fuzzy Search**: Typo-tolerant with accent-insensitive matching via pg_trgm (~11ms)
- **Exact Retrieval**: Fast SKU/ID lookups (~9ms response time)
- **Multi-tier Fallback**: 4-tier cascade strategy for optimal results

### Booking & Appointments (8 tools)
- **Google Calendar Integration**: Create, reschedule, cancel appointments with automatic calendar sync
- **Availability Management**: Real-time slot availability based on business hours
- **Customer Bookings**: Track and manage customer appointment history
- **Service Catalog**: Dynamic service types with pricing and duration

### Production Features
- **Concurrency Control**: Semaphore-based limiting (default: 50 concurrent requests)
- **Rate Limiting**: Per-session request throttling (30/min search, 20/min booking)
- **Async Database**: Full asyncpg integration for non-blocking operations
- **Docker Ready**: Named volumes, log rotation, configurable healthchecks

Built with modern Python 3.10+, async/await patterns, and comprehensive type safety.

## Table of Contents

- [Features](#features)
- [Visuals](#visuals)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [API Reference](#api-reference)
- [Architecture](#architecture)
- [Testing](#testing)
- [Deployment](#deployment)
- [Troubleshooting](#troubleshooting)
- [Roadmap](#roadmap)
- [Support](#support)
- [Contributing](#contributing)
- [Authors and Acknowledgment](#authors-and-acknowledgment)
- [License](#license)
- [Project Status](#project-status)

## Features

### Core Capabilities

- ✅ **100% MCP Compliant**: Implements Anthropic's official MCP specification (v1.21.0)
- ✅ **12 MCP Tools**: Product search (4), Booking (8)
- ✅ **5 MCP Resources**: Dynamic tool discovery and database statistics
- ✅ **2 MCP Prompts**: AI assistant templates for search and comparison
- ✅ **Google Calendar Integration**: Automatic appointment sync
- ✅ **Concurrency Control**: Semaphore-based request limiting (50 concurrent)
- ✅ **Rate Limiting**: Per-session throttling for search and booking operations
- ✅ **Async Database**: Full asyncpg integration (non-blocking I/O)
- ✅ **Type Safe**: Full Python 3.10+ type hints throughout
- ✅ **Production Ready**: Named Docker volumes, log rotation, health checks

### Performance Benchmarks

| Operation | Response Time | Description |
|-----------|---------------|-------------|
| SKU Fetch | ~9ms | Exact product retrieval by SKU code |
| Fuzzy Search | ~11ms | Typo-tolerant text search |
| Semantic Search | ~490ms | AI embedding-based conceptual search |
| Create Booking | ~150-300ms | With Google Calendar sync |
| Get Available Slots | ~50-100ms | Real-time availability check |
| Health Check | <50ms | Database connectivity and extension checks |

## Visuals

### Architecture Diagram

```mermaid
graph TB
    subgraph clients["🤖 AI Clients"]
        client1["Claude Desktop"]
        client2["ChatGPT"]
        client3["Custom AI Agents"]
    end

    subgraph mcp_server["🚀 MCP Server (FastMCP)"]
        direction TB

        subgraph handlers["📡 MCP Protocol Handlers"]
            tool_h["Tool Handlers<br/>fetch, search, fuzzy"]
            resource_h["Resource Handlers<br/>product://, database://"]
            prompt_h["Prompt Handlers<br/>AI Templates"]
        end

        subgraph business["⚙️ Business Logic (tools/)"]
            fetch["fetch.py<br/>SKU/ID Retrieval"]
            search["search.py<br/>Semantic Search"]
            fuzzy["fuzzy_search.py<br/>Fuzzy Matching"]
        end

        subgraph utils["🔧 Utilities"]
            db["db.py<br/>PostgreSQL Operations"]
            embeddings["embeddings.py<br/>Gemini Client"]
            logger["logger.py<br/>Structured Logging"]
            config["settings.py<br/>Pydantic v2 Config"]
        end

        handlers --> business
        business --> utils
    end

    subgraph external["🗄️ External Services"]
        postgres["PostgreSQL 15+<br/>+ pgvector<br/>+ pg_trgm<br/>+ unaccent"]
        gemini["Google Gemini API<br/>gemini-embedding-001<br/>1536-dim vectors"]
    end

    clients -->|"MCP Protocol<br/>(HTTP/STDIO)"| handlers
    utils --> postgres
    utils --> gemini

    style clients fill:#e1f5ff,stroke:#01579b,stroke-width:2px
    style mcp_server fill:#f3e5f5,stroke:#4a148c,stroke-width:3px
    style handlers fill:#fff3e0,stroke:#e65100,stroke-width:2px
    style business fill:#e8f5e9,stroke:#1b5e20,stroke-width:2px
    style utils fill:#fce4ec,stroke:#880e4f,stroke-width:2px
    style external fill:#fff9c4,stroke:#f57f17,stroke-width:2px
```

### Search Strategy Flow

```mermaid
flowchart TD
    Start([👤 User Query]) --> SKU{Exact SKU<br/>Match?}

    SKU -->|"✅ Match<br/>(~9ms)"| FoundSKU[/"🎯 Product Found<br/>Return Details"/]
    SKU -->|"❌ No Match"| Fuzzy{Fuzzy Text<br/>Search?<br/>pg_trgm}

    Fuzzy -->|"✅ Results<br/>(~11ms)"| FoundFuzzy[/"📝 Products Found<br/>Return Matches"/]
    Fuzzy -->|"❌ No Results"| Semantic{Semantic<br/>Search?<br/>Embeddings}

    Semantic -->|"✅ Results<br/>(~490ms)"| FoundSemantic[/"🧠 Products Found<br/>Return by Relevance"/]
    Semantic -->|"❌ No Results"| Empty[/"❌ No Results<br/>Return Empty Array"/]

    FoundSKU --> End([✨ Return to Client])
    FoundFuzzy --> End
    FoundSemantic --> End
    Empty --> End

    style Start fill:#e3f2fd,stroke:#1976d2,stroke-width:3px
    style SKU fill:#fff3e0,stroke:#f57c00,stroke-width:2px
    style Fuzzy fill:#f3e5f5,stroke:#7b1fa2,stroke-width:2px
    style Semantic fill:#e8f5e9,stroke:#388e3c,stroke-width:2px
    style FoundSKU fill:#c8e6c9,stroke:#2e7d32,stroke-width:2px
    style FoundFuzzy fill:#c8e6c9,stroke:#2e7d32,stroke-width:2px
    style FoundSemantic fill:#c8e6c9,stroke:#2e7d32,stroke-width:2px
    style Empty fill:#ffcdd2,stroke:#c62828,stroke-width:2px
    style End fill:#e1f5fe,stroke:#0277bd,stroke-width:3px
```

### Configuration Management Flow (Pydantic v2)

```mermaid
flowchart LR
    subgraph input["📥 Configuration Sources"]
        env_file[".env File"]
        env_vars["Environment<br/>Variables"]
        defaults["Default<br/>Values"]
    end

    subgraph pydantic["🔧 Pydantic v2 Processing"]
        direction TB
        load["BaseSettings<br/>Auto-Load"]
        validate["Field Validators<br/>Type Checking"]
        compute["Computed<br/>Properties"]
    end

    subgraph output["✅ Validated Configuration"]
        settings["settings<br/>Singleton Instance"]

        subgraph groups["Configuration Groups"]
            db_cfg["Database Config<br/>URL, Schema"]
            ai_cfg["AI Config<br/>API Key, Model"]
            log_cfg["Logging Config<br/>Level, Size, Dir"]
        end
    end

    subgraph app["🚀 Application"]
        server["server.py"]
        tools["tools/"]
        utils["utils/"]
    end

    env_file --> load
    env_vars --> load
    defaults --> load

    load --> validate
    validate -->|"❌ Error"| error["ValidationError<br/>❌ Startup Failed"]
    validate -->|"✅ Valid"| compute
    compute --> settings

    settings --> groups
    groups --> app

    style input fill:#fff3e0,stroke:#e65100,stroke-width:2px
    style pydantic fill:#e8f5e9,stroke:#2e7d32,stroke-width:3px
    style output fill:#e3f2fd,stroke:#1565c0,stroke-width:2px
    style groups fill:#f3e5f5,stroke:#6a1b9a,stroke-width:2px
    style app fill:#fff9c4,stroke:#f9a825,stroke-width:2px
    style error fill:#ffcdd2,stroke:#c62828,stroke-width:2px
```

## Prerequisites

### System Requirements

- **Python**: 3.10 or higher (with type hints support)
- **PostgreSQL**: 14 or higher (15+ recommended)
- **Memory**: Minimum 2GB RAM
- **Disk**: 500MB for application + database storage
- **OS**: Linux, macOS, or Windows (WSL recommended on Windows)

### PostgreSQL Extensions

Required extensions (must be enabled in your database):

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;     -- Trigram fuzzy search
CREATE EXTENSION IF NOT EXISTS unaccent;    -- Accent normalization
CREATE EXTENSION IF NOT EXISTS vector;      -- pgvector for embeddings
```

### External Services

- **Google Gemini API**: Required for semantic search
  - Sign up at: [Google AI Studio](https://makersuite.google.com/app/apikey)
  - Free tier available with rate limits

## Installation

### Quick Start (5 minutes)

```bash
# 1. Clone repository
git clone <repository-url>
cd Lab01-MCP/mcp_server

# 2. Create virtual environment
python3.10 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
nano .env  # Edit with your credentials

# 5. Start server
python server.py

# 6. Verify installation
curl http://localhost:8009/health
```

### Detailed Installation Steps

#### 1. Create Virtual Environment

```bash
# Create isolated Python environment
python3.10 -m venv venv

# Activate virtual environment
# On Linux/macOS:
source venv/bin/activate

# On Windows (Command Prompt):
venv\Scripts\activate

# On Windows (PowerShell):
venv\Scripts\Activate.ps1
```

#### 2. Install Dependencies

**Option A: Using pip (Recommended)**
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

**Option B: Using pyproject.toml**
```bash
# Production only
pip install -e .

# With development tools (ruff, pytest, mypy)
pip install -e .[dev]
```

#### 3. Database Setup

**Using Docker (Recommended)**
```bash
# From project root
cd ../DockerConfig
./start.sh

# Or manually:
docker-compose up -d
```

**Manual PostgreSQL Setup**
```bash
# Create database
createdb mcpdb

# Create user
psql -c "CREATE USER mcp_user WITH PASSWORD 'mcp_password';"
psql -c "GRANT ALL PRIVILEGES ON DATABASE mcpdb TO mcp_user;"

# Enable extensions
psql mcpdb -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;"
psql mcpdb -c "CREATE EXTENSION IF NOT EXISTS unaccent;"
psql mcpdb -c "CREATE EXTENSION IF NOT EXISTS vector;"

# Initialize schema (from SQL directory)
cd ../SQL
python3 src/init-db.py
python3 src/populate-db.py
```

#### 4. Environment Configuration

```bash
# Copy template
cp .env.example .env

# Edit configuration
nano .env  # or use your preferred editor
```

**Minimum required configuration:**
```bash
DATABASE_URL="postgresql://mcp_user:mcp_password@localhost:5434/mcpdb"
GOOGLE_API_KEY="your-google-api-key-here"
SCHEMA_NAME="test"
```

#### 5. Verify Installation

```bash
# Start server
python server.py

# In another terminal, test health endpoint
curl http://localhost:8009/health

# Expected response:
# {
#   "status": "healthy",
#   "checks": {
#     "database": {
#       "status": "healthy",
#       "product_count": 90,
#       "extensions": ["pg_trgm", "unaccent", "vector"]
#     }
#   }
# }
```

## Configuration

### Environment Variables

Complete configuration reference:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| **Database** ||||
| `DATABASE_URL` | ✅ Yes | - | PostgreSQL connection URL |
| `SCHEMA_NAME` | No | `test` | Database schema name |
| **AI/ML** ||||
| `GOOGLE_API_KEY` | ✅ Yes | - | Google Gemini API key |
| `EMBEDDING_MODEL` | No | `gemini-embedding-001` | Embedding model name |
| `BATCH_SIZE` | No | `8` | Batch size for embeddings |
| **Server** ||||
| `DEBUG_MODE` | No | `false` | Enable debug mode (set `false` in production) |
| `MCP_PORT` | No | `8009` | HTTP port for MCP server |
| `MAX_CONCURRENT_REQUESTS` | No | `50` | Maximum concurrent requests per worker |
| **Email Service** ||||
| `EMAIL_SERVICE_ENABLED` | No | `true` | Enable HTTP email service integration |
| `EMAIL_SERVICE_BASE_URL` | No | `http://localhost:8001` | Email service base URL |
| `EMAIL_SERVICE_API_KEY` | No | - | API key for email service (optional) |
| `EMAIL_SERVICE_TIMEOUT_SECONDS` | No | `5.0` | HTTP request timeout |
| `EMAIL_SERVICE_MAX_RETRIES` | No | `2` | Max retry attempts |
| `EMAIL_SERVICE_CIRCUIT_BREAKER_THRESHOLD` | No | `5` | Failures before circuit opens |
| **Logging** ||||
| `LOG_LEVEL` | No | `INFO` | Logging level |
| `LOG_MAX_SIZE_MB` | No | `10` | Max log file size (MB) |
| `LOG_BACKUP_COUNT` | No | `5` | Number of log backups |
| `LOG_DIR` | No | `logs` | Log directory path |
| **Performance** ||||
| `PGVECTOR_IVF_LISTS` | No | `100` | pgvector IVF lists count |

### Configuration Examples

#### Development Environment
```bash
DATABASE_URL="postgresql://mcp_user:mcp_password@localhost:5434/mcpdb"
GOOGLE_API_KEY="AIzaSyBu1JHchLA4TAhp..."
SCHEMA_NAME="test"
LOG_LEVEL="DEBUG"
```

#### Production Environment
```bash
DATABASE_URL="postgresql://mcp_user:STRONG_PASSWORD@db.example.com:5432/mcpdb"
GOOGLE_API_KEY="AIzaSyBu1JHchLA4TAhp..."
SCHEMA_NAME="production"
LOG_LEVEL="WARNING"
LOG_MAX_SIZE_MB="50"
LOG_BACKUP_COUNT="10"
```

### Logging Configuration

The server uses structured logging with automatic rotation:

**Log Files** (created in `logs/` directory):
- `mcp_server.log` - Main server operations
- `mcp_db.log` - Database queries and operations
- `mcp_embeddings.log` - Google Gemini API calls
- `mcp_tools_search.log` - Semantic search operations
- `mcp_tools_fuzzy_search.log` - Fuzzy search operations
- `mcp_tools_fetch.log` - Product fetch operations

**Log Format**:
```
2025-10-10 12:30:45,123 [INFO] mcp_server:45 - Server started successfully
2025-10-10 12:30:46,234 [DEBUG] mcp_db:78 - Executing query: SELECT * FROM test.products
```

### Configuration Management with Pydantic v2

The project uses **Pydantic v2** (`pydantic>=2.11.0`) with **pydantic-settings** for type-safe configuration management. This provides automatic validation, environment variable parsing, and comprehensive type safety.

#### Why Pydantic v2?

- ✅ **Automatic Type Validation**: Ensures all environment variables are correctly typed
- ✅ **Runtime Error Prevention**: Catches configuration errors at startup, not during operation
- ✅ **IDE Autocomplete**: Full type hints enable IDE support and autocomplete
- ✅ **Custom Validators**: Business logic validation (e.g., URL format, log levels)
- ✅ **Computed Properties**: Dynamic values derived from configuration
- ✅ **Zero Boilerplate**: Automatic `.env` file loading and parsing

#### Accessing Configuration in Code

All configuration is available through the singleton `settings` instance:

```python
from config import settings

# Access configuration values
db_url = settings.DATABASE_URL
api_key = settings.GOOGLE_API_KEY
log_level = settings.LOG_LEVEL

# Use computed properties
log_path = settings.log_dir_path  # Absolute Path object
log_bytes = settings.log_max_bytes  # Converted from MB to bytes
products_file = settings.products_path  # Resolved relative path

# Get grouped configurations
db_config = settings.get_database_config()
# Returns: {"database_url": "...", "schema_name": "test"}

embedding_config = settings.get_embedding_config()
# Returns: {"api_key": "...", "model": "gemini-embedding-001"}

logging_config = settings.get_logging_config()
# Returns: {"level": "INFO", "max_size_mb": 10, ...}
```

#### Field Validations

The following validations are automatically applied on startup:

| Field | Validation | Error Message |
|-------|------------|---------------|
| `DATABASE_URL` | Must start with `postgresql://` | "DATABASE_URL must start with 'postgresql://'" |
| `DATABASE_URL` | Cannot be empty | "DATABASE_URL cannot be empty" |
| `GOOGLE_API_KEY` | Cannot be empty or whitespace | "GOOGLE_API_KEY cannot be empty" |
| `LOG_LEVEL` | Must be valid log level | "LOG_LEVEL must be one of {DEBUG, INFO, WARNING, ERROR, CRITICAL}" |
| `BATCH_SIZE` | Must be > 0 | Pydantic validation error |
| `LOG_MAX_SIZE_MB` | Must be > 0 | Pydantic validation error |
| `LOG_BACKUP_COUNT` | Must be > 0 | Pydantic validation error |
| `PGVECTOR_IVF_LISTS` | Must be > 0 | Pydantic validation error |

**Example validation error at startup:**

```bash
$ export LOG_LEVEL=INVALID
$ python server.py

ValidationError: 1 validation error for Settings
LOG_LEVEL
  Value error, LOG_LEVEL must be one of {'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'}, got: INVALID
```

#### Computed Properties

These properties are dynamically calculated from base configuration values:

| Property | Type | Description | Example |
|----------|------|-------------|---------|
| `log_max_bytes` | `int` | Log size in bytes (from MB) | `10485760` (10MB) |
| `log_dir_path` | `Path` | Absolute path to logs directory | `/opt/mcp_server/logs` |
| `products_path` | `Path` | Absolute path to products JSON | `/opt/mcp_server/data/products.json` |

**Usage:**

```python
from config import settings

# Get absolute log directory path
log_dir = settings.log_dir_path
log_dir.mkdir(parents=True, exist_ok=True)

# Get log size in bytes (automatically converted)
max_bytes = settings.log_max_bytes  # 10 * 1024 * 1024 = 10485760
```

#### Extending Configuration

To add new configuration variables:

1. **Add to `config/settings.py`:**

```python
from pydantic import Field

class Settings(BaseSettings):
    # ... existing fields ...

    # Add new field with validation
    NEW_FEATURE_ENABLED: bool = Field(
        default=False,
        description="Enable new experimental feature"
    )

    MAX_RETRY_ATTEMPTS: int = Field(
        default=3,
        gt=0,  # Must be greater than 0
        le=10,  # Must be less than or equal to 10
        description="Maximum retry attempts for failed operations"
    )

    # Add custom validator
    @field_validator("MAX_RETRY_ATTEMPTS")
    @classmethod
    def validate_retry_attempts(cls, v: int) -> int:
        if v > 10:
            raise ValueError("MAX_RETRY_ATTEMPTS should not exceed 10 for performance")
        return v
```

2. **Add to `.env` file:**

```bash
NEW_FEATURE_ENABLED=true
MAX_RETRY_ATTEMPTS=5
```

3. **Use in code:**

```python
from config import settings

if settings.NEW_FEATURE_ENABLED:
    # Use new feature
    for attempt in range(settings.MAX_RETRY_ATTEMPTS):
        # Retry logic
        pass
```

#### Pydantic v2 Migration Notes

This project uses **modern Pydantic v2 patterns** (2025 best practices):

✅ **Correct (v2):**
- `model_config = SettingsConfigDict(...)` - Configuration via dict
- `@field_validator("field_name")` - Field validation decorator
- `Field(..., gt=0)` - Constraints as Field parameters
- `from pydantic_settings import BaseSettings` - Settings from separate package

❌ **Deprecated (v1 - NOT used):**
- `class Config:` - Old configuration style
- `@validator("field_name")` - Old validator decorator
- `conint(gt=0)` - Constrained types (replaced by Field)
- `from pydantic import BaseSettings` - Settings moved to pydantic-settings

**Reference:** See `config/settings.py` (217 lines) for complete implementation.

## Usage

### Smallest Example

```bash
# 1. Start the server
python server.py

# 2. Query health endpoint
curl http://localhost:8009/health

# 3. Use MCP tools (via AI client or SDK)
# The server exposes tools like:
# - fetch_by_sku(sku="LAPTOP-001")
# - search_products(query="gaming laptop", k=5)
# - fuzzy_search_smart(query="laptop para gamear", limit=10)
```

### Starting the Server

**HTTP Mode (Production - Recommended)**
```bash
# Default: runs on http://0.0.0.0:8009
python server.py

# Custom host and port
python server.py --host 127.0.0.1 --port 8000

# Server endpoints:
# - MCP: http://localhost:8009/mcp
# - Health: http://localhost:8009/health
```

**STDIO Mode (Local CLI)**
```bash
# For direct integration with local CLI tools
python server.py --stdio
```

### Using Helper Scripts

```bash
# Start server with monitoring
./test/start_mcp.sh

# Monitor all logs in real-time
tail -f logs/*.log

# Test MCP endpoints
./test/test_mcp_endpoints.sh
```

### Example Queries

#### 1. Fetch Product by SKU
```python
# Fastest method: ~9ms response time
{
  "tool": "fetch_by_sku",
  "arguments": {
    "sku": "COMP-001"
  }
}
```

#### 2. Semantic Search
```python
# AI-powered conceptual search
{
  "tool": "search_products",
  "arguments": {
    "query": "algo para limpiar automáticamente",
    "k": 5
  }
}

# Finds: vacuum cleaners, robot cleaners, etc.
```

#### 3. Fuzzy Search with Typos
```python
# Typo-tolerant search
{
  "tool": "fuzzy_search_smart",
  "arguments": {
    "query": "auricuares inalabricos",  # typos: auriculares inalámbricos
    "limit": 20
  }
}

# Finds: wireless headphones despite typos
```

### Health Check Monitoring

```bash
# Basic health check
curl http://localhost:8009/health

# Health check with details
curl http://localhost:8009/health | jq

# Expected healthy response:
{
  "status": "healthy",
  "timestamp": 1234567890.123,
  "checks": {
    "database": {
      "status": "healthy",
      "response_time_ms": 8.5,
      "product_count": 90,
      "schema": "test",
      "extensions": ["pg_trgm", "unaccent", "vector"],
      "normalize_text_available": true
    }
  }
}
```

## API Reference

### MCP Tools (12 total)

#### Product Tools (4)

| Tool | Response | Description |
|------|----------|-------------|
| `fetch_by_sku` | ~9ms | Retrieve product by exact SKU code |
| `fetch_by_id` | ~9ms | Retrieve product by database ID |
| `search_products` | ~490ms | AI-powered semantic search using Gemini embeddings |
| `fuzzy_search_smart` | ~11ms | Typo-tolerant search with 4-tier fallback |

**Concurrency & Rate Limiting:**
- `search_products`: Concurrency controlled + 30 req/min rate limit
- `fuzzy_search_smart`: Concurrency controlled + 30 req/min rate limit

#### Booking Tools (8)

| Tool | Response | Description |
|------|----------|-------------|
| `create_booking` | ~150-300ms | Create appointment with Google Calendar sync |
| `cancel_booking` | ~100-200ms | Cancel existing booking |
| `reschedule_booking` | ~150-300ms | Reschedule to new date/time |
| `get_available_slots` | ~50-100ms | Get available time slots for a date |
| `get_booking_by_id` | ~20-30ms | Get booking details by ID |
| `list_customer_bookings` | ~30-50ms | List all bookings for a customer email |
| `get_services` | ~20-30ms | Get available service types |
| `get_business_hours` | ~20-30ms | Get business operating hours |

**Concurrency & Rate Limiting:**
- `create_booking`, `cancel_booking`, `reschedule_booking`: Concurrency controlled + 20 req/min rate limit
- Read operations (`get_*`, `list_*`): No limiting (fast, read-only)

### MCP Resources (5)

| URI Pattern | Description |
|-------------|-------------|
| `product://sku/{sku}` | Access product data by SKU |
| `database://stats` | Database statistics and health |
| `tool-categories://products` | List of product tool names |
| `tool-categories://bookings` | List of booking tool names |
| `tool-categories://pageable-tools` | List of pageable tools |

### MCP Prompts (2)

| Prompt | Description |
|--------|-------------|
| `search_assistant_prompt` | AI template for product search assistance |
| `product_comparison_prompt` | AI template for comparing products |

## Architecture

### Tech Stack

**Core Technologies:**
- Python 3.10+ (modern type hints, pattern matching)
- PostgreSQL 14+ (with advanced extensions)
- FastMCP 1.2.0+ (Anthropic's official MCP SDK)

**AI & Machine Learning:**
- Google Gemini AI (gemini-embedding-001 model)
- pgvector (PostgreSQL extension for vector operations)

**Database Extensions:**
- pg_trgm (trigram similarity for fuzzy matching)
- unaccent (Unicode normalization)

**Web Framework:**
- Uvicorn (ASGI server)
- Starlette (via FastMCP)

**Configuration & Validation:**
- Pydantic v2 (data validation)
- python-dotenv (environment management)

**Development Tools:**
- Ruff (linting and formatting)
- pytest (testing framework)
- httpx (async HTTP client)

### Project Structure

```
mcp_server/
├── server.py                    # Main entry point - FastMCP server
├── Dockerfile                   # Multi-stage Docker build (Python 3.11)
├── docker-compose.yml           # Production deployment configuration
├── config/
│   ├── __init__.py
│   ├── settings.py              # Pydantic v2 settings
│   └── booking_constants.py     # Booking enums and constants
├── mcp_handlers/                # MCP protocol handlers (12 tools)
│   ├── __init__.py
│   ├── sales_handlers.py        # Product tools (4) with concurrency control
│   ├── booking_handlers.py      # Booking tools (8) with rate limiting
│   ├── resource_handlers.py     # MCP Resources (5)
│   └── prompt_handlers.py       # MCP Prompts (2)
├── tools/                       # Business logic (modular packages)
│   ├── __init__.py
│   ├── bookings/                # Booking module (7 files)
│   │   ├── __init__.py          # Public API exports
│   │   ├── core.py              # CRUD: create, cancel, reschedule
│   │   ├── availability.py      # Slot availability checking
│   │   ├── queries.py           # Read operations
│   │   ├── helpers.py           # Atomic transactions (row-level locking)
│   │   ├── calendar.py          # Google Calendar integration
│   │   └── email.py             # Fire-and-forget notifications
│   └── sales/                   # Sales module (4 files)
│       ├── __init__.py          # Public API exports
│       ├── fetch.py             # SKU/ID lookup (sync + async)
│       ├── search.py            # Semantic vector search (sync + async)
│       └── fuzzy_search.py      # Typo-tolerant text search
├── utils/                       # Utilities (11 modules)
│   ├── __init__.py
│   ├── db_async.py              # Async PostgreSQL with asyncpg
│   ├── concurrency.py           # Semaphore-based concurrency control
│   ├── rate_limiter.py          # Per-session rate limiting
│   ├── embeddings.py            # Google Gemini embeddings + LRU cache
│   ├── email_client.py          # HTTP email service (circuit breaker)
│   ├── google_calendar.py       # Google Calendar integration
│   ├── logger.py                # Structured logging with rotation + banner
│   ├── tool_registry.py         # Dynamic tool discovery
│   └── validation.py            # RFC 5321/5322 email validation
├── tests/                       # Test suite
│   ├── test_official_mcp_fixed.py
│   └── *.sh                     # Shell test scripts
├── logs/                        # Application logs (Docker: named volume)
├── .env                         # Environment configuration
├── .env.example                 # Environment template
├── requirements.txt             # Dependencies (asyncpg, fastmcp, etc.)
└── README.md                    # This file
```

### Design Principles

1. **Separation of Concerns**: MCP handlers separated from business logic
2. **Clean Architecture**: Clear dependencies flowing inward
3. **Type Safety**: Full type annotations throughout
4. **Async First**: Complete async/await pattern
5. **Configuration as Code**: Pydantic v2 models with validation
6. **Testability**: Pure functions with minimal side effects

## Code Review & Security Analysis

### Enterprise MCP Best Practices Implemented

This server follows Anthropic's official MCP Python SDK specification (v1.21.0) with enterprise-grade patterns:

| Practice | Status | Implementation |
|----------|--------|----------------|
| **Official FastMCP SDK** | ✅ | Uses `mcp.server.fastmcp.FastMCP` |
| **Stateless HTTP Mode** | ✅ | `stateless_http=True` for remote clients |
| **Protocol Version** | ✅ | Supports `2024-11-05` (latest) |
| **Parameterized SQL** | ✅ | All queries use `%s` placeholders |
| **Schema Validation** | ✅ | `validate_schema_name()` prevents SQL injection |
| **Connection Pooling** | ✅ | `psycopg2.pool.SimpleConnectionPool` |
| **Retry Logic** | ✅ | Automatic reconnection with exponential backoff |
| **Atomic Transactions** | ✅ | Row-level locking (`SELECT ... FOR UPDATE`) |
| **Fire-and-Forget Emails** | ✅ | Never block booking operations |
| **OTP Rate Limiting** | ✅ | 1 request/minute, max 3 attempts |
| **Session Timeout** | ✅ | 30-minute idle timeout |
| **RFC 5321/5322 Validation** | ✅ | Email validation with typo detection |
| **Health Endpoint** | ✅ | `/health` with DB/extension checks |
| **Structured Logging** | ✅ | Rotating logs with size limits |
| **Type Safety** | ✅ | 100% type annotations coverage |

### Security Review Summary

**Last Review Date:** December 2025
**Review Status:** ✅ Production Ready

#### Security Controls Verified

| Control | Status | Details |
|---------|--------|---------|
| SQL Injection Prevention | ✅ Pass | Parameterized queries + schema validation |
| Command Injection | ✅ Pass | No shell commands with user input |
| XSS Prevention | ✅ Pass | JSON API responses only |
| Authentication | ✅ Pass | OTP with SHA-256 hashing |
| Session Management | ✅ Pass | Server-side sessions with timeout |
| Rate Limiting | ✅ Pass | OTP request throttling |
| Secrets Management | ✅ Pass | Environment variables only |
| Non-root Container | ✅ Pass | Dockerfile uses UID 1001 |

#### Recommendations for Production

| Priority | Recommendation | Status |
|----------|----------------|--------|
| Medium | Make `debug=True` configurable via env var | ✅ Fixed (DEBUG_MODE) |
| Low | Mask email addresses in production logs | Optional |
| Low | Use `zoneinfo` consistently (remove TIMEZONE_OFFSETS) | ✅ Fixed |

### Modular Architecture (Dec 2025 Refactor)

Large monolithic files were refactored into modular packages for maintainability:

**Before:**
- `tools/bookings.py` (1552 lines) → Single file with all booking logic
- `tools/sales.py` → Single file with search/fetch logic

**After:**
- `tools/bookings/` (7 files) → Modular package with clear separation:
  - `core.py`: CRUD operations (create, cancel, reschedule)
  - `availability.py`: Slot availability checking
  - `queries.py`: Read-only database operations
  - `helpers.py`: Atomic transactions with row-level locking
  - `calendar.py`: Google Calendar integration
  - `email.py`: Fire-and-forget email notifications

- `tools/sales/` (4 files) → Modular package:
  - `fetch.py`: SKU/ID direct lookup (sync + async)
  - `search.py`: Semantic vector search (sync + async)
  - `fuzzy_search.py`: Typo-tolerant text matching

**Benefits:**
- ✅ Single Responsibility: Each file has one purpose
- ✅ Easier Testing: Smaller units to test
- ✅ Better IDE Support: Faster navigation and autocomplete
- ✅ Backward Compatible: `__init__.py` re-exports maintain API

## Email Service Integration

### Architecture Decision: Fire-and-Forget HTTP

After evaluating two integration patterns for email notifications:

| Pattern | Description | Use Case |
|---------|-------------|----------|
| **Sync Request-Response** | Wait for email service response | Critical emails requiring confirmation |
| **Async Fire-and-Forget** | Send request, don't wait | Non-blocking notifications |

**Chosen Pattern: Async Fire-and-Forget with Circuit Breaker**

This pattern was selected because:
1. **Booking operations should never fail due to email service issues**
2. **Email service already has its own queue and retry logic** (returns 202 Accepted)
3. **Users expect email within minutes, not milliseconds**
4. **Better UX** - booking completes immediately

### Design Patterns Implemented

| Pattern | Purpose | Implementation |
|---------|---------|----------------|
| **Circuit Breaker** | Prevents cascading failures | Opens after 5 failures, retries after 60s |
| **Retry with Backoff** | Handles transient errors | Exponential backoff (0.5s × 2^n) |
| **Fire-and-Forget** | Non-blocking operations | asyncio.create_task with error logging |
| **Singleton** | Single client instance | get_email_client() factory |

### Email Service API Integration

```
┌─────────────────┐     HTTP POST /emails     ┌─────────────────┐
│                 │ ─────────────────────────▶│                 │
│   MCP Server    │      (fire-and-forget)    │  Email Service  │
│   Port: 8009    │                           │   Port: 8001    │
│                 │ ◀─────────────────────────│                 │
└─────────────────┘     202 Accepted (async)  └─────────────────┘
        │                                              │
        │ Booking completes                    Email queued
        │ immediately                          for delivery
        ▼                                              ▼
   User sees                                  Background worker
   confirmation                               sends via SMTP
```

### HTTP Client Features

```python
# utils/email_client.py provides:
from utils.email_client import get_email_client, send_booking_email

# Full async client with circuit breaker
client = get_email_client()
response = await client.send_email(
    to=["user@example.com"],
    subject="Booking Confirmation",
    body="<h1>Confirmed!</h1>",
    template_id="booking_created",
    template_vars={"customer_name": "John"}
)

# Convenience fire-and-forget function
await send_booking_email(
    customer_email="user@example.com",
    customer_name="John",
    booking_id=123,
    service_type="Consultation",
    booking_date="2025-12-15",
    booking_time="10:00",
    template_id="booking_created"
)
```

### Configuration

```bash
# Enable email service integration
EMAIL_SERVICE_ENABLED=true
EMAIL_SERVICE_BASE_URL=http://localhost:8001
EMAIL_SERVICE_API_KEY=your-api-key  # Optional

# Resilience settings
EMAIL_SERVICE_TIMEOUT_SECONDS=5.0
EMAIL_SERVICE_MAX_RETRIES=2
EMAIL_SERVICE_RETRY_DELAY_SECONDS=0.5
EMAIL_SERVICE_CIRCUIT_BREAKER_THRESHOLD=5
EMAIL_SERVICE_CIRCUIT_BREAKER_TIMEOUT_SECONDS=60
```

### Sources

Integration patterns based on:
- [Microservices Communication: Sync vs Async](https://arizawan.com/2025/01/breaking-down-microservices-communication-sync-vs-async-which-pattern-is-right-for-your-architecture/)
- [Messaging Patterns for Event-Driven Microservices](https://solace.com/blog/messaging-patterns-for-event-driven-microservices/)
- [Synchronous vs Asynchronous Communication Patterns](https://www.theserverside.com/answer/Synchronous-vs-asynchronous-microservices-communication-patterns)

## Testing

### Running Tests

```bash
# Run all tests
pytest test/

# Run with verbose output
pytest test/ -v

# Run specific test file
pytest test/test_official_mcp_fixed.py -v

# Run with coverage report
pytest test/ --cov=. --cov-report=html
open htmlcov/index.html  # View coverage report
```

### Manual Testing

```bash
# Test MCP endpoints
./test/test_mcp_endpoints.sh

# Test individual tools
python -c "
from tools.fetch import fetch_by_sku
result = fetch_by_sku('COMP-001')
print(result)
"

# Test with httpx (Python)
python test/test_official_mcp_fixed.py
```

### Code Quality Checks

```bash
# Run Ruff linter
ruff check .

# Fix auto-fixable issues
ruff check . --fix

# Format code
ruff format .

# Check type hints (optional, if mypy is installed)
mypy server.py --config-file mypy.ini
```

## Deployment

### Production Checklist

- [ ] Set `LOG_LEVEL=WARNING` in production
- [ ] Use strong database credentials
- [ ] Enable PostgreSQL SSL/TLS connections
- [ ] Configure firewall (allow port 8009)
- [ ] Set up log rotation and monitoring
- [ ] Configure health check monitoring (every 60s)
- [ ] Use process manager (systemd, supervisor, Docker)
- [ ] Set up automatic database backups
- [ ] Configure rate limiting for API endpoints
- [ ] Set up alerting for health check failures

### Using Systemd (Linux)

Create `/etc/systemd/system/mcp-server.service`:

```ini
[Unit]
Description=MCP Product Search Server
After=network.target postgresql.service
Requires=postgresql.service

[Service]
Type=simple
User=mcp
Group=mcp
WorkingDirectory=/opt/mcp_server
Environment="PATH=/opt/mcp_server/venv/bin"
Environment="PYTHONUNBUFFERED=1"
EnvironmentFile=/opt/mcp_server/.env
ExecStart=/opt/mcp_server/venv/bin/python server.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

# Security settings
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

**Enable and start:**
```bash
sudo systemctl daemon-reload
sudo systemctl enable mcp-server
sudo systemctl start mcp-server
sudo systemctl status mcp-server

# View logs
sudo journalctl -u mcp-server -f
```

### Using Docker

The project includes a production-ready **multi-stage Dockerfile** with security best practices:

**Features:**
- ✅ Python 3.11 slim base (minimal image size)
- ✅ Multi-stage build (optimized layers)
- ✅ Non-root user (UID 1001) for security
- ✅ Built-in health check
- ✅ Configurable via environment variables

**Build and run:**
```bash
# Build image
docker build -t mcp-server:latest .

# Run container
docker run -d \
  --name mcp-server \
  -p 8009:8009 \
  --env-file .env \
  --restart unless-stopped \
  mcp-server:latest

# View logs
docker logs -f mcp-server

# Check health
docker inspect --format='{{.State.Health.Status}}' mcp-server
```

**Environment variables for Docker:**
```bash
# Required
DATABASE_URL=postgresql://user:pass@host:5432/db
GOOGLE_API_KEY=your-api-key

# Optional (with defaults)
MCP_PORT=8009
LOG_LEVEL=INFO
SCHEMA_NAME=test
```

### Using Docker Compose

See `../DockerConfig/docker-compose.yml` for complete setup with PostgreSQL, pgAdmin, and MCP Server.

## Troubleshooting

### Common Issues

#### 1. Database Connection Error

**Symptom:** `psycopg2.OperationalError: could not connect to server`

**Solutions:**
```bash
# Check PostgreSQL is running
sudo systemctl status postgresql
# or for Docker:
docker ps | grep mcp-postgres

# Verify connection string
echo $DATABASE_URL

# Test connection manually
psql "$DATABASE_URL" -c "SELECT 1"

# Check PostgreSQL logs
sudo journalctl -u postgresql -f
# or for Docker:
docker logs mcp-postgres
```

---

#### 2. Missing PostgreSQL Extension

**Symptom:** `ERROR: extension "pg_trgm" not found`

**Solutions:**
```bash
# Install PostgreSQL contrib package
# Ubuntu/Debian:
sudo apt-get install postgresql-contrib

# CentOS/RHEL:
sudo yum install postgresql-contrib

# Enable extensions
psql mcpdb -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;"
psql mcpdb -c "CREATE EXTENSION IF NOT EXISTS unaccent;"
psql mcpdb -c "CREATE EXTENSION IF NOT EXISTS vector;"

# Verify extensions
psql mcpdb -c "\dx"
```

---

#### 3. Google API Authentication Error

**Symptom:** `401 Unauthorized` or `Invalid API key`

**Solutions:**
```bash
# Verify API key is set
echo $GOOGLE_API_KEY

# Test API key directly
curl "https://generativelanguage.googleapis.com/v1/models?key=$GOOGLE_API_KEY"

# Get new API key
# Visit: https://makersuite.google.com/app/apikey

# Update .env file
nano .env  # Add: GOOGLE_API_KEY="your-new-key"
```

---

#### 4. Import Errors or Module Not Found

**Symptom:** `ModuleNotFoundError: No module named 'mcp'`

**Solutions:**
```bash
# Ensure virtual environment is activated
which python  # Should point to venv/bin/python

# Reinstall dependencies
pip install -r requirements.txt --force-reinstall

# Verify installation
pip list | grep mcp
```

---

#### 5. Port Already in Use

**Symptom:** `OSError: [Errno 98] Address already in use`

**Solutions:**
```bash
# Find process using port 8009
sudo lsof -i :8009
# or:
sudo netstat -tulpn | grep 8009

# Kill the process
kill -9 <PID>

# Or use different port
python server.py --port 8010
```

---

#### 6. Slow Semantic Search Performance

**Symptom:** Search takes >1000ms consistently

**Solutions:**
```bash
# Check if vector index exists
psql mcpdb -c "\d test.products"
# Look for: idx_products_embedding_ivf

# Create vector index if missing
psql mcpdb -c "
CREATE INDEX idx_products_embedding_ivf
ON test.products USING ivfflat (embedding vector_l2_ops)
WITH (lists = 100);
"

# Analyze table for query planner
psql mcpdb -c "ANALYZE test.products;"

# Check database load
top  # Look for high CPU/memory usage
```

### Debug Mode

Enable debug logging:

```bash
# Method 1: Environment variable
export LOG_LEVEL=DEBUG
python server.py

# Method 2: Edit .env file
echo "LOG_LEVEL=DEBUG" >> .env
python server.py

# Method 3: Temporary debug session
LOG_LEVEL=DEBUG python server.py
```

### Log Analysis

```bash
# View recent errors
tail -f logs/mcp_server.log | grep ERROR

# Monitor all logs
tail -f logs/*.log

# Search for exceptions
grep -r "Traceback" logs/

# Count errors by type
grep ERROR logs/mcp_server.log | cut -d'-' -f4 | sort | uniq -c
```

## Roadmap

### Current Version: v1.0

- ✅ Core MCP 1.2.0 implementation
- ✅ Semantic search with Gemini embeddings
- ✅ Fuzzy search with pg_trgm
- ✅ Health check monitoring
- ✅ Structured logging with rotation

### Planned Features

#### v1.1 (Next Release)
- [ ] WebSocket support for real-time updates
- [ ] Rate limiting per client
- [ ] API key authentication
- [ ] Prometheus metrics export
- [ ] GraphQL endpoint (optional)

#### v1.2 (Future)
- [ ] Multi-model embedding support (OpenAI, Cohere)
- [ ] Redis caching for frequent queries
- [ ] Advanced pagination with cursor-based navigation
- [ ] Bulk operations optimization
- [ ] Query suggestions and autocomplete

#### v2.0 (Long-term)
- [ ] Multi-tenant support
- [ ] Custom embedding fine-tuning
- [ ] Advanced analytics dashboard
- [ ] ML-powered query optimization
- [ ] Distributed deployment support

### Contributing to Roadmap

Have ideas for new features? Open an issue with the `enhancement` label or vote on existing proposals.

## Support

### Getting Help

For issues, questions, or suggestions:

1. **Check Documentation**: Review this README and inline code documentation
2. **Search Issues**: Check [existing GitHub issues](../../issues)
3. **Troubleshooting**: Review the [Troubleshooting](#troubleshooting) section
4. **Ask Questions**: Open a new [GitHub issue](../../issues/new)
5. **Community**: Join discussions in [GitHub Discussions](../../discussions)

### Reporting Bugs

When reporting bugs, please include:

1. MCP Server version (from `server.py`)
2. Python version (`python --version`)
3. PostgreSQL version (`psql --version`)
4. Operating system and version
5. Complete error message and stack trace
6. Steps to reproduce the issue
7. Expected vs. actual behavior

### Feature Requests

For feature requests:

1. Search existing feature requests first
2. Describe the use case and problem being solved
3. Provide examples of expected behavior
4. Indicate willingness to contribute (if applicable)

## Contributing

Contributions are welcome! We appreciate your help in making this project better.

### How to Contribute

1. **Fork** the repository
2. **Create** a feature branch: `git checkout -b feature/amazing-feature`
3. **Make** your changes with clear, descriptive commits
4. **Test** your changes thoroughly
5. **Run** quality checks (see below)
6. **Commit** your changes: `git commit -m 'Add amazing feature'`
7. **Push** to the branch: `git push origin feature/amazing-feature`
8. **Open** a Pull Request with description of changes

### Development Guidelines

**Code Style:**
- Follow PEP 8 style guidelines
- Use Ruff for formatting and linting
- Add type hints to all functions
- Write docstrings for public APIs (Google style)

**Testing:**
- Write tests for new features
- Ensure existing tests pass
- Aim for >80% code coverage
- Test edge cases and error conditions

**Quality Checks:**
```bash
# Before submitting PR, run:

# 1. Format code
ruff format .

# 2. Lint code
ruff check .

# 3. Fix auto-fixable issues
ruff check . --fix

# 4. Run tests
pytest test/ -v

# 5. Check coverage
pytest test/ --cov=. --cov-report=term

# 6. Type check (optional)
mypy server.py --config-file mypy.ini
```

**Commit Messages:**
- Use conventional commits format
- Examples:
  - `feat: add rate limiting support`
  - `fix: correct fuzzy search accent handling`
  - `docs: update installation instructions`
  - `refactor: simplify database connection logic`
  - `test: add tests for semantic search`

### Code Review Process

All pull requests require:
1. ✅ All quality checks passing
2. ✅ Tests covering new code
3. ✅ Documentation updated (if applicable)
4. ✅ At least one maintainer approval
5. ✅ No merge conflicts

## Authors and Acknowledgment

### Authors

- **Odiseo Team** - Initial work and ongoing maintenance

### Acknowledgments

This project is built on the shoulders of giants:

- **[Anthropic](https://www.anthropic.com/)** - For the official [MCP Python SDK](https://github.com/anthropics/mcp-python-sdk) and protocol specification
- **[Google AI](https://ai.google.dev/)** - For the Gemini AI API and embedding models
- **[PostgreSQL Team](https://www.postgresql.org/)** - For the world's most advanced open-source database
- **[pgvector Team](https://github.com/pgvector/pgvector)** - For high-performance vector operations in PostgreSQL
- **[Pydantic](https://docs.pydantic.dev/)** - For data validation and settings management
- **[Uvicorn](https://www.uvicorn.org/)** - For high-performance ASGI server

### Special Thanks

- Contributors who have submitted pull requests
- Users who reported bugs and provided feedback
- Open-source community for inspiration and best practices

## License

This project is licensed under the **MIT License**.

```
MIT License

Copyright (c) 2025 Odiseo Team

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

See the [LICENSE](../LICENSE) file in the project root for full details.

## Project Status

### Current Status: Production Ready ✅

This project is **actively maintained** and **production-ready**.

**Stability:** Stable
**Version:** 1.4.0
**MCP Protocol:** 1.21.0 (Official Anthropic SDK)
**Last Updated:** December 2025

**Recent Changes (v1.4.0):**
- ✅ Concurrency control with semaphore-based limiting (50 concurrent requests)
- ✅ Rate limiting for search (30/min) and booking (20/min) operations
- ✅ Full async database migration (asyncpg replaces psycopg2)
- ✅ Docker improvements: named volumes, log rotation, configurable healthcheck
- ✅ New `utils/concurrency.py` module
- ✅ Streamlined to 12 tools (removed user management - handled by separate service)

**Previous (v1.3.0):**
- ✅ HTTP Email Service Integration with Circuit Breaker pattern
- ✅ Fire-and-Forget async email notifications
- ✅ Configurable retry logic with exponential backoff

**Build Status:**
- ✅ All tests passing
- ✅ Code quality checks passing (Ruff)
- ✅ Type hints coverage: 100%
- ✅ Documentation: Complete
- ✅ Security audit: Passed

**Maintenance:**
- 🟢 Actively maintained
- 🔄 Regular security updates
- 📝 Active issue tracker
- 💬 Community discussions open

**Compatibility:**
- Python: 3.10, 3.11, 3.12
- PostgreSQL: 14, 15, 16
- MCP Protocol: 1.21.0+
- Operating Systems: Linux, macOS, Windows (WSL)
- Docker: 20.10+ (multi-stage builds)

**Production Features:**
- ✅ Concurrency control (MAX_CONCURRENT_REQUESTS=50)
- ✅ Rate limiting per session
- ✅ Named Docker volumes for logs
- ✅ Log rotation (json-file driver, 10m max, 3 files)
- ✅ Configurable healthcheck intervals
- ✅ Non-root Docker container (UID 1001)
- ✅ Async database with connection pooling

**Known Issues:** None

**Breaking Changes:** None planned for v1.x

---

**Questions?** Open an [issue](../../issues/new) or start a [discussion](../../discussions).

**Built with ❤️ by Odiseo Team using the official Anthropic MCP Python SDK v1.21.0**
