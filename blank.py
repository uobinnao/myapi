
set -euo pipefail

DISPLAY_ENV_NAME="preview"
PUBLIC_ACCESS="true"
STACK_PREFIX="preview-pr"

PROJECT_NAME="$(
  python3 -c 'from pathlib import Path; import tomllib; print(tomllib.load(Path("../../pyproject.toml").open("rb"))["project"]["name"])'
)"
PROJECT_SLUG="$(
  printf '%s' "$PROJECT_NAME" |
    tr '[:upper:]' '[:lower:]' |
    sed -E 's/[._]+/-/g; s/[^a-z0-9-]+/-/g; s/^-+//; s/-+$//; s/-{2,}/-/g'
)"

REPO_ROOT="$(cd ../.. && pwd)"
PROJECT_ID="$(
  python3 /home/uobinnao/workspace/github.com/read_project_id/main.py "$REPO_ROOT"
)"
PROJECT_NUMBER="$(
  gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)'
)"

REGION="us-central1"
PULUMI_STATE_BUCKET="${PROJECT_ID}-pulumi-state"

# MUST match GitHub Actions vars.GCP_AR_REPO
ARTIFACT_REGISTRY_REPO="images"

SECRET_NAME="USDA_API_KEY_PREVIEW"
BILLING_ACCOUNT_ID="01BAD1-548502-59B48D"

REMOTE_URL="$(git remote get-url origin)"

GITHUB_REPOSITORY="$(
  printf '%s\n' "$REMOTE_URL" |
    sed -E '
      s#^git@github\.com:##;
      s#^https://github\.com/##;
      s#\.git$##;
    '
)"

WIF_POOL_ID="github"
WIF_PROVIDER_ID="github-oidc"
WIF_PROVIDER="projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${WIF_POOL_ID}/providers/${WIF_PROVIDER_ID}"
WIF_PRINCIPAL_SET="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${WIF_POOL_ID}/attribute.repository/${GITHUB_REPOSITORY}"

DEPLOYER_SA_ID="github-${PROJECT_SLUG}-preview-deployer"
DEPLOYER_SA_EMAIL="${DEPLOYER_SA_ID}@${PROJECT_ID}.iam.gserviceaccount.com"
DEPLOYER_MEMBER="serviceAccount:${DEPLOYER_SA_EMAIL}"

RUNTIME_SA_ID="${PROJECT_SLUG}-preview-runtime"
RUNTIME_SA_EMAIL="${RUNTIME_SA_ID}@${PROJECT_ID}.iam.gserviceaccount.com"

CLOUD_RUN_SERVICE_AGENT="service-${PROJECT_NUMBER}@serverless-robot-prod.iam.gserviceaccount.com"

echo "PROJECT_ID=$PROJECT_ID"
echo "PROJECT_SLUG=$PROJECT_SLUG"
echo "PROJECT_NUMBER=$PROJECT_NUMBER"
echo "REGION=$REGION"
echo "PULUMI_STATE_BUCKET=$PULUMI_STATE_BUCKET"
echo "ARTIFACT_REGISTRY_REPO=$ARTIFACT_REGISTRY_REPO"
echo "DEPLOYER_SA_EMAIL=$DEPLOYER_SA_EMAIL"
echo "RUNTIME_SA_EMAIL=$RUNTIME_SA_EMAIL"
echo "CLOUD_RUN_SERVICE_AGENT=$CLOUD_RUN_SERVICE_AGENT"
echo "GITHUB_REPOSITORY=$GITHUB_REPOSITORY"
echo "WIF_PROVIDER=$WIF_PROVIDER"
echo "PUBLIC_ACCESS=$PUBLIC_ACCESS"
echo "STACK_PREFIX=$STACK_PREFIX"

gcloud config set project "$PROJECT_ID"

# ----------------------------
# Billing
# ----------------------------
gcloud billing projects link "$PROJECT_ID" --billing-account="$BILLING_ACCOUNT_ID"
gcloud beta billing projects describe "$PROJECT_ID"

# ----------------------------
# Budget alert
# ----------------------------
BUDGET_AMOUNT_USD="10"
BUDGET_ALERT_EMAIL="tnkvie@gmail.com"

BUDGET_CHANNEL_DISPLAY_NAME="${PROJECT_SLUG}-${DISPLAY_ENV_NAME}-budget-email"
BUDGET_DISPLAY_NAME="${PROJECT_SLUG}-${DISPLAY_ENV_NAME}-monthly-budget"

gcloud services enable \
  monitoring.googleapis.com \
  billingbudgets.googleapis.com

export PROJECT_ID
export BUDGET_CHANNEL_DISPLAY_NAME

CHANNEL_NAME="$(
  gcloud alpha monitoring channels list \
    --project="$PROJECT_ID" \
    --format=json | python3 -c '
import json, os, sys
want = os.environ["BUDGET_CHANNEL_DISPLAY_NAME"]
for ch in json.load(sys.stdin):
    if ch.get("type") == "email" and ch.get("displayName") == want:
        print(ch["name"])
        break
'
)"

if [ -z "${CHANNEL_NAME}" ]; then
  CHANNEL_NAME="$(
    gcloud alpha monitoring channels create \
      --project="$PROJECT_ID" \
      --display-name="$BUDGET_CHANNEL_DISPLAY_NAME" \
      --type="email" \
      --channel-labels="email_address=${BUDGET_ALERT_EMAIL}" \
      --format="value(name)"
  )"
fi

export BUDGET_DISPLAY_NAME

BUDGET_NAME="$(
  gcloud billing budgets list \
    --billing-account="$BILLING_ACCOUNT_ID" \
    --format=json | python3 -c '
import json, os, sys
want = os.environ["BUDGET_DISPLAY_NAME"]
for budget in json.load(sys.stdin):
    if budget.get("displayName") == want:
        print(budget["name"])
        break
'
)"

if [ -z "${BUDGET_NAME}" ]; then
  gcloud billing budgets create \
    --billing-account="$BILLING_ACCOUNT_ID" \
    --display-name="$BUDGET_DISPLAY_NAME" \
    --budget-amount="${BUDGET_AMOUNT_USD}USD" \
    --filter-projects="projects/${PROJECT_ID}" \
    --threshold-rule="percent=0.5,basis=current-spend" \
    --threshold-rule="percent=0.9,basis=current-spend" \
    --threshold-rule="percent=1.0,basis=current-spend" \
    --threshold-rule="percent=1.0,basis=forecasted-spend" \
    --notifications-rule-monitoring-notification-channels="${CHANNEL_NAME}"
else
  echo "Budget already exists: ${BUDGET_NAME}"
fi

# ----------------------------
# Required APIs
# ----------------------------
gcloud services enable \
  serviceusage.googleapis.com \
  run.googleapis.com \
  secretmanager.googleapis.com \
  artifactregistry.googleapis.com \
  iam.googleapis.com \
  iamcredentials.googleapis.com \
  sts.googleapis.com \
  cloudresourcemanager.googleapis.com \
  compute.googleapis.com

# ----------------------------
# Pulumi backend bucket
# ----------------------------
if ! gcloud storage buckets describe "gs://${PULUMI_STATE_BUCKET}" >/dev/null 2>&1; then
  gcloud storage buckets create "gs://${PULUMI_STATE_BUCKET}" \
    --location="$REGION" \
    --uniform-bucket-level-access
fi

# ----------------------------
# Service accounts
# ----------------------------
if ! gcloud iam service-accounts describe "${DEPLOYER_SA_EMAIL}" >/dev/null 2>&1; then
  gcloud iam service-accounts create "${DEPLOYER_SA_ID}" \
    --display-name="${PROJECT_SLUG} ${STACK} deployer"
fi

if ! gcloud iam service-accounts describe "${RUNTIME_SA_EMAIL}" >/dev/null 2>&1; then
  gcloud iam service-accounts create "${RUNTIME_SA_ID}" \
    --display-name="${PROJECT_SLUG} ${STACK} runtime"
fi

# ----------------------------
# Let GitHub OIDC impersonate the preview deployer SA
# ----------------------------
gcloud iam service-accounts add-iam-policy-binding "$DEPLOYER_SA_EMAIL" \
  --member="$WIF_PRINCIPAL_SET" \
  --role="roles/iam.workloadIdentityUser"

# ----------------------------
# Let the preview deployer use the Pulumi GCS backend
# ----------------------------
gcloud storage buckets add-iam-policy-binding "gs://${PULUMI_STATE_BUCKET}" \
  --member="$DEPLOYER_MEMBER" \
  --role="roles/storage.objectAdmin"

# ----------------------------
# Let the preview deployer manage Cloud Run
# ----------------------------
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="$DEPLOYER_MEMBER" \
  --role="roles/run.admin"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="$DEPLOYER_MEMBER" \
  --role="roles/run.developer"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="$DEPLOYER_MEMBER" \
  --role="roles/compute.viewer"

# ----------------------------
# Let the preview deployer attach the preview runtime SA to Cloud Run
# ----------------------------
gcloud iam service-accounts add-iam-policy-binding "${RUNTIME_SA_EMAIL}" \
  --member="$DEPLOYER_MEMBER" \
  --role="roles/iam.serviceAccountUser"

# ----------------------------
# Artifact Registry repo
# ----------------------------
if ! gcloud artifacts repositories describe "${ARTIFACT_REGISTRY_REPO}" --location="$REGION" >/dev/null 2>&1; then
  gcloud artifacts repositories create "${ARTIFACT_REGISTRY_REPO}" \
    --repository-format=docker \
    --location="$REGION" \
    --description="Docker repo for ${PROJECT_SLUG}"
fi

gcloud artifacts repositories add-iam-policy-binding "${ARTIFACT_REGISTRY_REPO}" \
  --location="$REGION" \
  --member="$DEPLOYER_MEMBER" \
  --role="roles/artifactregistry.reader"

gcloud artifacts repositories add-iam-policy-binding "${ARTIFACT_REGISTRY_REPO}" \
  --location="$REGION" \
  --member="$DEPLOYER_MEMBER" \
  --role="roles/artifactregistry.writer"

gcloud artifacts repositories add-iam-policy-binding "${ARTIFACT_REGISTRY_REPO}" \
  --location="$REGION" \
  --member="serviceAccount:${CLOUD_RUN_SERVICE_AGENT}" \
  --role="roles/artifactregistry.reader"

# ----------------------------
# Secret or rotate
# ----------------------------
read -rsp "USDA API key (preview): " USDA_API_KEY_PREVIEW
echo

if gcloud secrets describe "$SECRET_NAME" >/dev/null 2>&1; then
  printf '%s' "$USDA_API_KEY_PREVIEW" | gcloud secrets versions add "$SECRET_NAME" --data-file=-
else
  printf '%s' "$USDA_API_KEY_PREVIEW" | gcloud secrets create "$SECRET_NAME" --data-file=-
fi

unset USDA_API_KEY_PREVIEW

gcloud secrets add-iam-policy-binding "$SECRET_NAME" \
  --member="serviceAccount:${RUNTIME_SA_EMAIL}" \
  --role="roles/secretmanager.secretAccessor"

# ----------------------------
# Pulumi passphrase
# ----------------------------
read -rsp "Pulumi config passphrase: " PULUMI_CONFIG_PASSPHRASE
echo
export PULUMI_CONFIG_PASSPHRASE

# ----------------------------
# Pulumi backend sanity
# ----------------------------
pulumi login "gs://${PULUMI_STATE_BUCKET}"

# ----------------------------
# Optional sanity checks
# ----------------------------
gcloud services list --enabled
gcloud artifacts repositories describe "${ARTIFACT_REGISTRY_REPO}" --location="$REGION"
gcloud iam service-accounts describe "${DEPLOYER_SA_EMAIL}"
gcloud iam service-accounts describe "${RUNTIME_SA_EMAIL}"
gcloud secrets describe "$SECRET_NAME"

echo
echo "Set this GitHub Actions repo variable:"
echo "GCP_SERVICE_ACCOUNT_PREVIEW=${DEPLOYER_SA_EMAIL}"
echo
echo "Preview runtime service account:"
echo "${RUNTIME_SA_EMAIL}"
echo
echo "Preview Pulumi stacks should be named like:"
echo "${STACK_PREFIX}-<pr-number>"
echo
echo "Example:"
echo "preview-pr-17"
