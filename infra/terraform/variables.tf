variable "name" {
  description = "Prefix for all resources."
  type        = string
  default     = "eleride"
}

variable "aws_region" {
  description = "AWS region."
  type        = string
  default     = "ap-south-1"
}

variable "tags" {
  description = "Common tags."
  type        = map(string)
  default     = {}
}

variable "vpc_cidr" {
  description = "VPC CIDR."
  type        = string
  default     = "10.40.0.0/16"
}

variable "az_count" {
  description = "Number of AZs to use (2 recommended)."
  type        = number
  default     = 2
}

variable "platform_api_container_port" {
  description = "Container port (FastAPI listens on 8000 in Dockerfile)."
  type        = number
  default     = 8000
}

variable "platform_api_cpu" {
  description = "ECS task CPU units."
  type        = number
  default     = 512
}

variable "platform_api_memory" {
  description = "ECS task memory (MiB)."
  type        = number
  default     = 1024
}

variable "platform_api_desired_count" {
  description = "ECS service desired task count."
  type        = number
  default     = 2
}

variable "platform_api_env" {
  description = "ENV value passed to platform-api (prod/staging/dev)."
  type        = string
  default     = "prod"
}

variable "otp_dev_mode" {
  description = "If true, enable OTP dev mode in platform-api even when ENV=prod (returns dev_otp; no SMS required)."
  type        = bool
  default     = false
}

variable "root_domain" {
  description = "Root domain to use for custom domains (e.g., eleride.co.in)."
  type        = string
  default     = ""
}

variable "enable_custom_domains" {
  description = "If true, attach custom domains (aliases) to CloudFront and require a validated ACM cert. Use false for step 1 (request cert + print DNS records)."
  type        = bool
  default     = false
}

variable "manage_route53" {
  description = "If true, Terraform manages Route53 hosted zone + records for root_domain. If false (e.g., GoDaddy DNS), Terraform will not create Route53 resources."
  type        = bool
  default     = false
}

variable "jwt_secret" {
  description = "JWT secret for platform-api (set via tfvars; do not hardcode)."
  type        = string
  sensitive   = true
}

variable "cors_allow_origins" {
  description = "Comma-separated origins for CORS."
  type        = string
  default     = ""
}

variable "cashflow_basic_auth_password" {
  description = "Basic auth password for cashflow underwriting portal (MVP restriction)."
  type        = string
  default     = ""
  sensitive   = true
}

variable "msg91_api_key" {
  description = "MSG91 API key (optional)."
  type        = string
  default     = ""
  sensitive   = true
}

variable "msg91_sender_id" {
  description = "MSG91 sender id (optional)."
  type        = string
  default     = ""
}

variable "msg91_otp_template_id" {
  description = "MSG91 SMS DLT template id (optional)."
  type        = string
  default     = ""
}

variable "msg91_whatsapp_flow_id" {
  description = "MSG91 WhatsApp flow id (optional)."
  type        = string
  default     = ""
}

variable "msg91_whatsapp_otp_var" {
  description = "MSG91 WhatsApp Flow variable key for OTP."
  type        = string
  default     = "OTP"
}

variable "msg91_otp_channel_order" {
  description = "Channel order for OTP delivery."
  type        = string
  default     = "whatsapp,sms"
}

variable "db_name" {
  description = "RDS database name."
  type        = string
  default     = "eleride"
}

variable "db_username" {
  description = "RDS master username."
  type        = string
  default     = "postgres"
}

variable "db_password" {
  description = "RDS master password."
  type        = string
  sensitive   = true
}

variable "db_instance_class" {
  description = "RDS instance class."
  type        = string
  default     = "db.t4g.micro"
}

variable "db_allocated_storage_gb" {
  description = "RDS allocated storage (GB)."
  type        = number
  default     = 20
}


