# =============================================================================
# Centralized Terraform Pipeline - Main Configuration
# =============================================================================
# This orchestrates multi-module deployments (S3, KMS, IAM, etc.)
# Modules are sourced from the tf-module repository
# =============================================================================

terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.7"
    }
  }
}

# =============================================================================
# DATA SOURCES
# =============================================================================

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# =============================================================================
# LOCAL VARIABLES - Configuration Processing
# =============================================================================

locals {
  # Load YAML configuration if file is provided, otherwise use variable
  yaml_config = var.yaml_config_file != "" ? yamldecode(file(var.yaml_config_file)) : {}
  
  # ===========================
  # S3 Buckets Configuration
  # ===========================
  merged_s3_buckets = merge(
    try(local.yaml_config.s3_buckets, {}),
    var.s3_buckets
  )
  
  # Process S3 buckets: load policy files, clean up metadata fields
  processed_s3_buckets = {
    for k, v in local.merged_s3_buckets : k => merge(v, {
      # Load bucket policy from file if specified
      bucket_policy = v.bucket_policy_file != null ? file(v.bucket_policy_file) : v.bucket_policy

      # Remove metadata fields that S3 module doesn't expect
      bucket_policy_file = null
      account_key        = null
      region_code        = null

      # Normalize KMS key ID (trim whitespace)
      encryption = v.encryption != null ? merge(v.encryption, {
        kms_master_key_id = try(trimspace(v.encryption.kms_master_key_id), null)
      }) : null
    })
  }

  # ===========================
  # KMS Keys Configuration
  # ===========================
  merged_kms_keys = merge(
    try(local.yaml_config.kms_keys, {}),
    try(var.kms_keys, {})
  )
  
  # Process KMS keys: load policy files if specified
  processed_kms_keys = {
    for k, v in local.merged_kms_keys : k => merge(v, {
      # Load KMS policy from file if policy_file is specified
      policy_content = try(v.policy_file, null) != null ? file(v.policy_file) : try(v.policy, v.policy_content, null)
      
      # Set defaults
      tags = merge(var.common_tags, try(v.tags, {}))
    })
  }

  # ===========================
  # IAM Configuration
  # ===========================
  merged_iam_users = merge(
    try(local.yaml_config.iam_users, {}),
    try(var.iam_users, {})
  )
  
  merged_iam_roles = merge(
    try(local.yaml_config.iam_roles, {}),
    try(var.iam_roles, {})
  )
  
  merged_iam_policies = merge(
    try(local.yaml_config.iam_policies, {}),
    try(var.iam_policies, {})
  )
}

# =============================================================================
# MODULE: S3 BUCKETS
# =============================================================================
# Creates S3 buckets with all features:
# - Versioning, Encryption (SSE-S3 or SSE-KMS)
# - Lifecycle rules, CORS, Website hosting
# - Public access block, Bucket policies
# - Logging, Notifications
# =============================================================================

module "s3" {
  # Only create if there are S3 buckets to deploy
  count = length(local.processed_s3_buckets) > 0 ? 1 : 0
  
  source = "git::https://github.com/Terraform-centilazed-pipline/tf-module.git//Module/S3?ref=main"

  common_tags = var.common_tags
  s3_buckets  = local.processed_s3_buckets
}

# =============================================================================
# MODULE: KMS KEYS
# =============================================================================
# Creates KMS keys for encryption
# Each key is created separately using for_each
# Supports: key rotation, multi-region, aliases, grants
# =============================================================================

module "kms" {
  for_each = local.processed_kms_keys
  
  source = "git::https://github.com/Terraform-centilazed-pipline/tf-module.git//Module/KMS?ref=main"

  # Key configuration
  description              = try(each.value.description, "KMS key for ${each.key}")
  key_usage                = try(each.value.key_usage, "ENCRYPT_DECRYPT")
  key_spec                 = try(each.value.key_spec, "SYMMETRIC_DEFAULT")
  multi_region             = try(each.value.multi_region, false)
  deletion_window_in_days  = try(each.value.deletion_window_in_days, 30)
  enable_key_rotation      = try(each.value.enable_key_rotation, true)
  
  # Policy
  policy_content = each.value.policy_content
  
  # Aliases
  aliases = try(each.value.aliases, [each.key])
  
  # Grants
  grants = try(each.value.grants, [])
  
  # Tags
  tags = each.value.tags
}

# =============================================================================
# MODULE: IAM (Users, Roles, Policies)
# =============================================================================
# Creates IAM resources:
# - Users with access keys and login profiles
# - Roles with trust policies
# - Policies (managed and inline)
# - Group memberships
# =============================================================================

module "iam" {
  # Only create if there are IAM resources to deploy
  count = (length(local.merged_iam_users) + length(local.merged_iam_roles) + length(local.merged_iam_policies)) > 0 ? 1 : 0
  
  source = "git::https://github.com/Terraform-centilazed-pipline/tf-module.git//Module/IAM?ref=main"

  # IAM Users
  users = local.merged_iam_users
  
  # IAM Roles
  roles = local.merged_iam_roles
  
  # IAM Policies
  policies = local.merged_iam_policies
  
  # Common tags
  tags = var.common_tags
}
