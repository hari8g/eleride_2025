resource "aws_cloudfront_distribution" "api" {
  enabled = true
  comment = "${var.name}-api (CloudFront -> ALB)"
  aliases = local.enable_custom_domain && local.domain_api != null ? [local.domain_api] : []

  origin {
    domain_name = aws_lb.api.dns_name
    origin_id   = "alb-${aws_lb.api.id}"

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "http-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  default_cache_behavior {
    target_origin_id       = "alb-${aws_lb.api.id}"
    viewer_protocol_policy = "redirect-to-https"

    allowed_methods = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    cached_methods  = ["GET", "HEAD", "OPTIONS"]
    compress        = true

    # Legacy forwarding mode: this is the simplest way to forward Authorization headers
    # for bearer token auth without custom domains / ALB TLS.
    min_ttl     = 0
    default_ttl = 0
    max_ttl     = 0

    forwarded_values {
      query_string = true
      headers      = ["*"]
      cookies {
        forward = "none"
      }
    }
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = local.enable_custom_domain ? false : true
    acm_certificate_arn            = local.enable_custom_domain ? aws_acm_certificate_validation.cloudfront[0].certificate_arn : null
    ssl_support_method             = local.enable_custom_domain ? "sni-only" : null
    minimum_protocol_version       = local.enable_custom_domain ? "TLSv1.2_2021" : "TLSv1"
  }
}


