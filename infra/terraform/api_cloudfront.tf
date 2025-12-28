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
    # OPTIONS and POST should NOT be cached - CORS preflight and API requests must reach origin
    cached_methods  = ["GET", "HEAD"]
    compress        = true

    # Legacy forwarding mode: this is the simplest way to forward Authorization headers
    # for bearer token auth without custom domains / ALB TLS.
    # TTL set to 0 to prevent caching errors
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

  # Custom error response to prevent caching of 5xx errors
  custom_error_response {
    error_code            = 503
    error_caching_min_ttl = 0
  }

  custom_error_response {
    error_code            = 502
    error_caching_min_ttl = 0
  }

  custom_error_response {
    error_code            = 504
    error_caching_min_ttl = 0
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


