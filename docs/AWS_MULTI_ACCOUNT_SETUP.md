# AWS Multi-Account Setup Guide

This guide explains how to set up separate AWS accounts for development and production environments to avoid interruptions and ensure isolation.

## Overview

**Benefits of Separate AWS Accounts:**
- ✅ **Isolation**: Dev and prod resources are completely separated
- ✅ **Security**: Reduced risk of accidental production changes
- ✅ **Cost Management**: Easier to track and control costs per environment
- ✅ **Compliance**: Better audit trails and access control
- ✅ **No Interruptions**: Dev deployments don't affect production

## Step 1: Create AWS Accounts

### Option A: AWS Organizations (Recommended)

1. **Create AWS Organizations Account**
   - Sign in to AWS as root user
   - Go to AWS Organizations console
   - Create organization and enable all features

2. **Create Dev Account**
   - In Organizations, click "Add account" → "Create account"
   - Account name: `eleride-dev`
   - Email: `aws-eleride-dev@yourcompany.com`
   - Note the account ID

3. **Create Prod Account**
   - Repeat for production: `eleride-prod`
   - Email: `aws-eleride-prod@yourcompany.com`
   - Note the account ID

### Option B: Separate Standalone Accounts

1. Create two separate AWS accounts:
   - Development account (e.g., `eleride-dev@email.com`)
   - Production account (e.g., `eleride-prod@email.com`)

## Step 2: Set Up IAM Users

### For Development Account

1. **Create IAM User for CI/CD**
   ```bash
   # In AWS Console → IAM → Users → Add user
   User name: eleride-deployer-dev
   Access type: Programmatic access
   ```

2. **Attach Policies**
   - `AmazonEC2ContainerRegistryFullAccess` (for ECR)
   - `AmazonECS_FullAccess` (for ECS)
   - `CloudWatchLogsFullAccess` (for logs)
   - Custom policy for RDS/ElastiCache if needed

3. **Save Credentials**
   - Access Key ID
   - Secret Access Key

### For Production Account

1. **Create IAM User for CI/CD**
   ```bash
   User name: eleride-deployer-prod
   Access type: Programmatic access
   ```

2. **Attach Policies** (same as dev)

3. **Add MFA Requirement** (recommended for production)
   - Enable MFA for the user
   - Require MFA for sensitive operations

4. **Save Credentials**

## Step 3: Configure Environment Files

### Create `env.dev`

```bash
cp env.example env.dev
```

Edit `env.dev` with your DEV account details:
```bash
AWS_ACCESS_KEY_ID=YOUR_DEV_AWS_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY=YOUR_DEV_AWS_SECRET_ACCESS_KEY
AWS_REGION=ap-south-1
AWS_ACCOUNT_ID=123456789012  # Your DEV account ID
CLUSTER_NAME=eleride-cluster-dev
SERVICE_NAME=eleride-platform-api-dev
```

### Create `env.prod`

```bash
cp env.example env.prod
```

Edit `env.prod` with your PROD account details:
```bash
AWS_ACCESS_KEY_ID=YOUR_PROD_AWS_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY=YOUR_PROD_AWS_SECRET_ACCESS_KEY
AWS_REGION=ap-south-1
AWS_ACCOUNT_ID=987654321098  # Your PROD account ID
CLUSTER_NAME=eleride-cluster-prod
SERVICE_NAME=eleride-platform-api-prod
```

⚠️ **Security Note**: Never commit `env.dev` or `env.prod` to git! They're already in `.gitignore`.

## Step 4: Set Up Infrastructure in Each Account

### Development Account

1. **Create ECR Repository**
   ```bash
   aws ecr create-repository \
     --repository-name eleride/platform-api \
     --region ap-south-1 \
     --profile dev
   ```

2. **Create ECS Cluster**
   ```bash
   aws ecs create-cluster \
     --cluster-name eleride-cluster-dev \
     --region ap-south-1 \
     --profile dev
   ```

3. **Set up RDS/VPC/etc.** (using Terraform or AWS Console)

### Production Account

Repeat the same steps with production values:
- Cluster: `eleride-cluster-prod`
- Service: `eleride-platform-api-prod`
- Use production-grade security settings

## Step 5: Deploy to Environments

### Deploy to Development

```bash
./scripts/deploy/deploy.sh dev
```

### Deploy to Production

```bash
./scripts/deploy/deploy.sh prod
```

The script will:
- Load the correct environment file (`env.dev` or `env.prod`)
- Verify AWS credentials
- Build and push Docker image to the correct ECR
- Deploy to the correct ECS cluster/service

## Step 6: AWS CLI Profiles (Optional but Recommended)

Configure AWS CLI profiles for easier switching:

```bash
# Configure dev profile
aws configure --profile eleride-dev
# Enter DEV account credentials

# Configure prod profile
aws configure --profile eleride-prod
# Enter PROD account credentials
```

Then update deployment script to use profiles:
```bash
aws ecs describe-services --cluster ... --profile eleride-dev
```

## Best Practices

### 1. Environment Isolation

- ✅ Use separate AWS accounts
- ✅ Use separate VPCs and subnets
- ✅ Use separate databases (RDS instances)
- ✅ Use separate S3 buckets with different prefixes

### 2. Access Control

- ✅ Use IAM roles with least privilege
- ✅ Enable MFA for production access
- ✅ Use separate IAM users for each environment
- ✅ Rotate credentials regularly

### 3. Cost Management

- ✅ Enable Cost Allocation Tags
- ✅ Set up billing alerts per account
- ✅ Use AWS Budgets to monitor costs

### 4. Monitoring

- ✅ Separate CloudWatch log groups per environment
- ✅ Use different SNS topics for alerts
- ✅ Set up separate dashboards

### 5. CI/CD Integration

Update your CI/CD pipeline to:
- Deploy to dev on every commit to `develop` branch
- Deploy to prod only on `main` branch after manual approval
- Use different AWS credentials per environment

Example GitHub Actions:
```yaml
jobs:
  deploy-dev:
    if: github.ref == 'refs/heads/develop'
    steps:
      - name: Deploy to Dev
        env:
          AWS_ACCESS_KEY_ID: ${{ secrets.DEV_AWS_ACCESS_KEY_ID }}
          AWS_SECRET_ACCESS_KEY: ${{ secrets.DEV_AWS_SECRET_ACCESS_KEY }}
        run: ./scripts/deploy/deploy.sh dev

  deploy-prod:
    if: github.ref == 'refs/heads/main'
    needs: [test]
    steps:
      - name: Deploy to Prod
        env:
          AWS_ACCESS_KEY_ID: ${{ secrets.PROD_AWS_ACCESS_KEY_ID }}
          AWS_SECRET_ACCESS_KEY: ${{ secrets.PROD_AWS_SECRET_ACCESS_KEY }}
        run: ./scripts/deploy/deploy.sh prod
```

## Troubleshooting

### "Cluster not found" Error

Make sure:
1. You're using the correct AWS account credentials
2. The cluster exists in that account
3. The cluster name matches your `env.{environment}` file

### "Access Denied" Error

Check:
1. IAM user has necessary permissions
2. Using correct credentials for the environment
3. MFA required (for production) is configured

### Switch Between Accounts Quickly

Create helper scripts:
```bash
# scripts/use-dev.sh
export $(cat env.dev | xargs)
export AWS_PROFILE=eleride-dev  # if using profiles

# scripts/use-prod.sh
export $(cat env.prod | xargs)
export AWS_PROFILE=eleride-prod
```

## Next Steps

1. ✅ Set up AWS Organizations or create accounts
2. ✅ Configure IAM users and policies
3. ✅ Create `env.dev` and `env.prod` files
4. ✅ Set up infrastructure in each account
5. ✅ Test deployments to both environments
6. ✅ Update CI/CD pipeline to use multi-environment setup

## Security Checklist

- [ ] Separate AWS accounts created
- [ ] IAM users created with least privilege
- [ ] MFA enabled for production access
- [ ] `env.dev` and `env.prod` files created (not committed)
- [ ] Environment variables properly secured
- [ ] Access logging enabled (CloudTrail)
- [ ] Billing alerts configured per account

