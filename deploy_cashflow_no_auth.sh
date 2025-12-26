#!/bin/bash

set -euo pipefail

echo "=== Removing Basic Auth from Cashflow Portal ==="
echo ""

cd "$(dirname "$0")"

# Step 1: Apply Terraform changes
echo "Step 1: Applying Terraform changes to remove Basic Auth..."
cd infra/terraform
terraform apply -auto-approve

echo ""
echo "Step 2: Deploying updated frontend files..."
cd ../../apps/cashflow-underwriting-portal

BUCKET=$(cd ../../infra/terraform && terraform output -raw cashflow_underwriting_portal_bucket)
echo "Bucket: $BUCKET"

aws s3 sync . "s3://$BUCKET" \
  --exclude "*.md" \
  --exclude ".git/*" \
  --exclude "node_modules/*" \
  --delete \
  --region ap-south-1

echo ""
echo "Step 3: Invalidating CloudFront cache..."
CF_DIST_ID=$(cd ../../infra/terraform && terraform output -raw cashflow_underwriting_portal_cloudfront_distribution_id)

INVALIDATION_ID=$(aws cloudfront create-invalidation \
  --distribution-id "$CF_DIST_ID" \
  --paths "/*" \
  --region ap-south-1 \
  --query 'Invalidation.Id' \
  --output text)

echo "✅ CloudFront invalidation created: $INVALIDATION_ID"
echo ""
echo "✅✅✅ Deployment Complete! ✅✅✅"
echo ""
echo "The cashflow portal is now publicly accessible at:"
echo "https://cashflow.eleride.co.in"
echo ""
echo "No sign-in required - users can access directly!"

