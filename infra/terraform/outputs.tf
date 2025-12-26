output "aws_region" {
  value = data.aws_region.current.name
}

output "vpc_id" {
  value = aws_vpc.this.id
}

output "alb_dns_name" {
  value = aws_lb.api.dns_name
}

output "api_cloudfront_domain" {
  value = aws_cloudfront_distribution.api.domain_name
}

output "api_cloudfront_distribution_id" {
  value = aws_cloudfront_distribution.api.id
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

output "fleet_portal_bucket" {
  value = module.fleet_portal_site.bucket_name
}

output "fleet_portal_cloudfront_domain" {
  value = module.fleet_portal_site.cloudfront_domain_name
}

output "maintenance_tech_bucket" {
  value = module.maintenance_tech_site.bucket_name
}

output "maintenance_tech_cloudfront_domain" {
  value = module.maintenance_tech_site.cloudfront_domain_name
}

output "financing_portal_bucket" {
  value = module.financing_portal_site.bucket_name
}

output "financing_portal_cloudfront_domain" {
  value = module.financing_portal_site.cloudfront_domain_name
}

output "matchmaking_portal_bucket" {
  value = module.matchmaking_portal_site.bucket_name
}

output "matchmaking_portal_cloudfront_domain" {
  value = module.matchmaking_portal_site.cloudfront_domain_name
}

output "cashflow_underwriting_portal_bucket" {
  value = module.cashflow_underwriting_portal_site.bucket_name
}

output "cashflow_underwriting_portal_cloudfront_domain" {
  value = module.cashflow_underwriting_portal_site.cloudfront_domain_name
}

output "cashflow_underwriting_portal_distribution_id" {
  value = module.cashflow_underwriting_portal_site.cloudfront_distribution_id
}

output "route53_zone_name_servers" {
  value       = try(aws_route53_zone.primary[0].name_servers, null)
  description = "Set these as NS records at your domain registrar for eleride.co.in"
}

output "cloudfront_acm_dns_validation_records" {
  description = "If manage_route53=false, add these DNS records in your DNS provider (e.g., GoDaddy) to validate the CloudFront ACM cert."
  value = local.want_custom_domain ? [
    for r in values(local.cloudfront_cert_validation_records) : {
      name  = r.name
      type  = r.type
      value = r.value
    }
  ] : []
}

output "custom_domain_cname_targets" {
  description = "If manage_route53=false, create these CNAMEs in your DNS provider to point subdomains to CloudFront."
  value = local.want_custom_domain ? {
    (local.domain_rider)      = module.rider_app_site.cloudfront_domain_name
    (local.domain_fleet)      = module.fleet_portal_site.cloudfront_domain_name
    (local.domain_maint)      = module.maintenance_tech_site.cloudfront_domain_name
    (local.domain_financing)  = module.financing_portal_site.cloudfront_domain_name
    (local.domain_matchmaker) = module.matchmaking_portal_site.cloudfront_domain_name
    (local.domain_cashflow)   = module.cashflow_underwriting_portal_site.cloudfront_domain_name
    (local.domain_api)        = aws_cloudfront_distribution.api.domain_name
  } : {}
}

output "custom_domains" {
  value = local.enable_custom_domain ? {
    api       = local.domain_api
    rider     = local.domain_rider
    fleet     = local.domain_fleet
    maint     = local.domain_maint
    financing = local.domain_financing
    match     = local.domain_matchmaker
    cashflow  = local.domain_cashflow
  } : {}
}


