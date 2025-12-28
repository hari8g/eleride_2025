#!/bin/bash
# Deploy frontend apps to S3 and invalidate CloudFront cache
set -euo pipefail

ENV_NAME=${1:-local}
ENV_FILE="./env.${ENV_NAME}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Error: Environment file $ENV_FILE not found."
  exit 1
fi

source "$ENV_FILE"

echo "🚀 Deploying frontend apps to AWS..."
echo ""

# Get Terraform outputs
cd infra/terraform
AWS_REGION=$(terraform output -raw aws_region 2>/dev/null || echo "ap-south-1")

# Get bucket names and CloudFront distribution IDs
RIDER_BUCKET=$(terraform output -raw rider_app_bucket 2>/dev/null)
FLEET_BUCKET=$(terraform output -raw fleet_portal_bucket 2>/dev/null)

RIDER_CF_ID=$(terraform output -raw rider_app_cloudfront_distribution_id 2>/dev/null || echo "")
FLEET_CF_ID=$(terraform output -raw fleet_portal_cloudfront_distribution_id 2>/dev/null || echo "")

cd ../..

echo "Buckets:"
echo "  Rider App: $RIDER_BUCKET"
echo "  Fleet Portal: $FLEET_BUCKET"
echo ""

# Build and deploy Rider App
if [ -n "$RIDER_BUCKET" ] && [ "$RIDER_BUCKET" != "null" ]; then
  echo "📦 Building Rider App..."
  cd apps/rider-app
  
  # Install dependencies if needed
  if [ ! -d "node_modules" ]; then
    echo "Installing dependencies..."
    npm install
  fi
  
  # Build for production
  npm run build
  
  echo "📤 Uploading Rider App to S3..."
  aws s3 sync dist/ "s3://${RIDER_BUCKET}/" --delete --region "$AWS_REGION"
  echo "✅ Rider App uploaded"
  
  # Invalidate CloudFront cache
  if [ -n "$RIDER_CF_ID" ] && [ "$RIDER_CF_ID" != "null" ]; then
    echo "🔄 Invalidating CloudFront cache..."
    INVALIDATION_ID=$(aws cloudfront create-invalidation \
      --distribution-id "$RIDER_CF_ID" \
      --paths "/*" \
      --query 'Invalidation.Id' \
      --output text)
    echo "✅ CloudFront invalidation created: $INVALIDATION_ID"
  fi
  
  cd ../..
fi

# Build and deploy Fleet Portal
if [ -n "$FLEET_BUCKET" ] && [ "$FLEET_BUCKET" != "null" ]; then
  echo ""
  echo "📦 Building Fleet Portal..."
  cd apps/fleet-portal
  
  # Install dependencies if needed
  if [ ! -d "node_modules" ]; then
    echo "Installing dependencies..."
    npm install
  fi
  
  # Build for production
  npm run build
  
  echo "📤 Uploading Fleet Portal to S3..."
  aws s3 sync dist/ "s3://${FLEET_BUCKET}/" --delete --region "$AWS_REGION"
  echo "✅ Fleet Portal uploaded"
  
  # Invalidate CloudFront cache
  if [ -n "$FLEET_CF_ID" ] && [ "$FLEET_CF_ID" != "null" ]; then
    echo "🔄 Invalidating CloudFront cache..."
    INVALIDATION_ID=$(aws cloudfront create-invalidation \
      --distribution-id "$FLEET_CF_ID" \
      --paths "/*" \
      --query 'Invalidation.Id' \
      --output text)
    echo "✅ CloudFront invalidation created: $INVALIDATION_ID"
  fi
  
  cd ../..
fi

echo ""
echo "✅ Frontend deployment complete!"

