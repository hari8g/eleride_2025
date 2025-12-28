#!/bin/bash
# Fix OTP dev mode by forcing ECS service update
set -euo pipefail

cd "$(dirname "$0")/.."
source env.local || true

export AWS_ACCESS_KEY_ID
export AWS_SECRET_ACCESS_KEY
export AWS_REGION=${AWS_REGION:-ap-south-1}

cd infra/terraform
CLUSTER=$(terraform output -raw ecs_cluster_name 2>/dev/null)
cd ../..

echo "🔧 Fixing OTP Dev Mode..."
echo ""

echo "1. Checking current task definition..."
TASK_DEF=$(aws ecs describe-task-definition --task-definition eleride-platform-api --region "$AWS_REGION" --query 'taskDefinition.taskDefinitionArn' --output text 2>/dev/null)
OTP_MODE=$(aws ecs describe-task-definition --task-definition eleride-platform-api --region "$AWS_REGION" --query 'taskDefinition.containerDefinitions[0].environment[?name==`OTP_DEV_MODE`].value' --output text 2>/dev/null)

echo "   Task Definition: $TASK_DEF"
echo "   OTP_DEV_MODE: $OTP_MODE"
echo ""

if [ "$OTP_MODE" != "true" ]; then
  echo "❌ OTP_DEV_MODE is not set to 'true' in task definition"
  echo "   Run: cd infra/terraform && terraform apply -var='otp_dev_mode=true'"
  exit 1
fi

echo "2. Updating ECS service to use latest task definition..."
UPDATE_RESULT=$(aws ecs update-service \
  --cluster "$CLUSTER" \
  --service eleride-platform-api \
  --region "$AWS_REGION" \
  --task-definition "$TASK_DEF" \
  --force-new-deployment 2>&1)

if echo "$UPDATE_RESULT" | jq -e '.service.serviceName' > /dev/null 2>&1; then
  echo "   ✅ Service update initiated"
  SERVICE_NAME=$(echo "$UPDATE_RESULT" | jq -r '.service.serviceName')
  echo "   Service: $SERVICE_NAME"
else
  echo "   ⚠️  Update command output:"
  echo "$UPDATE_RESULT"
fi

echo ""
echo "3. Waiting 90 seconds for deployment to complete..."
for i in {90..1}; do
  printf "\r   ⏳ %d seconds remaining..." "$i"
  sleep 1
done
printf "\r   ✅ Wait complete                                    \n"

echo ""
echo "4. Testing OTP endpoint..."
OTP_RESPONSE=$(curl -s -X POST "https://api.eleride.co.in/auth/otp/request" \
  -H "Content-Type: application/json" \
  -d '{"phone":"+919999000401"}')

echo "$OTP_RESPONSE" | jq '.'

if echo "$OTP_RESPONSE" | jq -e '.dev_otp' > /dev/null 2>&1; then
  echo ""
  echo "✅ SUCCESS! OTP dev mode is working!"
  echo "   dev_otp is being returned - frontend should work now"
else
  echo ""
  echo "❌ OTP dev mode not yet active"
  echo "   The service may still be deploying. Wait another minute and try:"
  echo "   curl -X POST https://api.eleride.co.in/auth/otp/request -H 'Content-Type: application/json' -d '{\"phone\":\"+919999000401\"}' | jq ."
fi

