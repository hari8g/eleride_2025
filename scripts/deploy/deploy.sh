#!/bin/bash

# Multi-Environment Deployment Script
# Usage: ./scripts/deploy/deploy.sh [dev|prod]
# Example: ./scripts/deploy/deploy.sh dev
# Example: ./scripts/deploy/deploy.sh prod

set -euo pipefail

# Validate environment argument
ENVIRONMENT="${1:-}"
if [[ ! "$ENVIRONMENT" =~ ^(dev|prod)$ ]]; then
    echo "❌ Error: Invalid environment. Must be 'dev' or 'prod'"
    echo ""
    echo "Usage: $0 [dev|prod]"
    echo "Example: $0 dev"
    echo "Example: $0 prod"
    exit 1
fi

# Determine environment file
ENV_FILE="env.${ENVIRONMENT}"
if [ ! -f "$ENV_FILE" ]; then
    echo "❌ Error: Environment file '$ENV_FILE' not found"
    echo "Please create $ENV_FILE based on env.example"
    exit 1
fi

# Load environment variables
echo "📋 Loading configuration from $ENV_FILE..."
source "$ENV_FILE"

# Export AWS credentials for this deployment
export AWS_ACCESS_KEY_ID
export AWS_SECRET_ACCESS_KEY
export AWS_REGION

# Verify AWS credentials
echo "🔐 Verifying AWS credentials..."
if ! aws sts get-caller-identity --region "$AWS_REGION" > /dev/null 2>&1; then
    echo "❌ Error: Failed to authenticate with AWS"
    echo "Please check your AWS credentials in $ENV_FILE"
    exit 1
fi

AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text --region "$AWS_REGION")
echo "✅ Authenticated as AWS Account: $AWS_ACCOUNT_ID"
echo "📍 Environment: $ENVIRONMENT (uppercase: ${ENVIRONMENT^^})"
echo ""

# Set AWS resources based on environment
ECR_REPO="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/eleride/platform-api"
CLUSTER_NAME_VAR="CLUSTER_NAME"
SERVICE_NAME_VAR="SERVICE_NAME"

# Use environment-specific values if set, otherwise use defaults with suffix
CLUSTER_NAME="${!CLUSTER_NAME_VAR:-eleride-cluster-${ENVIRONMENT}}"
SERVICE_NAME="${!SERVICE_NAME_VAR:-eleride-platform-api-${ENVIRONMENT}}"

echo "=== Deployment Configuration ==="
echo "Environment: $ENVIRONMENT"
echo "AWS Account: $AWS_ACCOUNT_ID"
echo "AWS Region: $AWS_REGION"
echo "ECR Repository: $ECR_REPO"
echo "ECS Cluster: $CLUSTER_NAME"
echo "ECS Service: $SERVICE_NAME"
echo ""

# Confirm before deploying to production
if [ "$ENVIRONMENT" == "prod" ]; then
    echo "⚠️  WARNING: You are about to deploy to PRODUCTION!"
    read -p "Type 'yes' to confirm: " confirmation
    if [ "$confirmation" != "yes" ]; then
        echo "❌ Deployment cancelled"
        exit 1
    fi
    echo ""
fi

echo "=== Step 1: Building and Pushing Docker Image ==="
echo ""

echo "Logging in to ECR..."
aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "$ECR_REPO"

echo "Building Docker image for linux/amd64 (ECS Fargate compatible)..."
# Build from project root with Dockerfile in services/platform-api
# Use --platform linux/amd64 to ensure compatibility with ECS Fargate (not ARM64)
docker build --platform linux/amd64 -t "${ECR_REPO}:latest" -f services/platform-api/Dockerfile .
docker tag "${ECR_REPO}:latest" "${ECR_REPO}:${ENVIRONMENT}-$(date +%Y%m%d-%H%M%S)"

echo "Pushing image to ECR..."
docker push "${ECR_REPO}:latest"
docker push "${ECR_REPO}:${ENVIRONMENT}-$(date +%Y%m%d-%H%M%S)"

echo "✅ Docker image built and pushed to ECR."
echo ""

echo "=== Step 2: Updating ECS Service ==="
echo ""

# Check if cluster exists
if ! aws ecs describe-clusters --clusters "$CLUSTER_NAME" --region "$AWS_REGION" --query 'clusters[0].status' --output text 2>/dev/null | grep -q "ACTIVE"; then
    echo "❌ Error: ECS Cluster '$CLUSTER_NAME' not found or not active"
    echo "Please create the cluster first or check the cluster name in $ENV_FILE"
    exit 1
fi

# Check if service exists
if ! aws ecs describe-services --cluster "$CLUSTER_NAME" --services "$SERVICE_NAME" --region "$AWS_REGION" --query 'services[0].status' --output text 2>/dev/null | grep -q "ACTIVE"; then
    echo "❌ Error: ECS Service '$SERVICE_NAME' not found or not active in cluster '$CLUSTER_NAME'"
    echo "Please create the service first or check the service name in $ENV_FILE"
    exit 1
fi

echo "Forcing new ECS deployment..."
aws ecs update-service \
  --cluster "$CLUSTER_NAME" \
  --service "$SERVICE_NAME" \
  --region "$AWS_REGION" \
  --force-new-deployment

echo "✅ Deployment initiated!"
echo ""
echo "⏳ Deployment in progress. This may take 5-10 minutes."
echo "   The new tasks need to:"
echo "   - Pull the new image"
echo "   - Start containers"
echo "   - Pass health checks"
echo ""

if [ -n "${API_URL:-}" ]; then
    echo "Test the API after deployment:"
    echo "  curl ${API_URL}/api/data-files"
else
    echo "Monitor deployment status:"
    echo "  aws ecs describe-services --cluster $CLUSTER_NAME --services $SERVICE_NAME --region $AWS_REGION"
fi

echo ""
echo "✅ Deployment script completed successfully!"

