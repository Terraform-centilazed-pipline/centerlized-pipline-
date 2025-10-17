# S3 Management Deployment Outputs

# Debug output to highlight missing KMS configuration
output "debug_kms_requirements" {
  description = "Lists buckets missing KMS key IDs and shows resolved encryption IDs"
  value = {
    buckets_missing_kms = local.buckets_missing_kms
    buckets = {
      for k, v in local.processed_s3_buckets : k => {
        kms_key_id = v.encryption != null ? v.encryption.kms_master_key_id : "none"
      }
    }
  }
}

output "s3_buckets" {
  description = "Map of S3 buckets created"
  value       = module.s3.s3_buckets
}

output "bucket_website_endpoints" {
  description = "Map of S3 bucket website endpoints"
  value       = module.s3.bucket_website_endpoints
}

output "bucket_policies" {
  description = "Map of S3 bucket policies"
  value       = module.s3.bucket_policies
}

output "bucket_versioning" {
  description = "Map of S3 bucket versioning configurations"
  value       = module.s3.bucket_versioning
}

output "bucket_encryption" {
  description = "Map of S3 bucket encryption configurations"
  value       = module.s3.bucket_encryption
}

output "bucket_cors" {
  description = "Map of S3 bucket CORS configurations"
  value       = module.s3.bucket_cors
}

output "bucket_lifecycle" {
  description = "Map of S3 bucket lifecycle configurations"
  value       = module.s3.bucket_lifecycle
}

output "bucket_logging" {
  description = "Map of S3 bucket logging configurations"
  value       = module.s3.bucket_logging
}

output "bucket_replication" {
  description = "Map of S3 bucket replication configurations"
  value       = module.s3.bucket_replication
}

output "bucket_notifications" {
  description = "Map of S3 bucket notification configurations"
  value       = module.s3.bucket_notifications
}

output "bucket_public_access_block" {
  description = "Map of S3 bucket public access block configurations"
  value       = module.s3.bucket_public_access_block
}