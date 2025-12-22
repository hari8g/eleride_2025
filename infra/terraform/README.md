## AWS Terraform baseline (Eleride)

This folder deploys a production-friendly baseline:
- VPC (2 AZ), public + private subnets, NAT per AZ
- ECS Fargate service for `services/platform-api` behind an ALB
- ECR repo for images
- RDS Postgres in private subnets
- S3 + CloudFront module for static frontend hosting (repeat per app)
- CloudWatch log group + IAM task roles

### Prereqs
- Terraform `>= 1.6`
- AWS credentials configured (`aws configure` or environment vars)

### 1) Configure remote state (recommended)
Create an S3 bucket + DynamoDB lock table for Terraform state, then add a `backend.tf`:

```hcl
terraform {
  backend "s3" {
    bucket         = "YOUR_TF_STATE_BUCKET"
    key            = "eleride/terraform.tfstate"
    region         = "ap-south-1"
    dynamodb_table = "YOUR_TF_LOCK_TABLE"
    encrypt        = true
  }
}
```

### 2) Create `terraform.tfvars`
Example:

```hcl
name           = "eleride"
aws_region     = "ap-south-1"

jwt_secret     = "CHANGE_ME_LONG_RANDOM"
db_password    = "CHANGE_ME_LONG_RANDOM"

platform_api_env    = "prod"
cors_allow_origins  = "https://YOUR_CF_DOMAIN,https://YOUR_OTHER_DOMAIN"

# Optional MSG91
msg91_api_key          = ""
msg91_sender_id        = ""
msg91_otp_template_id  = ""
msg91_whatsapp_flow_id = ""
```

### 3) Deploy infra

```bash
cd infra/terraform
terraform init
terraform plan
terraform apply
```

### 4) Build + push platform-api image to ECR
After apply, Terraform prints `ecr_platform_api_repository_url`.

```bash
AWS_REGION=ap-south-1
ECR_REPO="$(terraform -chdir=infra/terraform output -raw ecr_platform_api_repository_url)"

aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "${ECR_REPO%/*}"

docker build -t platform-api:latest services/platform-api
docker tag platform-api:latest "$ECR_REPO:latest"
docker push "$ECR_REPO:latest"
```

Then force a new ECS deployment (via console or CLI):

```bash
aws ecs update-service \
  --cluster eleride-cluster \
  --service eleride-platform-api \
  --force-new-deployment \
  --region "$AWS_REGION"
```

### 5) Deploy a frontend to S3 + CloudFront
Terraform creates an S3 bucket + CloudFront distribution (one example module is enabled).

Build:

```bash
cd apps/rider-app
npm ci
VITE_API_BASE_URL="http://$(terraform -chdir=infra/terraform output -raw alb_dns_name)" npm run build
```

Upload:

```bash
BUCKET="$(terraform -chdir=infra/terraform output -raw rider_app_bucket)"
aws s3 sync dist "s3://$BUCKET" --delete
```

Invalidate CloudFront:

```bash
aws cloudfront create-invalidation \
  --distribution-id "$(terraform -chdir=infra/terraform output -raw rider_app_cloudfront_domain | cut -d. -f1)" \
  --paths "/*"
```

> Tip: You can enable more frontend modules in `frontend_static_sites.tf`.


