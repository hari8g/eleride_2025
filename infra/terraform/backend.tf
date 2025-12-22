terraform {
  backend "s3" {
    bucket         = "eleride-terraform-state-dev-31279777064"
    key            = "eleride/dev/terraform.tfstate"
    region         = "ap-south-1"
    dynamodb_table = "eleride-terraform-lock-dev"
    encrypt        = true
  }
}


