# ============================================================================
# MULTI-MODULE DEPLOYMENT EXAMPLE
# ============================================================================
# This example shows how to deploy BOTH S3 buckets AND KMS keys together
# in a single deployment using the centralized pipeline.
#
# Usage: Place this file in dev-deployment/Accounts/{account}/{region}/
# Example: dev-deployment/Accounts/arj-wkld-a-nonprd/us-east-1/app-with-kms.tfvars
# ============================================================================

# Common tags applied to ALL resources (S3 + KMS)
common_tags = {
  Environment = "nonprod"
  Project     = "secure-app"
  Owner       = "platform-team"
  CostCenter  = "engineering"
  ManagedBy   = "terraform-centralized-pipeline"
}

# ============================================================================
# S3 BUCKETS CONFIGURATION
# ============================================================================
s3_buckets = {
  # Application data bucket encrypted with KMS
  "app-data-bucket" = {
    bucket_name   = "arj-secure-app-data-nonprod-use1"
    account_key   = "arj-wkld-a-nonprd"
    region_code   = "use1"
    force_destroy = false

    # Enable versioning for data protection
    versioning_enabled = true

    # Encrypt with custom KMS key (created below)
    encryption = {
      sse_algorithm      = "aws:kms"
      kms_master_key_id  = "arn:aws:kms:us-east-1:123456789012:key/YOUR-KEY-ID"
      bucket_key_enabled = true
    }

    # Block all public access
    public_access_block = {
      block_public_acls       = true
      block_public_policy     = true
      ignore_public_acls      = true
      restrict_public_buckets = true
    }

    # Lifecycle policy to transition old data to Glacier
    lifecycle_rules = [
      {
        id     = "transition-old-data"
        status = "Enabled"
        
        transitions = [
          {
            days          = 90
            storage_class = "GLACIER"
          }
        ]
        
        noncurrent_version_expiration = {
          noncurrent_days = 180
        }
      }
    ]

    # Bucket policy from file
    bucket_policy_file = "templates/s3-bucket-policy.json"

    tags = {
      DataClassification = "internal"
      BackupRequired     = "true"
    }
  }

  # Logging bucket (no KMS encryption needed)
  "app-logs-bucket" = {
    bucket_name   = "arj-secure-app-logs-nonprod-use1"
    account_key   = "arj-wkld-a-nonprd"
    region_code   = "use1"
    force_destroy = true

    versioning_enabled = false

    # Use default SSE-S3 encryption for logs
    encryption = {
      sse_algorithm      = "AES256"
      kms_master_key_id  = ""  # Empty for SSE-S3
      bucket_key_enabled = false
    }

    # Expire logs after 90 days
    lifecycle_rules = [
      {
        id     = "expire-old-logs"
        status = "Enabled"
        
        expiration = {
          days = 90
        }
      }
    ]

    tags = {
      DataClassification = "logs"
      BackupRequired     = "false"
    }
  }
}

# ============================================================================
# KMS KEYS CONFIGURATION (for multi-module deployment)
# ============================================================================
# Note: To enable KMS module, you need to:
# 1. Uncomment the module "kms" block in main.tf
# 2. Provide the kms_keys configuration below

# Uncomment to enable KMS key creation:
# kms_keys = {
#   "app-encryption-key" = {
#     description              = "Encryption key for secure app data bucket"
#     key_usage                = "ENCRYPT_DECRYPT"
#     key_spec                 = "SYMMETRIC_DEFAULT"
#     enable_key_rotation      = true
#     deletion_window_in_days  = 30
#     multi_region             = false
#     
#     # KMS key policy (inline or from file)
#     policy = jsonencode({
#       Version = "2012-10-17"
#       Statement = [
#         {
#           Sid    = "Enable IAM User Permissions"
#           Effect = "Allow"
#           Principal = {
#             AWS = "arn:aws:iam::123456789012:root"
#           }
#           Action   = "kms:*"
#           Resource = "*"
#         },
#         {
#           Sid    = "Allow S3 to use the key"
#           Effect = "Allow"
#           Principal = {
#             Service = "s3.amazonaws.com"
#           }
#           Action = [
#             "kms:Decrypt",
#             "kms:GenerateDataKey"
#           ]
#           Resource = "*"
#         }
#       ]
#     })
#     
#     aliases = ["app-encryption-key", "secure-app-key"]
#     
#     tags = {
#       KeyPurpose = "S3Encryption"
#     }
#   }
# }

# ============================================================================
# HOW THIS WORKS:
# ============================================================================
# 1. You commit this file to: dev-deployment/Accounts/arj-wkld-a-nonprd/us-east-1/
# 2. Create a PR
# 3. GitHub Actions trigger:
#    - Discovers this tfvars file
#    - Checks out centerlized-pipline- repo (has main.tf with modules)
#    - Checks out tf-module repo (has Module/S3 and Module/KMS)
#    - Runs: terraform init (downloads BOTH modules)
#    - Runs: terraform plan (plans S3 + KMS together)
#    - OPA validates
#    - Auto-merges if pass
#    - Deploys BOTH modules in one apply
#
# 4. State file stored at:
#    s3://terraform-state-bucket/s3/arj-wkld-a-nonprd/us-east-1/app-with-kms/terraform.tfstate
#
# 5. Both S3 buckets AND KMS key are managed together as one deployment unit
# ============================================================================
