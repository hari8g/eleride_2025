#!/bin/bash
# Check the status of custom domain configuration

set -e

source "$(dirname "$0")/../env.local" || exit 1
export AWS_ACCESS_KEY_ID
export AWS_SECRET_ACCESS_KEY
export AWS_REGION=${AWS_REGION:-ap-south-1}

ZONE_ID="Z04194373OH5ILZFOQM2L"
CERT_ARN="arn:aws:acm:us-east-1:312797770645:certificate/02bc8017-e22c-4faa-8d4d-76e3fb535f95"

echo "=== Custom Domain Configuration Status ==="
echo ""

# Check certificate validation
echo "📜 ACM Certificate Status:"
CERT_STATUS=$(aws acm describe-certificate --certificate-arn "$CERT_ARN" --region us-east-1 --query 'Certificate.Status' --output text 2>/dev/null)
echo "  Status: $CERT_STATUS"
if [ "$CERT_STATUS" = "ISSUED" ]; then
  echo "  ✅ Certificate is validated!"
else
  echo "  ⏳ Certificate validation in progress..."
fi
echo ""

# Check validation records in all zones
echo "📋 Route53 Validation Records:"
VALIDATION_RECORDS=""
for CHECK_ZONE_ID in Z04194373OH5ILZFOQM2L Z03898093KWGAQM91WAC8; do
  ZONE_RECORDS=$(aws route53 list-resource-record-sets --hosted-zone-id "$CHECK_ZONE_ID" --region ap-south-1 --query "ResourceRecordSets[?Type=='CNAME' && (contains(Name, 'acm-validations') || contains(Name, '_270b5dabb3c0f2bab43391496598f1d2'))]" --output json 2>/dev/null)
  if [ "$(echo "$ZONE_RECORDS" | jq 'length' 2>/dev/null)" -gt 0 ]; then
    VALIDATION_RECORDS="$ZONE_RECORDS"
    echo "  ✅ Validation records found in zone $CHECK_ZONE_ID"
    echo "$ZONE_RECORDS" | jq -r '.[] | "  - \(.Name) -> \(.ResourceRecords[0].Value)"'
    break
  fi
done
if [ -z "$VALIDATION_RECORDS" ] || [ "$(echo "$VALIDATION_RECORDS" | jq 'length' 2>/dev/null)" -eq 0 ]; then
  echo "  ⏳ No validation records yet (Terraform may be creating them)"
fi
echo ""

# Check CloudFront distributions
echo "🌐 CloudFront Distribution Status:"
for DIST_ID in E19731VYKID56X E3TPH5CWFN7UAE E3FQJ3I0ZOG49S; do
  DIST_NAME=$(aws cloudfront list-distributions --region ap-south-1 --query "DistributionList.Items[?Id=='$DIST_ID'].Comment" --output text 2>/dev/null | head -1)
  ALIASES_JSON=$(aws cloudfront get-distribution-config --id "$DIST_ID" --region ap-south-1 --query 'DistributionConfig.Aliases.Items' --output json 2>/dev/null || echo "[]")
  ALIASES=$(echo "$ALIASES_JSON" | jq -r 'if type == "array" and length > 0 then .[] else empty end' 2>/dev/null || echo "")
  CERT_CF=$(aws cloudfront get-distribution-config --id "$DIST_ID" --region ap-south-1 --query 'DistributionConfig.ViewerCertificate.CertificateSource' --output text 2>/dev/null || echo "unknown")
  
  echo "  $DIST_ID ($DIST_NAME):"
  if [ -n "$ALIASES" ]; then
    echo "    ✅ Aliases: $ALIASES"
  else
    echo "    ⏳ No aliases configured yet"
  fi
  echo "    Certificate: $CERT_CF"
done
echo ""

# Check Route53 A records
echo "🔗 Route53 A Records:"
A_RECORDS=$(aws route53 list-resource-record-sets --hosted-zone-id "$ZONE_ID" --region ap-south-1 --query "ResourceRecordSets[?Type=='A' && (Name=='fleet.eleride.co.in.' || Name=='api.eleride.co.in.' || Name=='rider.eleride.co.in.')].{Name:Name,Value:AliasTarget.DNSName}" --output json 2>/dev/null)
if [ -n "$A_RECORDS" ] && [ "$(echo "$A_RECORDS" | jq 'length')" -gt 0 ]; then
  echo "$A_RECORDS" | jq -r '.[] | "  ✅ \(.Name) -> \(.Value)"'
else
  echo "  ⏳ No A records found"
fi
echo ""

# Terraform status
echo "🔧 Terraform Apply Status:"
if [ -f /tmp/terraform-apply-final.log ]; then
  if tail -5 /tmp/terraform-apply-final.log 2>/dev/null | grep -q "Apply complete"; then
    echo "  ✅ Terraform apply completed"
  elif ps aux | grep -v grep | grep -q "terraform apply"; then
    echo "  ⏳ Terraform apply is running..."
  else
    echo "  ⚠️  Terraform apply may have completed or failed. Check /tmp/terraform-apply-final.log"
  fi
else
  echo "  ⏳ Terraform apply not started or log not found"
fi
echo ""

echo "=== Summary ==="
if [ "$CERT_STATUS" = "ISSUED" ]; then
  echo "✅ Certificate is validated"
else
  echo "⏳ Waiting for certificate validation (usually takes 5-10 minutes after DNS records are created)"
fi
echo ""
echo "Once certificate is ISSUED and CloudFront distributions are updated, the custom domains will work!"
echo ""
echo "To check again, run: ./scripts/check-custom-domain-status.sh"

