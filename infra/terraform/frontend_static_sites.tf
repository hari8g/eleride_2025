module "rider_app_site" {
  source                 = "./modules/static_site"
  name                   = "${var.name}-rider-app"
  tags                   = local.common_tags
  viewer_protocol_policy = "redirect-to-https"
  aliases                = local.enable_custom_domain && local.domain_rider != null ? [local.domain_rider] : []
  acm_certificate_arn    = local.enable_custom_domain ? aws_acm_certificate_validation.cloudfront[0].certificate_arn : ""
}

module "fleet_portal_site" {
  source                 = "./modules/static_site"
  name                   = "${var.name}-fleet-portal"
  tags                   = local.common_tags
  viewer_protocol_policy = "redirect-to-https"
  aliases                = local.enable_custom_domain && local.domain_fleet != null ? [local.domain_fleet] : []
  acm_certificate_arn    = local.enable_custom_domain ? aws_acm_certificate_validation.cloudfront[0].certificate_arn : ""
}

module "maintenance_tech_site" {
  source                 = "./modules/static_site"
  name                   = "${var.name}-maintenance-tech"
  tags                   = local.common_tags
  viewer_protocol_policy = "redirect-to-https"
  aliases                = local.enable_custom_domain && local.domain_maint != null ? [local.domain_maint] : []
  acm_certificate_arn    = local.enable_custom_domain ? aws_acm_certificate_validation.cloudfront[0].certificate_arn : ""
}

module "financing_portal_site" {
  source                 = "./modules/static_site"
  name                   = "${var.name}-financing-portal"
  tags                   = local.common_tags
  viewer_protocol_policy = "redirect-to-https"
  aliases                = local.enable_custom_domain && local.domain_financing != null ? [local.domain_financing] : []
  acm_certificate_arn    = local.enable_custom_domain ? aws_acm_certificate_validation.cloudfront[0].certificate_arn : ""
}

module "matchmaking_portal_site" {
  source                 = "./modules/static_site"
  name                   = "${var.name}-matchmaking-portal"
  tags                   = local.common_tags
  viewer_protocol_policy = "redirect-to-https"
  aliases                = local.enable_custom_domain && local.domain_matchmaker != null ? [local.domain_matchmaker] : []
  acm_certificate_arn    = local.enable_custom_domain ? aws_acm_certificate_validation.cloudfront[0].certificate_arn : ""
}

module "cashflow_underwriting_portal_site" {
  source                 = "./modules/static_site"
  name                   = "${var.name}-cashflow-underwriting-portal"
  tags                   = local.common_tags
  viewer_protocol_policy = "redirect-to-https"
  aliases                = local.enable_custom_domain && local.domain_cashflow != null ? [local.domain_cashflow] : []
  acm_certificate_arn    = local.enable_custom_domain ? aws_acm_certificate_validation.cloudfront[0].certificate_arn : ""

  # Basic auth disabled - portal is now publicly accessible
  basic_auth_enabled  = false
  basic_auth_user     = ""
  basic_auth_password = ""
}

locals {
  frontend_cloudfront_domains = [
    module.rider_app_site.cloudfront_domain_name,
    module.fleet_portal_site.cloudfront_domain_name,
    module.maintenance_tech_site.cloudfront_domain_name,
    module.financing_portal_site.cloudfront_domain_name,
    module.matchmaking_portal_site.cloudfront_domain_name,
    module.cashflow_underwriting_portal_site.cloudfront_domain_name,
  ]

  frontend_custom_domains = compact([
    local.enable_custom_domain ? local.domain_rider : null,
    local.enable_custom_domain ? local.domain_fleet : null,
    local.enable_custom_domain ? local.domain_maint : null,
    local.enable_custom_domain ? local.domain_financing : null,
    local.enable_custom_domain ? local.domain_matchmaker : null,
    local.enable_custom_domain ? local.domain_cashflow : null,
  ])

  frontend_cors_origins = flatten([
    for d in local.frontend_cloudfront_domains : [
      "https://${d}",
      "http://${d}",
    ]
  ])

  cors_allow_origins_effective = var.cors_allow_origins != "" ? var.cors_allow_origins : join(
    ",",
    concat(
      local.frontend_cors_origins,
      [for d in local.frontend_custom_domains : "https://${d}"]
    )
  )
}


