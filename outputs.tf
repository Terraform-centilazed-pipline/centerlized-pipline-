# =============================================================================
# Centralized Pipeline - Outputs
# =============================================================================
# All outputs aggregated from S3, KMS, and IAM modules
# Follows Terraform best practices: outputs in outputs.tf, not main.tf
# =============================================================================

# =============================================================================
# DEPLOYMENT SUMMARY
# =============================================================================

output "deployment_summary" {
  description = "Summary of all deployed resources"
  value = {
    account_id   = data.aws_caller_identity.current.account_id
    region       = data.aws_region.current.id
    s3_buckets   = length(local.processed_s3_buckets)
    kms_keys     = length(local.processed_kms_keys)
    iam_users    = length(local.merged_iam_users)
    iam_roles    = length(local.merged_iam_roles)
    iam_policies = length(local.merged_iam_policies)
    deployed_at  = timestamp()
  }
}

# =============================================================================
# S3 OUTPUTS
# =============================================================================

output "s3_buckets" {
  description = "Complete S3 bucket information"
  value       = length(module.s3) > 0 ? module.s3[0].s3_buckets : {}
}

output "s3_bucket_arns" {
  description = "Map of S3 bucket ARNs"
  value = length(module.s3) > 0 ? {
    for k, v in module.s3[0].s3_buckets : k => v.arn
  } : {}
}

output "s3_bucket_names" {
  description = "Map of S3 bucket names (IDs)"
  value = length(module.s3) > 0 ? {
    for k, v in module.s3[0].s3_buckets : k => v.id
  } : {}
}

output "s3_bucket_domains" {
  description = "Map of S3 bucket regional domain names"
  value = length(module.s3) > 0 ? {
    for k, v in module.s3[0].s3_buckets : k => v.bucket_regional_domain_name
  } : {}
}

# =============================================================================
# S3 DETAILED OUTPUTS
# =============================================================================

output "bucket_versioning" {
  description = "Map of S3 bucket versioning configurations"
  value       = length(module.s3) > 0 ? module.s3[0].bucket_versioning : {}
}

output "bucket_encryption" {
  description = "Map of S3 bucket encryption configurations"
  value       = length(module.s3) > 0 ? module.s3[0].bucket_encryption : {}
}

output "bucket_lifecycle" {
  description = "Map of S3 bucket lifecycle configurations"
  value       = length(module.s3) > 0 ? module.s3[0].bucket_lifecycle : {}
}

output "bucket_policies" {
  description = "Map of S3 bucket policies"
  value       = length(module.s3) > 0 ? module.s3[0].bucket_policies : {}
}

output "bucket_public_access_block" {
  description = "Map of S3 bucket public access block configurations"
  value       = length(module.s3) > 0 ? try(module.s3[0].bucket_public_access_block, {}) : {}
}

output "bucket_logging" {
  description = "Map of S3 bucket logging configurations"
  value       = length(module.s3) > 0 ? module.s3[0].bucket_logging : {}
}

output "bucket_cors" {
  description = "Map of S3 bucket CORS configurations"
  value       = length(module.s3) > 0 ? module.s3[0].bucket_cors : {}
}

output "bucket_website_endpoints" {
  description = "Map of S3 bucket website endpoints"
  value       = length(module.s3) > 0 ? module.s3[0].bucket_website_endpoints : {}
}

output "bucket_notifications" {
  description = "Map of S3 bucket notification configurations"
  value       = length(module.s3) > 0 ? module.s3[0].bucket_notifications : {}
}

output "bucket_replication" {
  description = "Map of S3 bucket replication configurations"
  value       = length(module.s3) > 0 ? try(module.s3[0].bucket_replication, {}) : {}
}

# =============================================================================
# KMS OUTPUTS
# =============================================================================

output "kms_keys" {
  description = "Complete KMS key information"
  value = {
    for k, v in module.kms : k => {
      key_id              = v.key_id
      key_arn             = v.key_arn
      key_usage           = v.key_usage
      key_spec            = v.key_spec
      multi_region        = v.multi_region
      enable_key_rotation = v.enable_key_rotation
      aliases             = v.aliases
    }
  }
}

output "kms_key_ids" {
  description = "Map of KMS key IDs for easy reference"
  value       = { for k, v in module.kms : k => v.key_id }
}

output "kms_key_arns" {
  description = "Map of KMS key ARNs for bucket encryption configuration"
  value       = { for k, v in module.kms : k => v.key_arn }
}

output "kms_key_aliases" {
  description = "Map of KMS key aliases"
  value       = { for k, v in module.kms : k => v.alias_names }
}

# =============================================================================
# IAM OUTPUTS
# =============================================================================

output "iam_users" {
  description = "Complete IAM user information"
  value       = length(module.iam) > 0 ? module.iam[0].users : {}
}

output "iam_user_arns" {
  description = "Map of IAM user ARNs"
  value       = length(module.iam) > 0 ? module.iam[0].user_arns : {}
}

output "iam_user_names" {
  description = "List of IAM user names"
  value       = length(module.iam) > 0 ? keys(module.iam[0].users) : []
}

output "iam_roles" {
  description = "Complete IAM role information"
  value       = length(module.iam) > 0 ? try(module.iam[0].roles, {}) : {}
}

output "iam_role_arns" {
  description = "Map of IAM role ARNs"
  value       = length(module.iam) > 0 ? try(module.iam[0].role_arns, {}) : {}
}

output "iam_role_names" {
  description = "List of IAM role names"
  value       = length(module.iam) > 0 ? keys(try(module.iam[0].roles, {})) : []
}

# =============================================================================
# SENSITIVE OUTPUTS
# =============================================================================

output "iam_access_keys" {
  description = "IAM user access key IDs (secrets are sensitive)"
  value       = length(module.iam) > 0 ? try(module.iam[0].access_key_ids, {}) : {}
  sensitive   = true
}

output "iam_access_key_secrets" {
  description = "IAM user access key secrets"
  value       = length(module.iam) > 0 ? try(module.iam[0].access_key_secrets, {}) : {}
  sensitive   = true
}

output "iam_user_passwords" {
  description = "IAM user console passwords"
  value       = length(module.iam) > 0 ? try(module.iam[0].login_profile_passwords, {}) : {}
  sensitive   = true
}

# =============================================================================
# REFERENCE OUTPUTS (for cross-module usage)
# =============================================================================

output "resource_map" {
  description = "Quick reference map of all resource IDs and ARNs"
  value = {
    s3_buckets = length(module.s3) > 0 ? {
      for k, v in module.s3[0].s3_buckets : k => {
        id  = v.id
        arn = v.arn
      }
    } : {}
    
    kms_keys = {
      for k, v in module.kms : k => {
        id  = v.key_id
        arn = v.key_arn
      }
    }
    
    iam_users = length(module.iam) > 0 ? {
      for k, v in module.iam[0].users : k => {
        name = v.name
        arn  = v.arn
      }
    } : {}
    
    iam_roles = length(module.iam) > 0 ? {
      for k, v in try(module.iam[0].roles, {}) : k => {
        name = try(v.name, null)
        arn  = try(v.arn, null)
      }
    } : {}
  }
}

# =============================================================================
# DEBUG OUTPUTS
# =============================================================================

output "debug_configuration" {
  description = "Debug information about the deployment configuration"
  value = {
    # Counts
    s3_buckets_count   = length(local.processed_s3_buckets)
    kms_keys_count     = length(local.processed_kms_keys)
    iam_users_count    = length(local.merged_iam_users)
    iam_roles_count    = length(local.merged_iam_roles)
    iam_policies_count = length(local.merged_iam_policies)
    
    # Names/Keys
    s3_bucket_keys = keys(local.processed_s3_buckets)
    kms_key_keys   = keys(local.processed_kms_keys)
    iam_user_keys  = keys(local.merged_iam_users)
    iam_role_keys  = keys(local.merged_iam_roles)
    
    # Module status
    s3_module_created  = length(module.s3) > 0
    kms_modules_count  = length(module.kms)
    iam_module_created = length(module.iam) > 0
  }
}