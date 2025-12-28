#!/bin/bash

set -euo pipefail

# This script builds and pushes all services to AWS ECR, then runs database migrations
# Usage: ./scripts/deploy/deploy_all_to_aws.sh [dev|prod]

ENV_NAME=${1:-local}
ENV_FILE="./env.${ENV_NAME}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Error: Environment file $ENV_FILE not found."
  echo "Please create it based on env.example and fill in AWS credentials."
  exit 1
fi

source "$ENV_FILE"

echo "🚀 Deploying all services to AWS (${ENV_NAME})..."
echo ""

# Get Terraform outputs
cd infra/terraform
echo "📋 Getting Terraform outputs..."
TF_OUTPUTS=$(terraform output -json)
PLATFORM_API_ECR=$(echo "$TF_OUTPUTS" | jq -r '.ecr_platform_api_repository_url.value')
CONTRACT_SERVICE_ECR=$(echo "$TF_OUTPUTS" | jq -r '.ecr_contract_service_repository_url.value')
RDS_ENDPOINT=$(echo "$TF_OUTPUTS" | jq -r '.rds_endpoint.value')
AWS_REGION=$(echo "$TF_OUTPUTS" | jq -r '.aws_region.value')
cd ../..

echo "ECR Repositories:"
echo "  Platform API: $PLATFORM_API_ECR"
echo "  Contract Service: $CONTRACT_SERVICE_ECR"
echo ""

# Login to ECR
echo "🔐 Logging in to ECR..."
aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "$PLATFORM_API_ECR"
aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "$CONTRACT_SERVICE_ECR"

# Build and push Platform API
echo ""
echo "📦 Building and pushing Platform API..."
docker build --platform linux/amd64 -t "${PLATFORM_API_ECR}:latest" -f services/platform-api/Dockerfile .
docker push "${PLATFORM_API_ECR}:latest"
echo "✅ Platform API pushed"

# Build and push Contract Service
echo ""
echo "📦 Building and pushing Contract Service..."
docker build --platform linux/amd64 -t "${CONTRACT_SERVICE_ECR}:latest" -f services/contract-service/Dockerfile services/contract-service
docker push "${CONTRACT_SERVICE_ECR}:latest"
echo "✅ Contract Service pushed"

# Run database migrations
echo ""
echo "🔄 Running database migrations..."
docker run --rm --platform linux/amd64 \
  -e DATABASE_URL="postgresql+psycopg://${DB_USERNAME}:${DB_PASSWORD}@${RDS_ENDPOINT}:5432/${DB_NAME}" \
  "${PLATFORM_API_ECR}:latest" \
  python -c "
from sqlalchemy import create_engine, text
import os

db_url = os.getenv('DATABASE_URL')
engine = create_engine(db_url)

with engine.connect() as conn:
    # Add new columns if they don't exist
    conn.execute(text('''
        ALTER TABLE riders 
        ADD COLUMN IF NOT EXISTS signed_contract_url VARCHAR,
        ADD COLUMN IF NOT EXISTS signature_image TEXT,
        ADD COLUMN IF NOT EXISTS signed_at TIMESTAMP WITH TIME ZONE;
    '''))
    conn.commit()
    print('✅ Database migration completed')
"

# Force ECS service updates
echo ""
echo "🔄 Forcing ECS service updates..."
CLUSTER_NAME="${NAME}-cluster"

aws ecs update-service \
  --cluster "$CLUSTER_NAME" \
  --service "${NAME}-platform-api" \
  --region "$AWS_REGION" \
  --force-new-deployment

aws ecs update-service \
  --cluster "$CLUSTER_NAME" \
  --service "${NAME}-contract-service" \
  --region "$AWS_REGION" \
  --force-new-deployment

echo ""
echo "✅ Deployment initiated!"
echo ""
echo "⏳ Services are being updated. This may take 5-10 minutes."
echo "Monitor deployment with:"
echo "  aws ecs describe-services --cluster \"$CLUSTER_NAME\" --services \"${NAME}-platform-api\" \"${NAME}-contract-service\" --region \"$AWS_REGION\""

