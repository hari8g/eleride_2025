output "aws_region" {
  value = data.aws_region.current.name
}

output "vpc_id" {
  value = aws_vpc.this.id
}

output "alb_dns_name" {
  value = aws_lb.api.dns_name
}

output "ecr_platform_api_repository_url" {
  value = aws_ecr_repository.platform_api.repository_url
}

output "rds_endpoint" {
  value = aws_db_instance.postgres.address
}

output "rider_app_bucket" {
  value = module.rider_app_site.bucket_name
}

output "rider_app_cloudfront_domain" {
  value = module.rider_app_site.cloudfront_domain_name
}


