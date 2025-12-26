variable "name" {
  type        = string
  description = "Name prefix (used in bucket + distribution)."
}

variable "tags" {
  type        = map(string)
  description = "Common tags."
  default     = {}
}

variable "index_document" {
  type    = string
  default = "index.html"
}

variable "viewer_protocol_policy" {
  type        = string
  description = "CloudFront viewer protocol policy (allow-all | redirect-to-https | https-only)."
  default     = "redirect-to-https"
}

variable "aliases" {
  type        = list(string)
  description = "Optional custom domain aliases for CloudFront."
  default     = []
}

variable "acm_certificate_arn" {
  type        = string
  description = "Optional ACM certificate ARN (must be us-east-1 for CloudFront). If empty, uses default CloudFront certificate."
  default     = ""
}

variable "basic_auth_enabled" {
  type        = bool
  description = "If true, attach a CloudFront Function to enforce Basic Auth on all requests (lightweight restriction)."
  default     = false
}

variable "basic_auth_user" {
  type        = string
  description = "Basic auth username (only used if basic_auth_enabled=true)."
  default     = ""
}

variable "basic_auth_password" {
  type        = string
  description = "Basic auth password (only used if basic_auth_enabled=true)."
  default     = ""
  sensitive   = true
}


