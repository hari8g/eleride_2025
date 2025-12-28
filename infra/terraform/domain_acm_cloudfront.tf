resource "aws_acm_certificate" "cloudfront" {
  count    = local.want_custom_domain ? 1 : 0
  provider = aws.use1

  domain_name               = var.root_domain
  subject_alternative_names = ["*.${var.root_domain}"]
  validation_method         = "DNS"

  lifecycle {
    create_before_destroy = true
  }

  tags = merge(local.common_tags, { Name = "${var.name}-acm-cloudfront" })
}

locals {
  # ACM can return duplicate validation options (same CNAME) for apex + wildcard. Dedupe by name|type.
  cloudfront_cert_validation_records = local.want_custom_domain && length(aws_acm_certificate.cloudfront) > 0 ? {
    for k, v in {
      for dvo in aws_acm_certificate.cloudfront[0].domain_validation_options :
      "${dvo.resource_record_name}|${dvo.resource_record_type}" => {
        name  = dvo.resource_record_name
        type  = dvo.resource_record_type
        value = dvo.resource_record_value
      }...
    } : k => v[0]
  } : {}
}

resource "aws_route53_record" "cloudfront_cert_validation" {
  # Create validation records early (before enabling aliases) so ACM can validate
  # once the registrar NS points to this hosted zone.
  for_each = (local.want_custom_domain && var.manage_route53) ? local.cloudfront_cert_validation_records : {}

  zone_id = aws_route53_zone.primary[0].zone_id
  name    = each.value.name
  type    = each.value.type
  ttl     = 60
  records = [each.value.value]

  allow_overwrite = true
}

resource "aws_acm_certificate_validation" "cloudfront" {
  # IMPORTANT:
  # - Step 1 (enable_custom_domains=false): request cert + print DNS records. No validation resource.
  # - Step 2 (enable_custom_domains=true): validate cert (waits for GoDaddy CNAMEs) and then CloudFront aliases can attach.
  count    = local.enable_custom_domain ? 1 : 0
  provider = aws.use1

  certificate_arn         = aws_acm_certificate.cloudfront[0].arn
  # If DNS is managed outside Route53 (e.g., GoDaddy), Terraform won't create the records.
  # Add these CNAME records manually using the outputs, then re-apply.
  validation_record_fqdns = var.manage_route53 ? [for r in aws_route53_record.cloudfront_cert_validation : r.fqdn] : [for r in values(local.cloudfront_cert_validation_records) : r.name]
}


