# 🚀 Deployment Setup for DoobieLogic

This guide sets up automatic deployment to `ops.doobielogic.io` on every push to main.

## Prerequisites

- Google Cloud Project with billing enabled
- Workload Identity Federation configured (for GitHub Actions)
- Cloud Run, Artifact Registry, Secret Manager enabled

## Step 1: Set Up Workload Identity Federation

```bash
gcloud iam workload-identity-pools create "github" \
  --project=$PROJECT_ID \
  --location=global \
  --display-name="GitHub Actions"

# Get the pool resource name
WORKLOAD_IDENTITY_POOL_ID=$(gcloud iam workload-identity-pools describe "github" \
  --project=$PROJECT_ID \
  --location=global \
  --format='value(name)')

gcloud iam workload-identity-pools providers create-oidc "github" \
  --project=$PROJECT_ID \
  --location=global \
  --workload-identity-pool="github" \
  --display-name="GitHub" \
  --attribute-mapping="google.subject=sub,attribute.aud=aud,attribute.repository=repository" \
  --issuer-uri="https://token.actions.githubusercontent.com"
```

## Step 2: Create Service Account

```bash
gcloud iam service-accounts create buyer-dash-deployer \
  --project=$PROJECT_ID \
  --display-name="DoobieLogic Deployer"

gcloud iam service-accounts add-iam-policy-binding \
  buyer-dash-deployer@$PROJECT_ID.iam.gserviceaccount.com \
  --project=$PROJECT_ID \
  --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/$WORKLOAD_IDENTITY_POOL_ID/attribute.repository/MAVet710/buyer-dashboard"
```

## Step 3: Grant Service Account Permissions

```bash
# Cloud Run deploy
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member=serviceAccount:buyer-dash-deployer@$PROJECT_ID.iam.gserviceaccount.com \
  --role=roles/run.admin

# Artifact Registry push
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member=serviceAccount:buyer-dash-deployer@$PROJECT_ID.iam.gserviceaccount.com \
  --role=roles/artifactregistry.writer

# Secret Manager access
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member=serviceAccount:buyer-dash-deployer@$PROJECT_ID.iam.gserviceaccount.com \
  --role=roles/secretmanager.secretAccessor

# Service account passthrough
gcloud iam service-accounts add-iam-policy-binding \
  buyer-dash-deployer@$PROJECT_ID.iam.gserviceaccount.com \
  --project=$PROJECT_ID \
  --role=roles/iam.serviceAccountUser \
  --member=serviceAccount:buyer-dash-deployer@$PROJECT_ID.iam.gserviceaccount.com
```

## Step 4: Create Secrets in Secret Manager

```bash
# Database connection
echo -n "postgresql://user:pass@host/db" | \
  gcloud secrets create buyer-dash-database-url \
  --data-file=- --project=$PROJECT_ID

# Supabase config
echo -n "https://your-project.supabase.co" | \
  gcloud secrets create buyer-dash-supabase-url \
  --data-file=- --project=$PROJECT_ID

echo -n "https://your-project.supabase.co/auth/v1/.well-known/jwks.json" | \
  gcloud secrets create buyer-dash-supabase-jwks-url \
  --data-file=- --project=$PROJECT_ID

echo -n "your-service-role-key" | \
  gcloud secrets create buyer-dash-supabase-service-role \
  --data-file=- --project=$PROJECT_ID

# Integration encryption key
echo -n "your-encryption-key" | \
  gcloud secrets create buyer-dash-integration-encryption-key \
  --data-file=- --project=$PROJECT_ID
```

## Step 5: Add GitHub Secrets

Go to: **Settings → Secrets and variables → Actions**

Add these secrets:

| Secret | Value |
|--------|-------|
| `GCP_PROJECT_ID` | Your Google Cloud Project ID |
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | `projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/github/providers/github` |
| `GCP_SERVICE_ACCOUNT` | `buyer-dash-deployer@PROJECT_ID.iam.gserviceaccount.com` |
| `VITE_SUPABASE_URL` | Your Supabase project URL |
| `VITE_SUPABASE_PUBLISHABLE_KEY` | Your Supabase publishable key |

## Step 6: Set Up Cloud Run Services

Create the services first (deployment will update them):

```bash
# Create API service
gcloud run create buyer-dash-api \
  --region us-east1 \
  --image gcr.io/cloudrun/hello \
  --allow-unauthenticated \
  --port 8080 \
  --platform managed \
  --project=$PROJECT_ID

# Create web service
gcloud run create buyer-dash-web \
  --region us-east1 \
  --image gcr.io/cloudrun/hello \
  --allow-unauthenticated \
  --port 8080 \
  --platform managed \
  --project=$PROJECT_ID
```

## Step 7: Configure DNS

Point these domains to your Cloud Run services:

- `ops.doobielogic.io` → buyer-dash-web Cloud Run URL
- `api.doobielogic.io` → buyer-dash-api Cloud Run URL

Use Cloud Run domain mapping or update DNS records to point to the Cloud Run URLs.

## Step 8: Test Deployment

Push a commit to main:

```bash
git commit --allow-empty -m "Test deployment"
git push origin main
```

Watch the deployment in GitHub Actions → Deploy workflow.

## Monitoring

### Check deployment logs:
```bash
gcloud run services describe buyer-dash-api --region us-east1
gcloud run services describe buyer-dash-web --region us-east1
```

### View Cloud Run logs:
```bash
gcloud run logs read buyer-dash-api --region us-east1 --limit 50
gcloud run logs read buyer-dash-web --region us-east1 --limit 50
```

### Check Cloud Build:
```bash
gcloud builds log --limit=50
```

## Troubleshooting

### Deployment fails with auth error:
- Verify service account has correct roles
- Check Workload Identity Pool configuration

### Images won't push:
- Verify Artifact Registry repository exists
- Check service account has `artifactregistry.writer` role

### Environment variables not set:
- Verify secrets exist in Secret Manager
- Check service account can access secrets

### DNS not resolving:
- Wait 24-48 hours for DNS propagation
- Verify Cloud Run domain mapping is correct

---

**Done!** Every push to `main` now automatically deploys to `ops.doobielogic.io` and `api.doobielogic.io`.
