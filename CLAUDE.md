# Odiseo MCP Server - Project Context

## Current State
- Proyecto refactorizado
- Sistema i18n eliminado (el LLM maneja la localización via prompts)
- Módulo tools reorganizado: tools/sales/ contiene fetch, search, fuzzy_search
- MCP handlers renombrados: product_handlers.py → sales_handlers.py
- Recursos MCP actualizados: tool-categories://sales
- All tool docstrings and messages in English
- MCP Server es proveedor puro de herramientas (prompts de agentes en servicio separado)
- Rate limiting implementado (utils/rate_limiter.py) para OTP y búsquedas
- MCP Context usage: ctx.report_progress(), ctx.info(), ctx.debug(), ctx.warning(), ctx.error()
- Resources async con MIME types y error responses estructurados en JSON
- ToolAnnotations agregadas a tools principales (readOnlyHint, idempotentHint, openWorldHint)
- Embedding caching implementado (1000 entries LRU cache)
- Reorganización: tool_registry.py y tool_discovery_validator.py movidos a utils/
- Agregar banner a MCP
- MCP funcionando
- UV package manager (10-100x faster than pip) - migración completa
- 45 productos de prueba cargados en test.products con embeddings
- Documentación completa de despliegue en deploy/README.md (8 fases)
- Code review exhaustivo completado (14 tools, 6 resources verificados)
- Production test suite: 24/24 tests passing (scripts/test_production.py)
- Fix Decimal serialization en product://sku resource
- Booking system fully operational (migration 002 applied)
- Tables: service_types, business_hours + appointments columns added
- Functions: is_slot_available(), get_available_slots()
- Visual Search 4-tier confidence system (2026-01-22)

## Visual Search Confidence Tiers (2026-01-22)

`tools/sales/embedding_search.py` implementa sistema de 4 niveles de confianza:

| Tier | Threshold | Response |
|------|-----------|----------|
| high | ≥75% | Productos mostrados con confianza |
| medium | 60-75% | Productos con nota "podrían interesarte" |
| low | 45-60% | Productos con `low_confidence: True` |
| none | <45% | Sin resultados (filtrados) |

**Response incluye:**
```json
{
  "items": [...],
  "confidence_tier": "high",
  "best_match_score": 0.956,
  "search_type": "embedding_similarity"
}
```

**Logs:**
```
visual_search_tier_classification: tier=high, high=5, medium=0, low=0, best_score=0.956
```

## Production Test Suite (Dec 2025)

### Test Script
- `scripts/test_production.py`: Automated MCP testing against Cloud Run
- Handles SSE response format from streamable-http transport
- Parses JSON-RPC responses with notifications filtering

### Test Results: 24/24 ✅
| Category | Tests | Status |
|----------|-------|--------|
| Health Check | 1 | ✅ |
| MCP Protocol | 3 | ✅ (initialize, tools/list, resources/list) |
| Sales Tools | 4 | ✅ (fetch_by_sku, fetch_by_id, search, fuzzy) |
| Booking Tools | 8 | ✅ (all tools functional after migration 002) |
| OTP Tools | 2 | ✅ (generate_otp, verify_otp) |
| MCP Resources | 6 | ✅ (product, database, tool-categories) |

### Run Tests
```bash
python scripts/test_production.py
```

### Key Findings
- Service URL: `https://mcp-server-4k3haexkga-uc.a.run.app`
- Server Version: Odiseo MCP Server v1.25.0
- Average response time: ~300ms per tool call
- Database: 45 products with embeddings

## Cloud Run Deployment (Dec 2025)

> **Complete Guide:** See `deploy/README.md` for step-by-step deployment from scratch.

### Deployment Structure
```
deploy/
├── Dockerfile.cloudrun    # Multi-stage build with UV package manager
├── env.production         # Production environment variables reference
└── README.md              # Complete 8-phase deployment guide
cloudbuild.yaml            # Cloud Build configuration (6 steps)
sql/
├── 000_init_extensions_and_schema.sql  # Database initialization
├── 001_create_otp_codes.sql            # OTP table migration
└── 002_create_booking_tables.sql       # Booking system tables and functions
scripts/
├── init_cloud_sql.py          # Python database initializer
├── load_sample_products.py    # Sample product loader with embeddings
├── migrate_booking_tables.py  # Booking migration runner (asyncpg)
└── test_production.py         # Production test suite (24 scenarios)
```

### Deployment Phases (deploy/README.md)
1. **GCP Project Setup** - APIs, Artifact Registry
2. **Cloud SQL Setup** - PostgreSQL 15, pgvector, user
3. **Secret Manager Setup** - database-url (only, GOOGLE_API_KEY uses ADC)
4. **Service Account Config** - IAM roles (cloudsql.client, secretmanager.secretAccessor, aiplatform.user)
5. **Database Initialization** - Extensions, schema, tables, functions
6. **Deploy to Cloud Run** - Cloud Build or manual
7. **Verification** - Health checks, logs
8. **Load Sample Data** - Products with embeddings

### Security Configuration
- IAM Authentication: `--no-allow-unauthenticated`
- Service Account: `mcp-server-sa@gen-lang-client-0329024102.iam.gserviceaccount.com`
- Orchestrator Access: `orchestrator-sa` has `roles/run.invoker`
- Secrets: Only `database-url` in Secret Manager (GOOGLE_API_KEY not needed - uses ADC)

### Cloud Build Steps
1. Quality checks (ruff, mypy, bandit) with UV
2. Docker build (multi-stage with UV)
3. Push to Artifact Registry
4. Deploy to Cloud Run
5. Grant IAM binding to orchestrator-sa
6. Verify deployment

### Environment Variables
- From cloudbuild.yaml `--set-env-vars`:
  - GCP_PROJECT_ID, GCP_LOCATION, ENVIRONMENT
  - DEBUG_MODE=false, LOG_LEVEL=INFO
  - MCP_PORT=8080, SCHEMA_NAME=test
  - EMBEDDING_MODEL, EMBEDDING_DIMENSION, BATCH_SIZE
  - MAX_CONCURRENT_REQUESTS=50
  - EMAIL_SERVICE_ENABLED, EMAIL_SERVICE_BASE_URL
  - OTP_ENABLED, OTP_CODE_LENGTH, OTP_EXPIRY_MINUTES
  - USE_ADC=true (Application Default Credentials)
- From Secret Manager `--set-secrets`:
  - DATABASE_URL=database-url:latest
  - (GOOGLE_API_KEY not needed - USE_ADC=true handles embeddings via Vertex AI)

### Service Integration
- Updated `/home/javort/shared-libs/internal_service_client.py`
- New methods: `call_mcp_service()`, `get_mcp_health()`
- MCP_SERVICE_URL env variable or default URL
- Added to health_check() services

### Deployment Commands
```bash
# Deploy with Cloud Build
gcloud builds submit --config=cloudbuild.yaml

# Manual deploy
gcloud run deploy mcp-server \
    --image=us-central1-docker.pkg.dev/gen-lang-client-0329024102/mcp-repo/mcp-server:latest \
    --region=us-central1 \
    --service-account=mcp-server-sa@gen-lang-client-0329024102.iam.gserviceaccount.com \
    --no-allow-unauthenticated
```

### Production Test Scenarios
1. **Health Check**: `curl -H "Authorization: Bearer $(gcloud auth print-identity-token)" "$SERVICE_URL/health"`
2. **Product Search**: Call via internal_service_client with search_products tool
3. **OTP Generation**: Test generate_otp and verify_otp tools
4. **Booking Flow**: Test create_booking, get_available_slots

### Code Quality
- Ruff: All checks passing
- Mypy: Type checking with --ignore-missing-imports
- Bandit: Security scan (B104, B608 are expected for Cloud Run)
- Radon: Average complexity A (3.33)

## UV Package Manager Migration (Dec 2025)

### Files Updated
- `Dockerfile`: Uses `uv pip install` with `UV_SYSTEM_PYTHON=1`
- `deploy/Dockerfile.cloudrun`: UV for fast builds
- `cloudbuild.yaml`: UV for quality checks and builds
- `Makefile`: New targets `install-uv`, `install`, `install-dev`
- `README.md`: Installation instructions with uv (pip as fallback)
- `requirements.txt`: Updated comments

### Usage
```bash
# Install uv (first time)
make install-uv

# Install dependencies
make install

# Install dev dependencies
make install-dev
```

## Sample Products Data

### Script
- `scripts/load_sample_products.py`: Loads products with Gemini embeddings

### Categories (45 products total)
- Computing (laptops, keyboards, mice, monitors)
- Home (vacuums, lights, air purifiers, thermostats)
- Audio (headphones, speakers, earbuds)
- Office (chairs, desks, monitors)
- Sports (fitness trackers, yoga mats, bikes)
- Kitchen (pans, coffee makers, blenders)
- Accessories (phone cases, chargers, cables)

## Booking System Migration (Dec 2025)

### Migration Files
- `sql/002_create_booking_tables.sql` - psql migration script
- `scripts/migrate_booking_tables.py` - Python asyncpg migration runner

### Created Objects
| Object | Type | Description |
|--------|------|-------------|
| service_types | Table | Available services catalog (5 sample services) |
| business_hours | Table | Operating hours Mon-Sat (6 entries) |
| is_slot_available() | Function | Check if time slot is available |
| get_available_slots() | Function | List all slots for a date |

### Appointments Table Columns Added
- `google_calendar_event_id` VARCHAR(255) - Calendar event ID
- `google_calendar_link` VARCHAR(255) - Calendar event link
- `cancellation_reason` TEXT - Reason for cancellation
- `cancelled_at` TIMESTAMPTZ - Cancellation timestamp

### Sample Data
- **Services**: consultation, demo, support, training, followup
- **Hours**: Mon-Fri 9:00-18:00 (break 13:00-14:00), Sat 10:00-14:00

### Run Migration
```bash
# Using Python script (requires DATABASE_URL)
python scripts/migrate_booking_tables.py
```

## MCP Tools Inventory

### Sales Tools (4)
- `fetch_by_sku` - Direct SKU lookup (readOnly, idempotent)
- `fetch_by_id` - Direct ID lookup (readOnly, idempotent)
- `search_products` - Semantic search with Gemini embeddings (readOnly, openWorld)
- `fuzzy_search_smart` - Fuzzy text search with pg_trgm (readOnly, idempotent)

### Booking Tools (8)
- `create_booking` - Create new reservations with Google Calendar
- `cancel_booking` - Cancel existing bookings
- `reschedule_booking` - Change booking date/time
- `get_available_slots` - Check availability for date
- `get_booking_by_id` - Get booking details
- `list_customer_bookings` - Customer booking history
- `get_services` - Available services catalog
- `get_business_hours` - Operating hours

### OTP Tools (2)
- `generate_otp` - Generate and send OTP via email (rate limited)
- `verify_otp` - Verify OTP code (timing-safe comparison)

### MCP Resources (6)
- `product://sku/{sku}` - Product access by SKU
- `database://stats` - Database statistics
- `tool-categories://sales` - Sales tools discovery
- `tool-categories://bookings` - Booking tools discovery
- `tool-categories://pageable-tools` - Pageable tools discovery
- `tool-categories://otp` - OTP tools discovery

## Architecture

```
                    ┌─────────────────────┐
                    │   Cloud Run (MCP)   │
                    │   mcp-server-sa     │
                    └──────────┬──────────┘
                               │
          ┌────────────────────┼────────────────────┐
          │                    │                    │
          ▼                    ▼                    ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│   Cloud SQL     │  │ Secret Manager  │  │  AI Platform    │
│   PostgreSQL    │  │  database-url   │  │ Gemini Embed    │
│   + pgvector    │  │    (only)       │  │  (via ADC)      │
└─────────────────┘  └─────────────────┘  └─────────────────┘
```

## Lessons Learned

| Issue | Context | Solution |
|-------|---------|----------|
| stateless_http | FastMCP on Cloud Run | Add `stateless_http=True` to FastMCP configuration |
| decimal_json | Product resource returning price | Convert `Decimal` to `float()` before JSON serialization |
| adc_for_embeddings | Gemini API access | `USE_ADC=true` eliminates need for GOOGLE_API_KEY secret |
| sse_response_parsing | Production test suite | Parse SSE format with JSON-RPC notifications filtering |
| unaccent_search | Spanish/accented text search | Use `unaccent` extension with `pg_trgm` for fuzzy matching |
| booking_migration | Adding booking system | Use `asyncpg` for Python migrations, `psql` for SQL scripts |

## Anti-Patterns (Don't Do)

- **Never create duplicate files for corrections** (e.g., `models_simple.py`) - edit the original
- **Never store GOOGLE_API_KEY in secrets** - use ADC (`USE_ADC=true`)
- **Never allow unauthenticated access** to Cloud Run (`--no-allow-unauthenticated`)
- **Never skip Decimal to float conversion** in JSON responses
- **Never use pip when UV is available** - UV is 10-100x faster

## Code Patterns

### MCP Context Logging
```python
ctx.report_progress(current, total)
ctx.info("message")
ctx.debug("message")
ctx.warning("message")
ctx.error("message")
```

### Tool Annotations
```python
from mcp.server.fastmcp import ToolAnnotations

annotations=ToolAnnotations(
    readOnlyHint=True,
    idempotentHint=True,
    openWorldHint=False
)
```

### Async Resources
- All resources must be `async`
- Include MIME types in responses
- Return structured JSON error responses

### Decimal Serialization
```python
# Always convert Decimal to float for JSON
price = float(product.price)  # NOT product.price directly
```

## Quick Commands

```bash
# Deploy
gcloud builds submit --config=cloudbuild.yaml

# Health check
curl -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
    "$(gcloud run services describe mcp-server --region=us-central1 --format='value(status.url)')/health"

# View logs
gcloud run services logs read mcp-server --region=us-central1

# Local development
make install-dev
python server.py

# Run production tests
python scripts/test_production.py
```
