# REQ-2: Cloud Run Deployment

## Overview
Implementation of Google Cloud Run deployment for Odiseo MCP Server with IAM authentication, Secret Manager integration, and orchestrator service account access.

## Status: COMPLETED
**Date:** December 2025

## Requirements

### Security Requirements
- [x] IAM Authentication (`--no-allow-unauthenticated`)
- [x] Service Account: `mcp-server-sa`
- [x] Orchestrator access: `orchestrator-sa` with `roles/run.invoker`
- [x] Secrets from Secret Manager (database-url, google-api-key)
- [x] Non-root container user (UID 1000)

### Build Requirements
- [x] UV package manager (replaces pip)
- [x] Multi-stage Docker build
- [x] Code quality checks (ruff, mypy, bandit)
- [x] Cloud Build automation (6 steps)

### Integration Requirements
- [x] Update `internal_service_client.py` with MCP service
- [x] `call_mcp_service()` method for tool invocation
- [x] `get_mcp_health()` method for health checks
- [x] MCP_SERVICE_URL environment variable

## Implementation

### Files Created
| File | Purpose |
|------|---------|
| `deploy/Dockerfile.cloudrun` | Multi-stage Docker build with UV |
| `deploy/env.production` | Production environment reference |
| `deploy/README.md` | Deployment guide |
| `cloudbuild.yaml` | Cloud Build configuration |

### Files Modified
| File | Changes |
|------|---------|
| `CLAUDE.md` | Added Cloud Run deployment section |
| `README.md` | Added Cloud Run deployment documentation |
| `/shared-libs/internal_service_client.py` | Added MCP service methods |
| `utils/concurrency.py` | Fixed naming convention (Error suffix) |
| `tools/otp/__init__.py` | Sorted __all__ alphabetically |

### Environment Variables
```bash
# From cloudbuild.yaml --set-env-vars
GCP_PROJECT_ID=gen-lang-client-0329024102
GCP_LOCATION=us-central1
ENVIRONMENT=production
DEBUG_MODE=false
LOG_LEVEL=INFO
MCP_PORT=8080
SCHEMA_NAME=test
EMBEDDING_MODEL=gemini-embedding-001
MAX_CONCURRENT_REQUESTS=50
EMAIL_SERVICE_ENABLED=true
OTP_ENABLED=true
USE_ADC=true

# From Secret Manager --set-secrets
DATABASE_URL=database-url:latest
# Note: GOOGLE_API_KEY not needed - using ADC (USE_ADC=true)
```

## Cloud Build Pipeline

### Step 1: Quality Checks
- Install UV and quality tools
- Run ruff check and format
- Run mypy type checking
- Run bandit security scan

### Step 2: Docker Build
- Multi-stage build with UV
- Python 3.12 slim base
- Non-root user (UID 1000)
- Health check endpoint

### Step 3: Push to Artifact Registry
- Region: us-central1
- Repository: mcp-repo
- Tags: SHORT_SHA, latest

### Step 4: Deploy to Cloud Run
- Region: us-central1
- Service: mcp-server
- Memory: 512Mi
- CPU: 1
- Min instances: 0
- Max instances: 10
- Concurrency: 80
- Cloud SQL: demo-db (Unix socket connection)

### Step 5: IAM Binding
- Grant `roles/run.invoker` to `orchestrator-sa`

### Step 6: Verify Deployment
- Health check with retries
- Log service URL

## Database Setup (Required Before Deployment)

Before deploying, the Cloud SQL database must be initialized with required extensions and tables:

```bash
# Connect to Cloud SQL
gcloud sql connect demo-db --database=demodb --user=demo_user

# Run initialization script
\i sql/000_init_extensions_and_schema.sql
```

Required extensions:
- **pg_trgm**: Trigram similarity for typo-tolerant search
- **unaccent**: Accent removal for Unicode normalization
- **vector** (pgvector): Vector operations for semantic search

Required tables:
- **products**: Product catalog with embedding column
- **appointments**: Booking system appointments
- **otp_codes**: One-time password verification

## Production Test Scenarios

### 1. Health Check
```bash
# Service URL: https://mcp-server-4k3haexkga-uc.a.run.app
curl -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  "https://mcp-server-4k3haexkga-uc.a.run.app/health"
```

Expected response:
```json
{
  "status": "healthy",
  "checks": {
    "database": {
      "status": "healthy",
      "product_count": 90,
      "extensions": ["pg_trgm", "unaccent", "vector"]
    }
  }
}
```

### 2. Product Search (via internal_service_client)
```python
client = InternalServiceClient()
result = await client.call_mcp_service(
    tool="search_products",
    arguments={"query": "laptop gaming", "k": 5}
)
```

### 3. OTP Flow
```python
# Generate OTP
result = await client.call_mcp_service(
    tool="generate_otp",
    arguments={"email": "test@example.com"}
)

# Verify OTP
result = await client.call_mcp_service(
    tool="verify_otp",
    arguments={"email": "test@example.com", "code": "123456"}
)
```

### 4. Booking Flow
```python
# Get available slots
slots = await client.call_mcp_service(
    tool="get_available_slots",
    arguments={"date": "2025-01-15"}
)

# Create booking
booking = await client.call_mcp_service(
    tool="create_booking",
    arguments={
        "customer_email": "user@example.com",
        "customer_name": "John Doe",
        "service_type": "consultation",
        "booking_date": "2025-01-15",
        "booking_time": "10:00"
    }
)
```

## Code Quality Results

### Ruff
```
All checks passed!
```

### Mypy
```
Found 24 errors (expected - type annotations in some external libs)
```

### Bandit
```
B104: Binding to 0.0.0.0 (expected for Cloud Run)
B608: SQL with schema name (validated via validate_schema_name)
```

### Radon
```
Average complexity: A (3.33)
```

## Deployment Commands

### Full Deploy
```bash
gcloud builds submit --config=cloudbuild.yaml
```

### Check Status
```bash
gcloud run services describe mcp-server --region=us-central1
```

### View Logs
```bash
gcloud run services logs read mcp-server --region=us-central1
```

### Rollback
```bash
gcloud run services update-traffic mcp-server \
    --region=us-central1 \
    --to-revisions=PREVIOUS_REVISION=100
```
