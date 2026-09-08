variable "name" {
  type    = string
  default = "arbiter"
}

variable "environment" {
  type    = string
  default = "staging"
}

variable "region" {
  type    = string
  default = "us-east-1"
}

variable "vpc_id" {
  type = string
}

variable "private_subnet_ids" {
  type = list(string)

  validation {
    condition     = length(var.private_subnet_ids) >= 2
    error_message = "At least two private subnets are required for the Multi-AZ deployment."
  }
}

variable "public_subnet_ids" {
  type = list(string)

  validation {
    condition     = length(var.public_subnet_ids) >= 2
    error_message = "At least two public subnets are required for the internet-facing ALB."
  }
}

variable "container_image" {
  type = string
}

variable "certificate_arn" {
  type = string
}

variable "oidc_issuer" {
  type    = string
  default = ""
}

variable "oidc_audience" {
  type    = string
  default = ""
}

variable "oidc_jwks_url" {
  type    = string
  default = ""
}

variable "db_instance_class" {
  type    = string
  default = "db.t4g.medium"
}

variable "db_allocated_storage" {
  type    = number
  default = 50

  validation {
    condition     = var.db_allocated_storage >= 20
    error_message = "db_allocated_storage must be at least 20 GiB."
  }
}

variable "desired_count" {
  type    = number
  default = 2
}

variable "min_count" {
  type    = number
  default = 2
}

variable "max_count" {
  type    = number
  default = 6

  validation {
    condition     = var.max_count >= 2
    error_message = "max_count must be at least 2."
  }
}

variable "api_key_secret_arn" {
  type        = string
  description = "Secrets Manager secret containing ARBITER_API_KEYS JSON."
}

variable "settlement_signing_secret_arn" {
  type        = string
  description = "Temporary HMAC settlement signer secret; replace with asymmetric KMS/HSM before live settlement."
}

variable "webhook_signing_secret_arn" {
  type        = string
  description = "Webhook signer secret."
}
