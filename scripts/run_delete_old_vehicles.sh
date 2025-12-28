#!/bin/bash
# Script to delete old vehicles from AWS database
# Usage: ./scripts/run_delete_old_vehicles.sh

set -euo pipefail

cd "$(dirname "$0")/.."
source env.local || true

export AWS_ACCESS_KEY_ID
export AWS_SECRET_ACCESS_KEY
export AWS_REGION=${AWS_REGION:-ap-south-1}

echo "🗑️  Deleting old vehicles (pattern: MH12LZ)..."
echo ""

# Get Terraform outputs
cd infra/terraform
DB_ENDPOINT=$(terraform output -raw rds_endpoint 2>/dev/null)
DB_PASSWORD="${TF_VAR_db_password:-ElerideDbPwd_2025!Strong#123}"
CLUSTER=$(terraform output -raw ecs_cluster_name 2>/dev/null)
SUBNET=$(terraform output -json private_subnet_ids 2>/dev/null | jq -r '.[0]')
SG=$(terraform output -raw ecs_security_group_id 2>/dev/null)
PLATFORM_API_ECR=$(terraform output -raw ecr_platform_api_repository_url 2>/dev/null)
cd ../..

echo "📋 Configuration:"
echo "   Cluster: $CLUSTER"
echo "   DB Endpoint: $DB_ENDPOINT"
echo "   Pattern: MH12LZ"
echo ""

# Build and push image if script was added
echo "📦 Ensuring script is in image..."
docker build --platform linux/amd64 -t "${PLATFORM_API_ECR}:latest" -f services/platform-api/Dockerfile . || true
docker push "${PLATFORM_API_ECR}:latest" || true
echo ""

# Run ECS task
echo "🚀 Starting ECS task to delete old vehicles..."
TASK_OUTPUT=$(aws ecs run-task \
  --cluster "$CLUSTER" \
  --task-definition eleride-platform-api \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNET],securityGroups=[$SG],assignPublicIp=DISABLED}" \
  --overrides "{
    \"containerOverrides\": [{
      \"name\": \"platform-api\",
      \"command\": [\"python3\", \"/app/scripts/delete_old_vehicles_migration.py\", \"MH12LZ\"],
      \"environment\": [{
        \"name\": \"DATABASE_URL\",
        \"value\": \"postgresql+psycopg://postgres:${DB_PASSWORD}@${DB_ENDPOINT}:5432/eleride\"
      }]
    }]
  }" \
  --region "$AWS_REGION" 2>&1)

TASK_ARN=$(echo "$TASK_OUTPUT" | jq -r '.tasks[0].taskArn // empty' 2>/dev/null)

if [ -z "$TASK_ARN" ]; then
  echo "❌ Failed to start task:"
  echo "$TASK_OUTPUT"
  exit 1
fi

echo "✅ Task started: $TASK_ARN"
echo ""
echo "⏳ Waiting 25 seconds for task to complete..."
sleep 25

echo ""
echo "📋 Task logs:"
aws logs tail "/aws/ecs/eleride-platform-api" --since 30s --region "$AWS_REGION" 2>&1 | tail -30

echo ""
echo "✅ Check logs above for deletion results"
echo "   If needed, view full logs with:"
echo "   aws logs tail \"/aws/ecs/eleride-platform-api\" --follow --region $AWS_REGION"

