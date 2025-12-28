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
└── 001_create_otp_codes.sql            # OTP table migration
scripts/
├── init_cloud_sql.py      # Python database initializer
└── load_sample_products.py # Sample product loader with embeddings
```

### Deployment Phases (deploy/README.md)
1. **GCP Project Setup** - APIs, Artifact Registry
2. **Cloud SQL Setup** - PostgreSQL 15, pgvector, user
3. **Secret Manager Setup** - database-url, google-api-key
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
```
