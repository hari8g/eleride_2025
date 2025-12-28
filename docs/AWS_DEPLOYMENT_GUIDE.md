# AWS Deployment Guide

This guide walks you through deploying all changes to AWS using Terraform.

## Prerequisites

1. AWS CLI configured with appropriate credentials
2. Terraform installed
3. Docker installed and running

## Step 1: Configure AWS Credentials

```bash
# Option 1: Use AWS CLI configure
aws configure

# Option 2: Export environment variables
export AWS_ACCESS_KEY_ID="your-access-key"
export AWS_SECRET_ACCESS_KEY="your-secret-key"
export AWS_REGION="ap-south-1"
```

## Step 2: Initialize and Plan Terraform

```bash
cd infra/terraform

# Initialize Terraform (uses S3 backend)
terraform init

# Review the planned changes
terraform plan
```

## Step 3: Apply Terraform Infrastructure

This will create/update:
- Contract Service ECR repository
- Contract Service ECS task definition and service
- ALB listener rules for contract-service
- Security group updates
- Platform API environment variable updates

```bash
# Apply changes (review output carefully)
terraform apply

# Type 'yes' when prompted
```

## Step 4: Deploy Services

The deployment script will:
1. Build Docker images for both services
2. Push images to ECR
3. Run database migrations
4. Force ECS service updates

```bash
cd ../..

# Make sure you have the environment file configured
# Copy env.prod if needed:
cp env.example env.prod
# Edit env.prod with your values (DB credentials, etc.)

# Deploy everything
./scripts/deploy/deploy_all_to_aws.sh prod
```

## Step 5: Verify Deployment

```bash
# Get cluster name from Terraform outputs
cd infra/terraform
CLUSTER_NAME=$(terraform output -raw cluster_name 2>/dev/null || echo "eleride-cluster")
AWS_REGION=$(terraform output -raw aws_region)

# Check service status
aws ecs describe-services \
  --cluster "$CLUSTER_NAME" \
  --services eleride-platform-api eleride-contract-service \
  --region "$AWS_REGION" \
  --query 'services[*].[serviceName,status,runningCount,desiredCount]' \
  --output table

# Check logs
aws logs tail /ecs/eleride/platform-api --follow --region "$AWS_REGION"
aws logs tail /ecs/eleride/contract-service --follow --region "$AWS_REGION"
```

## Database Migrations

The deployment script automatically runs database migrations to add:
- `signed_contract_url` (VARCHAR)
- `signature_image` (TEXT)  
- `signed_at` (TIMESTAMP WITH TIME ZONE)

If migrations fail, you can run them manually:

```bash
# Get RDS endpoint
RDS_ENDPOINT=$(cd infra/terraform && terraform output -raw rds_endpoint)

# Connect and run migration
psql -h "$RDS_ENDPOINT" -U postgres -d eleride -c "
ALTER TABLE riders 
ADD COLUMN IF NOT EXISTS signed_contract_url VARCHAR,
ADD COLUMN IF NOT EXISTS signature_image TEXT,
ADD COLUMN IF NOT EXISTS signed_at TIMESTAMP WITH TIME ZONE;
"
```

## Troubleshooting

### AWS Credentials Error
If you see "InvalidClientTokenId", configure AWS credentials:
```bash
aws configure
```

### Terraform State Lock
If Terraform is locked, wait a few minutes or manually unlock:
```bash
cd infra/terraform
terraform force-unlock <LOCK_ID>
```

### ECS Service Not Updating
Check service events:
```bash
aws ecs describe-services \
  --cluster eleride-cluster \
  --services eleride-platform-api \
  --region ap-south-1 \
  --query 'services[0].events[:5]'
```

### Database Migration Fails
Ensure RDS security group allows connections from your IP or ECS tasks.

## What Was Deployed

### New Infrastructure
- Contract Service ECR repository
- Contract Service ECS service (Fargate, 256 CPU, 512 MB memory)
- ALB listener rule for `/contract-service/*` and `/contracts/*`
- CloudWatch log groups for contract service

### Updated Infrastructure
- Platform API environment variables:
  - `CONTRACT_SERVICE_URL` - Internal ALB URL
  - `CONTRACT_SERVICE_URL_EXTERNAL` - External CloudFront URL
- ECS security group - Added ingress for contract service port 8000

### Code Changes
- Contract signing feature
- Vehicle VIN support
- Fleet portal pagination
- Database schema updates

## Rollback

If you need to rollback:

```bash
cd infra/terraform
terraform destroy -target=aws_ecs_service.contract_service
terraform destroy -target=aws_ecs_task_definition.contract_service
# Then redeploy previous version
```

