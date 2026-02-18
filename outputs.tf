# =============================================================================
# CENTRALIZED TERRAFORM PIPELINE - Outputs
# =============================================================================
# All resource outputs aggregated from S3, KMS, and IAM modules.
# These outputs are surfaced after a successful terraform apply and can be
# used by other Terraform configurations or referenced in CI/CD pipelines.
#
# OUTPUT GROUPS:
#   - deployment_summary     : High-level count of all deployed resources
#   - s3_*                   : S3 bucket IDs, ARNs, domain names, configs
#   - kms_*                  : KMS key IDs, ARNs, aliases
#   - iam_*                  : IAM user/role ARNs, names, access keys (sensitive)
#   - resource_map           : Unified lookup map of all resource IDs and ARNs
#   - debug_configuration    : Resource counts and module status for troubleshooting
# =============================================================================

# =============================================================================
# DEPLOYMENT SUMMARY
# =============================================================================

output "deployment_summary" {
  description = "High-level summary of the deployment: account ID, region, and count of each resource type (S3 buckets, KMS keys, IAM users/roles/policies) created in this terraform apply."
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
  description = "Full S3 bucket resource details keyed by logical bucket name. Each entry contains the bucket ID, ARN, region, and all configuration attributes returned by the S3 module."
  value       = length(module.s3) > 0 ? module.s3[0].s3_buckets : {}
}

output "s3_bucket_arns" {
  description = "Map of S3 bucket ARNs keyed by logical bucket name. Use these ARNs in IAM policies, KMS key policies, or cross-module references. Format: arn:aws:s3:::<bucket-name>"
  value = length(module.s3) > 0 ? {
    for k, v in module.s3[0].s3_buckets : k => v.arn
  } : {}
}

output "s3_bucket_names" {
  description = "Map of actual S3 bucket names (IDs) keyed by logical bucket name. These are the globally unique bucket names as created in AWS, matching the bucket_name field in your tfvars."
  value = length(module.s3) > 0 ? {
    for k, v in module.s3[0].s3_buckets : k => v.id
  } : {}
}

output "s3_bucket_domains" {
  description = "Map of S3 bucket regional domain names keyed by logical bucket name. Use these endpoints for direct bucket access and in CloudFront origins. Format: <bucket>.s3.<region>.amazonaws.com"
  value = length(module.s3) > 0 ? {
    for k, v in module.s3[0].s3_buckets : k => v.bucket_regional_domain_name
  } : {}
}

# =============================================================================
# S3 DETAILED OUTPUTS
# =============================================================================

output "bucket_versioning" {
  description = "Map of S3 bucket versioning configurations keyed by logical bucket name. Shows whether versioning is enabled or suspended on each bucket."
  value       = length(module.s3) > 0 ? module.s3[0].bucket_versioning : {}
}

output "bucket_encryption" {
  description = "Map of S3 bucket server-side encryption configurations keyed by logical bucket name. Shows the SSE algorithm (AES256 or aws:kms) and the KMS key ARN if applicable."
  value       = length(module.s3) > 0 ? module.s3[0].bucket_encryption : {}
}

output "bucket_lifecycle" {
  description = "Map of S3 bucket lifecycle rule configurations keyed by logical bucket name. Shows object transition and expiration rules configured on each bucket."
  value       = length(module.s3) > 0 ? module.s3[0].bucket_lifecycle : {}
}

output "bucket_policies" {
  description = "Map of applied S3 bucket policy JSON documents keyed by logical bucket name. Useful for auditing and verifying that the correct bucket policies were applied."
  value       = length(module.s3) > 0 ? module.s3[0].bucket_policies : {}
}

output "bucket_public_access_block" {
  description = "Map of S3 public access block settings keyed by logical bucket name. Shows whether BlockPublicAcls, IgnorePublicAcls, BlockPublicPolicy, and RestrictPublicBuckets are enabled on each bucket."
  value       = length(module.s3) > 0 ? try(module.s3[0].bucket_public_access_block, {}) : {}
}

output "bucket_logging" {
  description = "Map of S3 access logging configurations keyed by logical bucket name. Shows the target log bucket and prefix where access logs are delivered."
  value       = length(module.s3) > 0 ? module.s3[0].bucket_logging : {}
}

output "bucket_cors" {
  description = "Map of S3 CORS rule configurations keyed by logical bucket name. Shows allowed origins, methods, and headers for cross-origin requests to each bucket."
  value       = length(module.s3) > 0 ? module.s3[0].bucket_cors : {}
}

output "bucket_website_endpoints" {
  description = "Map of S3 static website hosting endpoints keyed by logical bucket name. Only populated for buckets with website hosting enabled. Use these URLs to access bucket-hosted static sites."
  value       = length(module.s3) > 0 ? module.s3[0].bucket_website_endpoints : {}
}

output "bucket_notifications" {
  description = "Map of S3 event notification configurations keyed by logical bucket name. Shows configured Lambda, SQS, and SNS notification targets for bucket events."
  value       = length(module.s3) > 0 ? module.s3[0].bucket_notifications : {}
}

output "bucket_replication" {
  description = "Map of S3 cross-region replication (CRR) configurations keyed by logical bucket name. Shows replication rules and destination buckets for each source bucket."
  value       = length(module.s3) > 0 ? try(module.s3[0].bucket_replication, {}) : {}
}

# =============================================================================
# KMS OUTPUTS
# =============================================================================

output "kms_keys" {
  description = "Full KMS key resource details keyed by logical key name. Each entry includes the key ID, ARN, usage type, spec, multi-region flag, rotation setting, and alias names. Use key_arn values when configuring S3 bucket encryption or other services that require KMS."
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
  description = "Map of KMS key IDs keyed by logical key name. These are the short UUID-format key IDs (e.g. mrk-abc123def456). Use key ARNs (kms_key_arns) when referencing keys in policies or resource configurations."
  value       = { for k, v in module.kms : k => v.key_id }
}

output "kms_key_arns" {
  description = "Map of KMS key ARNs keyed by logical key name. Use these ARNs in the s3_buckets.encryption.kms_master_key_id field when deploying S3 buckets with KMS encryption in a separate deployment. Format: arn:aws:kms:<region>:<account-id>:key/<key-id>"
  value       = { for k, v in module.kms : k => v.key_arn }
}

output "kms_key_aliases" {
  description = "Map of KMS alias names keyed by logical key name. Aliases are human-readable names for KMS keys (e.g. alias/my-app-key). Use aliases when referencing keys in application configs or other Terraform modules."
  value       = { for k, v in module.kms : k => v.alias_names }
}

# =============================================================================
# IAM OUTPUTS
# =============================================================================

output "iam_users" {
  description = "Full IAM user resource details keyed by logical user name. Each entry contains the user ARN, name, path, and tags as returned by the IAM module after creation."
  value       = length(module.iam) > 0 ? module.iam[0].users : {}
}

output "iam_user_arns" {
  description = "Map of IAM user ARNs keyed by logical user name. Use these ARNs in trust policies, resource-based policies, or when granting cross-account access. Format: arn:aws:iam::<account-id>:user/<username>"
  value       = length(module.iam) > 0 ? module.iam[0].user_arns : {}
}

output "iam_user_names" {
  description = "List of IAM usernames as created in AWS. These are the actual IAM usernames (matching the name field in the iam_users variable), not the logical Terraform map keys."
  value       = length(module.iam) > 0 ? keys(module.iam[0].users) : []
}

output "iam_roles" {
  description = "Full IAM role resource details keyed by logical role name. Each entry contains the role ARN, name, unique ID, and assume-role policy as returned by the IAM module after creation."
  value       = length(module.iam) > 0 ? try(module.iam[0].roles, {}) : {}
}

output "iam_role_arns" {
  description = "Map of IAM role ARNs keyed by logical role name. Use these ARNs in trust policies (to allow other services/roles to assume this role), in Lambda function configurations, or ECS task definitions. Format: arn:aws:iam::<account-id>:role/<role-name>"
  value       = length(module.iam) > 0 ? try(module.iam[0].role_arns, {}) : {}
}

output "iam_role_names" {
  description = "List of IAM role names as created in AWS. These are the actual IAM role names (matching the name field in iam_roles), not the logical Terraform map keys."
  value       = length(module.iam) > 0 ? keys(try(module.iam[0].roles, {})) : []
}

# =============================================================================
# SENSITIVE OUTPUTS
# =============================================================================

output "iam_access_keys" {
  description = "SENSITIVE: Map of IAM user programmatic access key IDs keyed by logical user name. Only populated for users with create_access_key = true. These are the ACCESS KEY IDs only — retrieve secrets from iam_access_key_secrets output separately."
  value       = length(module.iam) > 0 ? try(module.iam[0].access_key_ids, {}) : {}
  sensitive   = true
}

output "iam_access_key_secrets" {
  description = "SENSITIVE: Map of IAM user access key secrets (the actual secret access keys) keyed by logical user name. Only shown once at creation time. Store securely — these cannot be retrieved again from AWS after initial creation."
  value       = length(module.iam) > 0 ? try(module.iam[0].access_key_secrets, {}) : {}
  sensitive   = true
}

output "iam_user_passwords" {
  description = "SENSITIVE: Map of auto-generated AWS Console login passwords keyed by logical user name. Only populated for users with create_login_profile = true. Store securely — users should change these on first login."
  value       = length(module.iam) > 0 ? try(module.iam[0].login_profile_passwords, {}) : {}
  sensitive   = true
}

# =============================================================================
# REFERENCE OUTPUTS (for cross-module usage)
# =============================================================================

output "resource_map" {
  description = "Unified cross-resource lookup map of all deployed resource IDs and ARNs. Contains entries for s3_buckets, kms_keys, iam_users, and iam_roles. Use this output as a single reference point when wiring together resources across modules or when a downstream system needs a consolidated inventory of what was deployed."
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
  description = "Diagnostic output for troubleshooting deployments. Shows the count and map keys of all processed resource configurations (S3 buckets, KMS keys, IAM users/roles/policies) and whether each Terraform module instance was created. Use this to verify that the correct number of resources were discovered and processed from your tfvars."
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