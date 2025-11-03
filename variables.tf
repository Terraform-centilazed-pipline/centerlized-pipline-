# S3 Management Deployment Variables

variable "accounts" {
  description = "Account configurations for multi-account deployment"
  type = map(object({
    id           = string
    account_id   = string
    account_name = string
    environment  = string
    regions      = list(string)
  }))
  default = {}
}

variable "aws_regions" {
  description = "AWS regions mapping"
  type = map(object({
    name = string
    code = string
  }))
  default = {
    "use1" = {
      name = "us-east-1"
      code = "use1"
    }
    "usw2" = {
      name = "us-west-2"
      code = "usw2"
    }
    "ew1" = {
      name = "eu-west-1"
      code = "ew1"
    }
  }
}

variable "s3_buckets" {
  description = "S3 bucket configurations"
  type = map(object({
    bucket_name   = string
    account_key   = string
    region_code   = string
    force_destroy = optional(bool, false)

    # Versioning
    versioning_enabled = optional(bool, null)

    # Encryption
    encryption = optional(object({
      sse_algorithm      = string
      kms_master_key_id  = string
      bucket_key_enabled = optional(bool, true)
    }), null)

    # Bucket Policy
    bucket_policy      = optional(string, null)
    bucket_policy_file = optional(string, null)

    tags = optional(map(string), {})
  }))
  default = {}

  validation {
    condition = alltrue([
      for _, v in var.s3_buckets : v.bucket_policy == null || v.bucket_policy_file == null
    ])
    error_message = "Each S3 bucket can have either bucket_policy OR bucket_policy_file specified, but not both."
  }

  validation {
    condition = alltrue([
      for _, v in var.s3_buckets : v.encryption == null ? true : length(trimspace(v.encryption.kms_master_key_id)) > 0
    ])
    error_message = "Each encrypted S3 bucket must include a non-empty kms_master_key_id."
  }
}

variable "assume_role_name" {
  description = "IAM role name to assume for cross-account access"
  type        = string
  default     = "TerraformExecutionRole"
}

variable "terraform_session_name" {
  description = "Unique session name for Terraform execution (auto-injected by controller: team-environment-deployment)"
  type        = string
  default     = "terraform-deployment-session"
}

variable "common_tags" {
  description = "Common tags to be applied to all resources"
  type        = map(string)
  default = {
    ManagedBy   = "terraform"
    Project     = "S3-Management"
    Environment = "dev"
    Owner       = "DevOps-Team"
  }
}

variable "yaml_config_file" {
  description = "Path to YAML configuration file for S3 buckets (alternative to s3_buckets variable)"
  type        = string
  default     = ""
}

variable "kms_key_id" {
  description = "KMS key ID for S3 bucket encryption (existing custom key)"
  type        = string
  default     = ""
}

variable "iam_role_name" {
  description = "IAM role name for S3 and KMS access"
  type        = string
  default     = ""
}

variable "update_kms_policy" {
  description = "Whether to update the KMS key policy to allow S3 and IAM role access"
  type        = bool
  default     = false
}

# =============================================================================
# KMS Module Variables
# =============================================================================

variable "kms_keys" {
  description = "Map of KMS keys to create"
  type = map(object({
    description              = optional(string)
    key_usage                = optional(string, "ENCRYPT_DECRYPT")
    key_spec                 = optional(string, "SYMMETRIC_DEFAULT")
    multi_region             = optional(bool, false)
    deletion_window_in_days  = optional(number, 30)
    enable_key_rotation      = optional(bool, true)
    policy                   = optional(string)
    policy_file              = optional(string)
    policy_content           = optional(string)
    aliases                  = optional(list(string), [])
    grants                   = optional(list(object({
      name               = string
      grantee_principal  = string
      operations         = list(string)
      retiring_principal = optional(string)
      constraints = optional(object({
        encryption_context_equals = optional(map(string))
        encryption_context_subset = optional(map(string))
      }))
    })), [])
    tags = optional(map(string), {})
  }))
  default = {}
}

# =============================================================================
# IAM Module Variables
# =============================================================================

variable "iam_users" {
  description = "Map of IAM users to create"
  type = map(object({
    name                    = string
    path                    = optional(string, "/")
    permissions_boundary    = optional(string)
    force_destroy           = optional(bool, false)
    create_access_key       = optional(bool, false)
    create_login_profile    = optional(bool, false)
    password_reset_required = optional(bool, true)
    password_length         = optional(number, 20)
    pgp_key                 = optional(string)
    policies                = optional(map(string), {})
    tags                    = optional(map(string), {})
  }))
  default = {}
}

variable "iam_roles" {
  description = "Map of IAM roles to create"
  type = map(object({
    name                 = string
    path                 = optional(string, "/")
    description          = optional(string)
    assume_role_policy   = string
    permissions_boundary = optional(string)
    max_session_duration = optional(number, 3600)
    policies             = optional(map(string), {})
    inline_policies      = optional(map(string), {})
    tags                 = optional(map(string), {})
  }))
  default = {}
}

variable "iam_policies" {
  description = "Map of IAM policies to create"
  type = map(object({
    name        = string
    path        = optional(string, "/")
    description = optional(string)
    policy      = string
    tags        = optional(map(string), {})
  }))
  default = {}
}

