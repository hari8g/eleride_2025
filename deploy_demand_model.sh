#!/bin/bash
set -e

echo "=== Deploying Demand Prediction Model ==="
echo ""

cd "$(dirname "$0")"
source env.local

ECR_REPO="312797770645.dkr.ecr.ap-south-1.amazonaws.com/eleride/platform-api"
AWS_REGION="ap-south-1"
CLUSTER_NAME="eleride-cluster"
SERVICE_NAME="eleride-platform-api"

# Check Docker
if ! docker ps > /dev/null 2>&1; then
  echo "❌ Docker is not running. Please start Docker Desktop first."
  exit 1
fi

echo "✅ Docker is running"
echo ""

# Step 1: Login to ECR
echo "Step 1: Logging in to ECR..."
aws ecr get-login-password --region $AWS_REGION | \
  docker login --username AWS --password-stdin $ECR_REPO

# Step 2: Build image
echo ""
echo "Step 2: Building Docker image (this may take a few minutes)..."
cd services/platform-api
docker build -t ${ECR_REPO}:latest .

# Step 3: Push image
echo ""
echo "Step 3: Pushing image to ECR (this may take a few minutes)..."
docker push ${ECR_REPO}:latest

# Step 4: Update ECS service
echo ""
echo "Step 4: Updating ECS service..."
cd ../../infra/terraform
aws ecs update-service \
  --cluster "$CLUSTER_NAME" \
  --service "$SERVICE_NAME" \
  --region ap-south-1 \
  --force-new-deployment \
  --output table

echo ""
echo "✅✅✅ Deployment initiated! ✅✅✅"
echo ""
echo "The new image is being deployed. This will take 5-10 minutes."
echo ""
echo "Monitor progress:"
echo "  AWS Console → ECS → Clusters → $CLUSTER_NAME → Services → $SERVICE_NAME"
echo ""
echo "Once deployment completes, test:"
echo "  curl https://api.eleride.co.in/admin/demand/status"
echo ""
echo "To import data:"
echo "  curl -X POST https://api.eleride.co.in/admin/demand/import-from-docs \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{\"filename\":\"ELERIDE IBBN Payout Dec 25 WEEK 1 (1).xlsx\",\"sheet_name\":\"Sheet1\"}'"

