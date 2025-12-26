resource "aws_route53_record" "api" {
  count   = (local.enable_custom_domain && var.manage_route53) ? 1 : 0
  zone_id = aws_route53_zone.primary[0].zone_id
  name    = local.domain_api
  type    = "A"

  alias {
    name                   = aws_cloudfront_distribution.api.domain_name
    zone_id                = aws_cloudfront_distribution.api.hosted_zone_id
    evaluate_target_health = false
  }
}

resource "aws_route53_record" "api_aaaa" {
  count   = (local.enable_custom_domain && var.manage_route53) ? 1 : 0
  zone_id = aws_route53_zone.primary[0].zone_id
  name    = local.domain_api
  type    = "AAAA"

  alias {
    name                   = aws_cloudfront_distribution.api.domain_name
    zone_id                = aws_cloudfront_distribution.api.hosted_zone_id
    evaluate_target_health = false
  }
}

locals {
  frontend_alias_targets = (local.enable_custom_domain && var.manage_route53) ? {
    (local.domain_rider)      = module.rider_app_site.cloudfront_distribution_id
    (local.domain_fleet)      = module.fleet_portal_site.cloudfront_distribution_id
    (local.domain_maint)      = module.maintenance_tech_site.cloudfront_distribution_id
    (local.domain_financing)  = module.financing_portal_site.cloudfront_distribution_id
    (local.domain_matchmaker) = module.matchmaking_portal_site.cloudfront_distribution_id
    (local.domain_cashflow)   = module.cashflow_underwriting_portal_site.cloudfront_distribution_id
  } : {}
}

data "aws_cloudfront_distribution" "frontend" {
  for_each = local.frontend_alias_targets
  id       = each.value
}

resource "aws_route53_record" "frontend_a" {
  for_each = local.frontend_alias_targets
  zone_id  = aws_route53_zone.primary[0].zone_id
  name     = each.key
  type     = "A"

  alias {
    name                   = data.aws_cloudfront_distribution.frontend[each.key].domain_name
    zone_id                = data.aws_cloudfront_distribution.frontend[each.key].hosted_zone_id
    evaluate_target_health = false
  }
}

resource "aws_route53_record" "frontend_aaaa" {
  for_each = local.frontend_alias_targets
  zone_id  = aws_route53_zone.primary[0].zone_id
  name     = each.key
  type     = "AAAA"

  alias {
    name                   = data.aws_cloudfront_distribution.frontend[each.key].domain_name
    zone_id                = data.aws_cloudfront_distribution.frontend[each.key].hosted_zone_id
    evaluate_target_health = false
  }
}


