#!/bin/bash
# deploy.sh - Script to provision infrastructure and deploy the agent using Terraform & ADK CLI

set -e

# Load project configurations
PROJECT_ID=${GOOGLE_CLOUD_PROJECT:-"your-gcp-project-id"}
REGION="us-central1"
SERVICE_ACCOUNT="finsentry-agent-sa@${PROJECT_ID}.iam.gserviceaccount.com"

echo "=========================================================="
echo "🚀 Starting FinSentry IaC Provisioning & Deployment"
echo "=========================================================="

echo "=== Step 1: Provisioning GCP Resources via Terraform (IaC) ==="
# Initialize and apply Terraform directly in the root directory
terraform init
terraform apply \
  -var="project_id=${PROJECT_ID}" \
  -var="region=${REGION}" \
  -var="agent_service_account_email=${SERVICE_ACCOUNT}" \
  -auto-approve

echo "=== Step 2: Deploying Agent using ADK CLI (Agent CLI) ==="
# Deploys the agent directory to GCP Cloud Run using ADK CLI
adk deploy cloud_run \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --service_name="finsentry-agent" \
  --trace_to_cloud \
  --otel_to_cloud \
  .

echo "=========================================================="
echo "🎉 Deployment complete! FinSentry is running on GCP."
echo "=========================================================="
