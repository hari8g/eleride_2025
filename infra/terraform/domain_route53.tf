locals {
  want_custom_domain   = var.root_domain != ""
  enable_custom_domain = var.root_domain != "" && var.enable_custom_domains

  # Subdomain map (you can adjust names anytime).
  domain_api        = local.want_custom_domain ? "api.${var.root_domain}" : null
  domain_rider      = local.want_custom_domain ? "rider.${var.root_domain}" : null
  domain_fleet      = local.want_custom_domain ? "fleet.${var.root_domain}" : null
  domain_maint      = local.want_custom_domain ? "maint.${var.root_domain}" : null
  domain_financing  = local.want_custom_domain ? "financing.${var.root_domain}" : null
  domain_matchmaker = local.want_custom_domain ? "match.${var.root_domain}" : null
  domain_cashflow   = local.want_custom_domain ? "cashflow.${var.root_domain}" : null
}

resource "aws_route53_zone" "primary" {
  # Create the hosted zone as soon as root_domain is set (even before aliases are enabled),
  # so DNS can be pointed at the correct NS first.
  count = (local.want_custom_domain && var.manage_route53) ? 1 : 0
  name  = var.root_domain
  tags  = merge(local.common_tags, { Name = "${var.name}-zone-${var.root_domain}" })
}


