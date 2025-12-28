#!/bin/bash
# Quick script to check Terraform apply status

cd /Users/harig/Desktop/Eleride/infra/terraform
source ../../env.local
export AWS_ACCESS_KEY_ID
export AWS_SECRET_ACCESS_KEY
export AWS_REGION=${AWS_REGION:-ap-south-1}
export TF_VAR_jwt_secret="${JWT_SECRET:-your-jwt-secret-here}"
export TF_VAR_db_password="${DB_PASSWORD:-ElerideDbPwd_2025!Strong#123}"

echo "=== Terraform Apply Status ==="
echo ""
echo "Check log file: tail -f /tmp/terraform-apply-bg.log"
echo ""
echo "=== Current CloudFront Distribution Status ==="
echo ""

for DIST_ID in E19731VYKID56X E3TPH5CWFN7UAE E3FQJ3I0ZOG49S; do
  DIST_NAME=$(aws cloudfront list-distributions --region ap-south-1 --query "DistributionList.Items[?Id=='$DIST_ID'].Comment" --output text 2>/dev/null | head -1)
  ALIASES=$(aws cloudfront get-distribution-config --id "$DIST_ID" --region ap-south-1 --query 'DistributionConfig.Aliases.Items' --output text 2>/dev/null)
  STATUS=$(aws cloudfront get-distribution-config --id "$DIST_ID" --region ap-south-1 --query 'DistributionConfig.Status' --output text 2>/dev/null)
  
  echo "Distribution: $DIST_ID ($DIST_NAME)"
  echo "  Status: $STATUS"
  echo "  Aliases: ${ALIASES:-None}"
  echo ""
done

echo "=== To check if apply completed ==="
echo "Run: cd /Users/harig/Desktop/Eleride/infra/terraform && terraform output custom_domains"

