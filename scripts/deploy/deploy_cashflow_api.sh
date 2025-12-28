#!/bin/bash

set -euo pipefail

# Load environment variables
source env.local

ECR_REPO="312797770645.dkr.ecr.ap-south-1.amazonaws.com/eleride/platform-api"
AWS_REGION="ap-south-1"
CLUSTER_NAME="eleride-cluster"
SERVICE_NAME="eleride-platform-api"

echo "=== Step 1: Building and Pushing Docker Image ==="

echo "ECR Repository: $ECR_REPO"
echo "AWS Region: $AWS_REGION"
echo ""

echo "Logging in to ECR..."
aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "$ECR_REPO"

echo "Building Docker image for linux/amd64 (ECS Fargate compatible)..."
# Build from project root with Dockerfile in services/platform-api
# Use --platform linux/amd64 to ensure compatibility with ECS Fargate (not ARM64)
docker build --platform linux/amd64 -t "${ECR_REPO}:latest" -f services/platform-api/Dockerfile .

echo "Pushing image to ECR..."
docker push "${ECR_REPO}:latest"

echo "✅ Docker image built and pushed to ECR."
echo ""

echo "=== Step 2: Updating ECS Service ==="

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
echo "Test the API after deployment:"
echo "  curl https://api.eleride.co.in/api/data-files"
