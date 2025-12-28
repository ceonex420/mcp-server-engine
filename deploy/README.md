# Odiseo MCP Server - Production Deployment Guide

Complete guide to deploy the MCP Server to Google Cloud Run from scratch.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Phase 1: GCP Project Setup](#phase-1-gcp-project-setup)
3. [Phase 2: Cloud SQL Setup](#phase-2-cloud-sql-setup)
4. [Phase 3: Secret Manager Setup](#phase-3-secret-manager-setup)
5. [Phase 4: Service Account Configuration](#phase-4-service-account-configuration)
6. [Phase 5: Database Initialization](#phase-5-database-initialization)
7. [Phase 6: Deploy to Cloud Run](#phase-6-deploy-to-cloud-run)
8. [Phase 7: Verification](#phase-7-verification)
9. [Phase 8: Load Sample Data](#phase-8-load-sample-data)
10. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Required Tools

```bash
# Google Cloud SDK
curl https://sdk.cloud.google.com | bash
gcloud init

# Docker (for local testing)
# https://docs.docker.com/engine/install/

# Python 3.11+ (for scripts)
python3 --version

# UV package manager (recommended)
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### GCP Account Requirements

- Billing enabled
- Owner or Editor role on the project
- Sufficient quotas for Cloud Run, Cloud SQL, Artifact Registry

---

## Phase 1: GCP Project Setup

### 1.1 Set Project Variables

```bash
# Set your project ID
export PROJECT_ID="your-project-id"
export REGION="us-central1"
export SERVICE_NAME="mcp-server"

# Configure gcloud
gcloud config set project $PROJECT_ID
gcloud config set compute/region $REGION
```

### 1.2 Enable Required APIs

```bash
gcloud services enable \
    run.googleapis.com \
    cloudbuild.googleapis.com \
    artifactregistry.googleapis.com \
    secretmanager.googleapis.com \
    sqladmin.googleapis.com \
    aiplatform.googleapis.com
```

### 1.3 Create Artifact Registry Repository

```bash
gcloud artifacts repositories create mcp-repo \
    --repository-format=docker \
    --location=$REGION \
    --description="Odiseo MCP Server images"

# Verify
gcloud artifacts repositories list --location=$REGION
```

---

## Phase 2: Cloud SQL Setup

### 2.1 Create Cloud SQL Instance

```bash
# Create PostgreSQL 15 instance
gcloud sql instances create demo-db \
    --database-version=POSTGRES_15 \
    --tier=db-f1-micro \
    --region=$REGION \
    --storage-type=SSD \
    --storage-size=10GB \
    --database-flags=cloudsql.enable_pgaudit=off

# Wait for instance to be ready (3-5 minutes)
gcloud sql instances describe demo-db --format='value(state)'
```

### 2.2 Create Database and User

```bash
# Create database
gcloud sql databases create demodb --instance=demo-db

# Create user (save this password securely!)
export DB_PASSWORD=$(openssl rand -base64 24)
echo "Database Password: $DB_PASSWORD"

gcloud sql users create demo_user \
    --instance=demo-db \
    --password=$DB_PASSWORD
```

### 2.3 Enable pgvector Extension

```bash
# Connect to Cloud SQL (requires Cloud SQL Auth Proxy or Cloud Shell)
gcloud sql connect demo-db --database=demodb --user=postgres

# In psql prompt, run:
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;
\q
```

### 2.4 Get Connection Details

```bash
# Get instance connection name
export INSTANCE_CONNECTION=$(gcloud sql instances describe demo-db \
    --format='value(connectionName)')
echo "Instance Connection: $INSTANCE_CONNECTION"

# Build DATABASE_URL for Cloud Run (Unix socket)
export DATABASE_URL="postgresql://demo_user:${DB_PASSWORD}@/${demodb}?host=/cloudsql/${INSTANCE_CONNECTION}"
echo "DATABASE_URL: $DATABASE_URL"
```

---

## Phase 3: Secret Manager Setup

### 3.1 Create Secrets

```bash
# Store database URL
echo -n "$DATABASE_URL" | gcloud secrets create database-url --data-file=-

# Store Google API Key (get from https://aistudio.google.com/apikey)
echo -n "your-google-api-key" | gcloud secrets create google-api-key --data-file=-

# Verify secrets
gcloud secrets list
```

### 3.2 (Optional) Update Secrets Later

```bash
# Add new version
echo -n "new-value" | gcloud secrets versions add database-url --data-file=-

# View secret value
gcloud secrets versions access latest --secret=database-url
```

---

## Phase 4: Service Account Configuration

### 4.1 Create Service Account

```bash
# Create service account for MCP Server
gcloud iam service-accounts create mcp-server-sa \
    --display-name="MCP Server Service Account"

export MCP_SA="mcp-server-sa@${PROJECT_ID}.iam.gserviceaccount.com"
```

### 4.2 Grant Required Roles

```bash
# Cloud SQL Client (database connection)
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$MCP_SA" \
    --role="roles/cloudsql.client"

# Secret Manager Accessor (read secrets)
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$MCP_SA" \
    --role="roles/secretmanager.secretAccessor"

# AI Platform User (Gemini embeddings via ADC)
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$MCP_SA" \
    --role="roles/aiplatform.user"
```

### 4.3 Create Orchestrator Service Account (for calling MCP)

```bash
# This SA will be used by other services to invoke MCP
gcloud iam service-accounts create orchestrator-sa \
    --display-name="Orchestrator Service Account"

export ORCHESTRATOR_SA="orchestrator-sa@${PROJECT_ID}.iam.gserviceaccount.com"
```

---

## Phase 5: Database Initialization

### 5.1 Option A: Using Python Script (Recommended)

```bash
# From mcp-server directory
cd /path/to/mcp-server

# Install dependencies
uv pip install --system asyncpg

# Set DATABASE_URL (use direct connection for initialization)
export DATABASE_URL="postgresql://demo_user:${DB_PASSWORD}@<CLOUD_SQL_IP>:5432/demodb"

# Run initialization
python scripts/init_cloud_sql.py
```

### 5.2 Option B: Using SQL Script

```bash
# Connect via Cloud Shell or psql
gcloud sql connect demo-db --database=demodb --user=demo_user

# Run the initialization script
\i sql/000_init_extensions_and_schema.sql
\i sql/001_create_otp_codes.sql
```

### 5.3 Verify Database Setup

```bash
# Connect and check
gcloud sql connect demo-db --database=demodb --user=demo_user

# Verify tables
\dt test.*

# Verify extensions
SELECT extname, extversion FROM pg_extension;

# Verify normalize_text function
SELECT test.normalize_text('Café');
-- Should return: cafe
```

---

## Phase 6: Deploy to Cloud Run

### 6.1 Option A: Deploy with Cloud Build (Recommended)

```bash
# From mcp-server directory
gcloud builds submit --config=cloudbuild.yaml

# Cloud Build will:
# 1. Run quality checks (ruff, mypy, bandit)
# 2. Build Docker image with UV
# 3. Push to Artifact Registry
# 4. Deploy to Cloud Run
# 5. Grant invoker role to orchestrator-sa
# 6. Verify deployment
```

### 6.2 Option B: Manual Deployment

```bash
# Build image
docker build -f deploy/Dockerfile.cloudrun -t mcp-server .

# Tag for Artifact Registry
docker tag mcp-server \
    ${REGION}-docker.pkg.dev/${PROJECT_ID}/mcp-repo/mcp-server:latest

# Configure Docker authentication
gcloud auth configure-docker ${REGION}-docker.pkg.dev

# Push image
docker push ${REGION}-docker.pkg.dev/${PROJECT_ID}/mcp-repo/mcp-server:latest

# Deploy to Cloud Run
gcloud run deploy mcp-server \
    --image=${REGION}-docker.pkg.dev/${PROJECT_ID}/mcp-repo/mcp-server:latest \
    --region=$REGION \
    --platform=managed \
    --service-account=$MCP_SA \
    --no-allow-unauthenticated \
    --port=8080 \
    --memory=512Mi \
    --cpu=1 \
    --min-instances=0 \
    --max-instances=10 \
    --timeout=300 \
    --add-cloudsql-instances=${PROJECT_ID}:${REGION}:demo-db \
    --set-env-vars="GCP_PROJECT_ID=${PROJECT_ID},GCP_LOCATION=${REGION},ENVIRONMENT=production,DEBUG_MODE=false,LOG_LEVEL=INFO,MCP_PORT=8080,SCHEMA_NAME=test,EMBEDDING_MODEL=gemini-embedding-001,EMBEDDING_DIMENSION=1536,USE_ADC=true,OTP_ENABLED=true" \
    --set-secrets="DATABASE_URL=database-url:latest"
```

### 6.3 Grant Invoker Access

```bash
# Allow orchestrator to call MCP service
gcloud run services add-iam-policy-binding mcp-server \
    --region=$REGION \
    --member="serviceAccount:$ORCHESTRATOR_SA" \
    --role="roles/run.invoker"
```

---

## Phase 7: Verification

### 7.1 Get Service URL

```bash
export SERVICE_URL=$(gcloud run services describe mcp-server \
    --region=$REGION \
    --format='value(status.url)')
echo "Service URL: $SERVICE_URL"
```

### 7.2 Health Check

```bash
# Get identity token (for authenticated request)
TOKEN=$(gcloud auth print-identity-token)

# Check health endpoint
curl -s -H "Authorization: Bearer $TOKEN" \
    "$SERVICE_URL/health" | python -m json.tool
```

Expected response:
```json
{
    "status": "healthy",
    "environment": "production",
    "timestamp": "2025-12-28T...",
    "services": {
        "database": "connected",
        "embedding": "available"
    }
}
```

### 7.3 View Logs

```bash
# Stream logs
gcloud run services logs read mcp-server --region=$REGION --tail=50

# Or via Cloud Console
echo "https://console.cloud.google.com/run/detail/${REGION}/mcp-server/logs?project=${PROJECT_ID}"
```

### 7.4 Check Service Status

```bash
gcloud run services describe mcp-server --region=$REGION
```

---

## Phase 8: Load Sample Data

### 8.1 Load Products with Embeddings

```bash
# Set environment variables
export DATABASE_URL="postgresql://demo_user:${DB_PASSWORD}@<CLOUD_SQL_IP>:5432/demodb"
export GOOGLE_API_KEY="your-google-api-key"

# Install dependencies
uv pip install --system asyncpg google-genai pgvector numpy

# Load sample products (15 items)
python scripts/load_sample_products.py
```

### 8.2 Verify Products

```bash
# Connect to database
gcloud sql connect demo-db --database=demodb --user=demo_user

# Check product count
SELECT COUNT(*) FROM test.products;

# View products
SELECT sku, name, category, price FROM test.products LIMIT 10;

# Test semantic search (requires embedding)
SELECT name, description
FROM test.products
ORDER BY embedding <-> (SELECT embedding FROM test.products WHERE sku = 'COMP-0001')
LIMIT 5;
```

---

## Troubleshooting

### Common Issues

#### "Invalid Host header" Error
**Cause:** DNS rebinding protection blocking Cloud Run hosts
**Solution:** Already fixed in server.py with `TransportSecuritySettings(enable_dns_rebinding_protection=False)`

#### "Permission denied" for Cloud SQL
**Cause:** Service account missing roles
**Solution:**
```bash
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$MCP_SA" \
    --role="roles/cloudsql.client"
```

#### "Permission denied" for Embeddings
**Cause:** Missing aiplatform.user role
**Solution:**
```bash
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$MCP_SA" \
    --role="roles/aiplatform.user"
```

#### "Secret not found"
**Cause:** Secret doesn't exist or SA can't access
**Solution:**
```bash
# Verify secret exists
gcloud secrets list

# Grant access
gcloud secrets add-iam-policy-binding database-url \
    --member="serviceAccount:$MCP_SA" \
    --role="roles/secretmanager.secretAccessor"
```

#### "Extension vector does not exist"
**Cause:** pgvector not installed on Cloud SQL
**Solution:**
```bash
gcloud sql connect demo-db --database=demodb --user=postgres
# Then run: CREATE EXTENSION IF NOT EXISTS vector;
```

### Useful Commands

```bash
# View service details
gcloud run services describe mcp-server --region=$REGION

# View logs
gcloud run services logs read mcp-server --region=$REGION

# List revisions
gcloud run revisions list --service=mcp-server --region=$REGION

# Delete and redeploy
gcloud run services delete mcp-server --region=$REGION
gcloud builds submit --config=cloudbuild.yaml

# Check Cloud Build history
gcloud builds list --limit=5
```

### Local Testing

```bash
# Build locally
docker build -f deploy/Dockerfile.cloudrun -t mcp-server .

# Run with local environment
docker run -p 8080:8080 \
    -e DATABASE_URL="postgresql://user:pass@host:5432/db" \
    -e GOOGLE_API_KEY="your-key" \
    -e ENVIRONMENT="development" \
    mcp-server

# Test health
curl http://localhost:8080/health
```

---

## Files Reference

| File | Description |
|------|-------------|
| `deploy/Dockerfile.cloudrun` | Multi-stage Docker build with UV |
| `deploy/env.production` | Environment variables reference |
| `cloudbuild.yaml` | Cloud Build configuration (6 steps) |
| `sql/000_init_extensions_and_schema.sql` | Database initialization |
| `sql/001_create_otp_codes.sql` | OTP table migration |
| `scripts/init_cloud_sql.py` | Python database initializer |
| `scripts/load_sample_products.py` | Sample product loader |

---

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
│   + pgvector    │  │  google-api-key │  │  (via ADC)      │
└─────────────────┘  └─────────────────┘  └─────────────────┘
```

## Security

- **IAM Authentication:** `--no-allow-unauthenticated`
- **Service Account:** Workload Identity Federation
- **Secrets:** Secret Manager (never in env vars)
- **Database:** Cloud SQL with private connection
- **Embeddings:** Application Default Credentials (no API key in production)

---

## Next Steps

1. **Set up CI/CD trigger:** Connect Cloud Build to GitHub for automatic deployments
2. **Configure alerting:** Set up Cloud Monitoring alerts for errors
3. **Enable autoscaling:** Adjust min/max instances based on traffic
4. **Add custom domain:** Configure Cloud Run domain mapping
