#!/bin/bash
# Test script to verify contract generation is working
set -euo pipefail

cd "$(dirname "$0")/.."
source env.local || true

export AWS_ACCESS_KEY_ID
export AWS_SECRET_ACCESS_KEY
export AWS_REGION=${AWS_REGION:-ap-south-1}

echo "=== Testing Contract Generation Flow ==="
echo ""

# Get API URL
API_URL="https://api.eleride.co.in"

# Test OTP and get token
echo "1. Authenticating..."
OTP_RESP=$(curl -s -X POST "${API_URL}/auth/otp/request" \
  -H "Content-Type: application/json" \
  -d '{"phone":"+919999000401"}')

REQUEST_ID=$(echo "$OTP_RESP" | jq -r '.request_id')
DEV_OTP=$(echo "$OTP_RESP" | jq -r '.dev_otp // empty')

if [ -z "$DEV_OTP" ]; then
  echo "❌ No dev OTP returned. OTP_DEV_MODE might not be enabled."
  exit 1
fi

echo "   Request ID: $REQUEST_ID"
echo "   Dev OTP: $DEV_OTP"

TOKEN=$(curl -s -X POST "${API_URL}/auth/otp/verify" \
  -H "Content-Type: application/json" \
  -d "{\"request_id\":\"$REQUEST_ID\",\"otp\":\"$DEV_OTP\"}" | jq -r '.access_token')

if [ -z "$TOKEN" ] || [ "$TOKEN" = "null" ]; then
  echo "❌ Failed to get access token"
  exit 1
fi

echo "   ✅ Authenticated"
echo ""

# Get rider status
echo "2. Getting rider status..."
RIDER_STATUS=$(curl -s -X GET "${API_URL}/riders/status" \
  -H "Authorization: Bearer $TOKEN")

RIDER_ID=$(echo "$RIDER_STATUS" | jq -r '.rider_id')
STATUS=$(echo "$RIDER_STATUS" | jq -r '.status')
CONTRACT_URL=$(echo "$RIDER_STATUS" | jq -r '.contract_url // empty')
SIGNED_CONTRACT_URL=$(echo "$RIDER_STATUS" | jq -r '.signed_contract_url // empty')

echo "   Rider ID: $RIDER_ID"
echo "   Status: $STATUS"
echo "   Contract URL: ${CONTRACT_URL:-'Not set'}"
echo "   Signed Contract URL: ${SIGNED_CONTRACT_URL:-'Not set'}"
echo ""

# Get supply status
echo "3. Getting supply status..."
SUPPLY_STATUS=$(curl -s -X GET "${API_URL}/supply/status" \
  -H "Authorization: Bearer $TOKEN")

PICKUP_VERIFIED=$(echo "$SUPPLY_STATUS" | jq -r '.pickup_verified_at // empty')
SUPPLY_CONTRACT_URL=$(echo "$SUPPLY_STATUS" | jq -r '.contract_url // empty')
STAGE_CODE=$(echo "$SUPPLY_STATUS" | jq -r '.stage.code // empty')

echo "   Pickup Verified At: ${PICKUP_VERIFIED:-'Not verified'}"
echo "   Stage Code: $STAGE_CODE"
echo "   Contract URL in supply status: ${SUPPLY_CONTRACT_URL:-'Not set'}"
echo ""

if [ -n "$PICKUP_VERIFIED" ] && [ -z "$SUPPLY_CONTRACT_URL" ]; then
  echo "⚠️  ISSUE FOUND: Pickup is verified but contract_url is not in supply status!"
  echo "   This means contract generation might have failed or not been triggered."
elif [ -n "$SUPPLY_CONTRACT_URL" ]; then
  echo "✅ Contract URL is present: $SUPPLY_CONTRACT_URL"
  echo "   Testing contract URL..."
  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$SUPPLY_CONTRACT_URL")
  if [ "$HTTP_CODE" = "200" ]; then
    echo "   ✅ Contract URL is accessible (HTTP $HTTP_CODE)"
  else
    echo "   ❌ Contract URL returned HTTP $HTTP_CODE"
  fi
fi

echo ""
echo "=== Test Complete ==="

