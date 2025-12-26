provider "aws" {
  region = var.aws_region
}

// CloudFront ACM certificates (if/when used) must be in us-east-1.
// Keep this alias so Terraform can manage/clean up any legacy state objects created there.
provider "aws" {
  alias  = "use1"
  region = "us-east-1"
}

data "aws_caller_identity" "current" {}

data "aws_region" "current" {}

data "aws_availability_zones" "available" {
  state = "available"
}


