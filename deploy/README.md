# Odiseo MCP Server - Cloud Run Deployment

This directory contains all files needed for deploying the MCP Server to Google Cloud Run.

## Prerequisites

1. **Google Cloud SDK** installed and configured
2. **Project ID**: `gen-lang-client-0329024102`
3. **Region**: `us-central1`
4. **Required APIs enabled**:
   - Cloud Run API
   - Cloud Build API
   - Artifact Registry API
   - Secret Manager API
   - Cloud SQL Admin API

## Files

| File | Description |
|------|-------------|
| `Dockerfile.cloudrun` | Multi-stage Docker build with UV package manager |
| `env.production` | Production environment variables reference |
| `README.md` | This file |

## Deployment Steps

### 1. Initial Setup (One-time)

```bash
# Enable required APIs
gcloud services enable \
    run.googleapis.com \
    cloudbuild.googleapis.com \
    artifactregistry.googleapis.com \
    secretmanager.googleapis.com \
    sqladmin.googleapis.com

# Create Artifact Registry repository
gcloud artifacts repositories create mcp-repo \
    --repository-format=docker \
    --location=us-central1 \
    --description="Odiseo MCP Server images"

# Create service account for MCP Server
gcloud iam service-accounts create mcp-server-sa \
    --display-name="MCP Server Service Account"

# Grant necessary roles
gcloud projects add-iam-policy-binding gen-lang-client-0329024102 \
    --member="serviceAccount:mcp-server-sa@gen-lang-client-0329024102.iam.gserviceaccount.com" \
    --role="roles/cloudsql.client"

gcloud projects add-iam-policy-binding gen-lang-client-0329024102 \
    --member="serviceAccount:mcp-server-sa@gen-lang-client-0329024102.iam.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor"

# Create secrets in Secret Manager (if not exist)
echo -n "postgresql://user:pass@host:5432/db" | \
    gcloud secrets create database-url --data-file=-

echo -n "your-google-api-key" | \
    gcloud secrets create google-api-key --data-file=-
```

### 2. Deploy with Cloud Build

```bash
# From the mcp-server directory
gcloud builds submit --config=cloudbuild.yaml
```

### 3. Manual Deployment (Alternative)

```bash
# Build locally
docker build -f deploy/Dockerfile.cloudrun -t mcp-server .

# Tag for Artifact Registry
docker tag mcp-server \
    us-central1-docker.pkg.dev/gen-lang-client-0329024102/mcp-repo/mcp-server:latest

# Push to registry
docker push \
    us-central1-docker.pkg.dev/gen-lang-client-0329024102/mcp-repo/mcp-server:latest

# Deploy to Cloud Run
gcloud run deploy mcp-server \
    --image=us-central1-docker.pkg.dev/gen-lang-client-0329024102/mcp-repo/mcp-server:latest \
    --region=us-central1 \
    --platform=managed \
    --service-account=mcp-server-sa@gen-lang-client-0329024102.iam.gserviceaccount.com \
    --no-allow-unauthenticated \
    --port=8080 \
    --memory=512Mi \
    --set-secrets=DATABASE_URL=database-url:latest,GOOGLE_API_KEY=google-api-key:latest
```

## Security

### IAM Authentication

The service is deployed with `--no-allow-unauthenticated`, meaning all requests must include a valid identity token.

**Invoker permissions granted to:**
- `orchestrator-sa@gen-lang-client-0329024102.iam.gserviceaccount.com` - Main orchestrator service

### Calling the MCP Server

From another Cloud Run service using `internal_service_client.py`:

```python
from internal_service_client import InternalServiceClient

client = InternalServiceClient()
result = await client.call_mcp_service(
    tool="search_products",
    arguments={"query": "laptop gaming", "k": 5}
)
```

## Environment Variables

See `env.production` for the complete list of environment variables.

**Secrets (from Secret Manager):**
- `DATABASE_URL` - PostgreSQL connection string
- `GOOGLE_API_KEY` - Google Gemini API key

## Health Check

```bash
# Get service URL
SERVICE_URL=$(gcloud run services describe mcp-server \
    --region=us-central1 \
    --format='value(status.url)')

# Health check (requires authentication)
curl -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
    "$SERVICE_URL/health"
```

## Troubleshooting

### View Logs
```bash
gcloud run services logs read mcp-server --region=us-central1
```

### Check Service Status
```bash
gcloud run services describe mcp-server --region=us-central1
```

### Test Locally
```bash
# Build and run locally
docker build -f deploy/Dockerfile.cloudrun -t mcp-server .
docker run -p 8080:8080 \
    -e DATABASE_URL="postgresql://user:pass@host:5432/db" \
    -e GOOGLE_API_KEY="your-key" \
    mcp-server
```
