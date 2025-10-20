# =============================================================================
# COMPLETE MULTI-MODULE DEPLOYMENT EXAMPLE
# =============================================================================
# This example demonstrates deploying S3, KMS, and IAM resources together
# in a single coordinated deployment.
#
# File location: dev-deployment/Accounts/arj-wkld-a-nonprd/us-east-1/complete-app.tfvars
# =============================================================================

# =============================================================================
# COMMON TAGS - Applied to ALL resources
# =============================================================================
common_tags = {
  Environment    = "nonprod"
  Project        = "complete-secure-app"
  Owner          = "platform-team"
  CostCenter     = "engineering"
  DataClass      = "internal"
  ManagedBy      = "terraform-centralized-pipeline"
  DeploymentDate = "2025-10-17"
}

# =============================================================================
# 1. KMS KEYS - Create encryption keys first
# =============================================================================
kms_keys = {
  # KMS key for S3 bucket encryption
  "s3-encryption-key" = {
    description              = "Encryption key for application S3 buckets"
    key_usage                = "ENCRYPT_DECRYPT"
    key_spec                 = "SYMMETRIC_DEFAULT"
    multi_region             = false
    deletion_window_in_days  = 30
    enable_key_rotation      = true
    
    # KMS Key Policy - allows root account and S3 service
    policy = jsonencode({
      Version = "2012-10-17"
      Id      = "s3-encryption-key-policy"
      Statement = [
        {
          Sid    = "Enable IAM User Permissions"
          Effect = "Allow"
          Principal = {
            AWS = "arn:aws:iam::123456789012:root"
          }
          Action   = "kms:*"
          Resource = "*"
        },
        {
          Sid    = "Allow S3 to use the key"
          Effect = "Allow"
          Principal = {
            Service = "s3.amazonaws.com"
          }
          Action = [
            "kms:Decrypt",
            "kms:GenerateDataKey",
            "kms:DescribeKey"
          ]
          Resource = "*"
          Condition = {
            StringEquals = {
              "kms:ViaService" = "s3.us-east-1.amazonaws.com"
            }
          }
        },
        {
          Sid    = "Allow application role to use the key"
          Effect = "Allow"
          Principal = {
            AWS = "arn:aws:iam::123456789012:role/app-s3-access-role"
          }
          Action = [
            "kms:Decrypt",
            "kms:DescribeKey"
          ]
          Resource = "*"
        }
      ]
    })
    
    # Create aliases for easier reference
    aliases = ["s3-encryption-key", "app-data-key"]
    
    tags = {
      KeyPurpose = "S3Encryption"
      Compliance = "SOC2"
    }
  }

  # KMS key for sensitive data encryption
  "sensitive-data-key" = {
    description              = "Encryption key for highly sensitive application data"
    key_usage                = "ENCRYPT_DECRYPT"
    key_spec                 = "SYMMETRIC_DEFAULT"
    multi_region             = true  # Multi-region for DR
    deletion_window_in_days  = 30
    enable_key_rotation      = true
    
    policy = jsonencode({
      Version = "2012-10-17"
      Statement = [
        {
          Sid    = "Enable IAM User Permissions"
          Effect = "Allow"
          Principal = {
            AWS = "arn:aws:iam::123456789012:root"
          }
          Action   = "kms:*"
          Resource = "*"
        }
      ]
    })
    
    aliases = ["sensitive-data-key"]
    
    tags = {
      KeyPurpose        = "DataEncryption"
      DataClassification = "PII"
      Compliance        = "HIPAA"
    }
  }
}

# =============================================================================
# 2. S3 BUCKETS - Using the KMS keys created above
# =============================================================================
s3_buckets = {
  # Application data bucket with KMS encryption
  "app-data-bucket" = {
    bucket_name   = "arj-complete-app-data-nonprod-use1"
    account_key   = "arj-wkld-a-nonprd"
    region_code   = "use1"
    force_destroy = false

    # Enable versioning for data protection
    versioning_enabled = true

    # Encrypt with the KMS key created above
    # NOTE: After first apply, update this with the actual KMS key ARN from outputs
    encryption = {
      sse_algorithm      = "aws:kms"
      kms_master_key_id  = "arn:aws:kms:us-east-1:123456789012:key/REPLACE-WITH-KMS-KEY-ID"
      bucket_key_enabled = true
    }

    # Block all public access
    public_access_block = {
      block_public_acls       = true
      block_public_policy     = true
      ignore_public_acls      = true
      restrict_public_buckets = true
    }

    # Lifecycle management
    lifecycle_rules = [
      {
        id     = "transition-and-expire"
        status = "Enabled"
        
        # Move to cheaper storage after 90 days
        transitions = [
          {
            days          = 90
            storage_class = "STANDARD_IA"
          },
          {
            days          = 180
            storage_class = "GLACIER"
          }
        ]
        
        # Delete old versions after 365 days
        noncurrent_version_expiration = {
          noncurrent_days = 365
        }
        
        # Delete incomplete multipart uploads after 7 days
        abort_incomplete_multipart_upload_days = 7
      }
    ]

    # Bucket policy - allow access only from specific IAM role
    bucket_policy = jsonencode({
      Version = "2012-10-17"
      Statement = [
        {
          Sid    = "DenyInsecureTransport"
          Effect = "Deny"
          Principal = "*"
          Action = "s3:*"
          Resource = [
            "arn:aws:s3:::arj-complete-app-data-nonprod-use1",
            "arn:aws:s3:::arj-complete-app-data-nonprod-use1/*"
          ]
          Condition = {
            Bool = {
              "aws:SecureTransport" = "false"
            }
          }
        },
        {
          Sid    = "AllowApplicationRoleAccess"
          Effect = "Allow"
          Principal = {
            AWS = "arn:aws:iam::123456789012:role/app-s3-access-role"
          }
          Action = [
            "s3:GetObject",
            "s3:PutObject",
            "s3:DeleteObject",
            "s3:ListBucket"
          ]
          Resource = [
            "arn:aws:s3:::arj-complete-app-data-nonprod-use1",
            "arn:aws:s3:::arj-complete-app-data-nonprod-use1/*"
          ]
        }
      ]
    })

    # Server access logging
    logging = {
      target_bucket = "arj-complete-app-logs-nonprod-use1"
      target_prefix = "access-logs/app-data/"
    }

    tags = {
      DataClassification = "internal"
      BackupRequired     = "true"
      RetentionPeriod    = "7years"
    }
  }

  # Logging bucket (receives logs from other buckets)
  "app-logs-bucket" = {
    bucket_name   = "arj-complete-app-logs-nonprod-use1"
    account_key   = "arj-wkld-a-nonprd"
    region_code   = "use1"
    force_destroy = true  # Can delete logs bucket

    versioning_enabled = false

    # Use default S3 encryption for logs (not KMS)
    encryption = {
      sse_algorithm      = "AES256"
      kms_master_key_id  = ""
      bucket_key_enabled = false
    }

    # Auto-expire logs after 90 days
    lifecycle_rules = [
      {
        id     = "expire-old-logs"
        status = "Enabled"
        
        expiration = {
          days = 90
        }
      }
    ]

    # Bucket policy - allow S3 log delivery
    bucket_policy = jsonencode({
      Version = "2012-10-17"
      Statement = [
        {
          Sid    = "S3ServerAccessLogsPolicy"
          Effect = "Allow"
          Principal = {
            Service = "logging.s3.amazonaws.com"
          }
          Action = "s3:PutObject"
          Resource = "arn:aws:s3:::arj-complete-app-logs-nonprod-use1/*"
          Condition = {
            StringEquals = {
              "aws:SourceAccount" = "123456789012"
            }
          }
        }
      ]
    })

    tags = {
      DataClassification = "logs"
      BackupRequired     = "false"
      Purpose            = "audit-logging"
    }
  }

  # Backup bucket with cross-region replication
  "app-backup-bucket" = {
    bucket_name   = "arj-complete-app-backup-nonprod-use1"
    account_key   = "arj-wkld-a-nonprd"
    region_code   = "use1"
    force_destroy = false

    versioning_enabled = true  # Required for replication

    encryption = {
      sse_algorithm      = "aws:kms"
      kms_master_key_id  = "arn:aws:kms:us-east-1:123456789012:key/REPLACE-WITH-KMS-KEY-ID"
      bucket_key_enabled = true
    }

    public_access_block = {
      block_public_acls       = true
      block_public_policy     = true
      ignore_public_acls      = true
      restrict_public_buckets = true
    }

    # Backup retention policy
    lifecycle_rules = [
      {
        id     = "backup-retention"
        status = "Enabled"
        
        # Transition to Glacier Deep Archive for long-term retention
        transitions = [
          {
            days          = 30
            storage_class = "GLACIER_IR"  # Instant Retrieval
          },
          {
            days          = 90
            storage_class = "DEEP_ARCHIVE"
          }
        ]
        
        # Keep backups for 7 years
        expiration = {
          days = 2555  # 7 years
        }
      }
    ]

    tags = {
      DataClassification = "backup"
      BackupRequired     = "true"
      RetentionPeriod    = "7years"
      Purpose            = "disaster-recovery"
    }
  }
}

# =============================================================================
# 3. IAM USERS & ROLES - For accessing the S3 buckets
# =============================================================================

iam_users = {
  "app-developer-1" = {
    name                    = "app-developer-1"
    path                    = "/developers/"
    force_destroy           = true
    create_access_key       = true
    create_login_profile    = true
    password_reset_required = true
    password_length         = 24
    
    # Attach policies
    policies = {
      s3-read-only = "arn:aws:iam::aws:policy/AmazonS3ReadOnlyAccess"
    }
    
    tags = {
      Team = "development"
      Role = "developer"
    }
  }

  "app-deployer" = {
    name                    = "app-deployer"
    path                    = "/automation/"
    force_destroy           = true
    create_access_key       = true
    create_login_profile    = false  # Service account, no console access
    
    tags = {
      Team = "devops"
      Role = "automation"
    }
  }
}

iam_roles = {
  "app-s3-access-role" = {
    name        = "app-s3-access-role"
    path        = "/application/"
    description = "Role for application to access S3 buckets"
    
    # Trust policy - who can assume this role
    assume_role_policy = jsonencode({
      Version = "2012-10-17"
      Statement = [
        {
          Effect = "Allow"
          Principal = {
            Service = "ec2.amazonaws.com"
          }
          Action = "sts:AssumeRole"
        }
      ]
    })
    
    # Inline policies
    inline_policies = {
      s3-bucket-access = jsonencode({
        Version = "2012-10-17"
        Statement = [
          {
            Effect = "Allow"
            Action = [
              "s3:GetObject",
              "s3:PutObject",
              "s3:DeleteObject",
              "s3:ListBucket"
            ]
            Resource = [
              "arn:aws:s3:::arj-complete-app-data-nonprod-use1",
              "arn:aws:s3:::arj-complete-app-data-nonprod-use1/*"
            ]
          },
          {
            Effect = "Allow"
            Action = [
              "kms:Decrypt",
              "kms:GenerateDataKey",
              "kms:DescribeKey"
            ]
            Resource = "arn:aws:kms:us-east-1:123456789012:key/*"
          }
        ]
      })
    }
    
    tags = {
      Application = "complete-secure-app"
      Environment = "nonprod"
    }
  }
}

# =============================================================================
# DEPLOYMENT INSTRUCTIONS:
# =============================================================================
# 1. Commit this file to: dev-deployment/Accounts/arj-wkld-a-nonprd/us-east-1/
# 2. Create a Pull Request
# 3. GitHub Actions will:
#    - Discover this tfvars file
#    - Checkout centerlized-pipline- (has main.tf with module calls)
#    - Checkout tf-module (has Module/S3, Module/KMS, Module/IAM)
#    - Run terraform init (downloads ALL THREE modules)
#    - Run terraform plan (plans resources for ALL modules together)
#    - Run OPA validation
#    - Post plan to PR as comment
#    - Auto-merge if all checks pass
# 4. After merge to main:
#    - Deploys ALL resources: 2 KMS keys + 3 S3 buckets + 2 users + 1 role
#    - All managed in ONE state file
#    - All atomic - succeed or fail together
#
# 5. State file location:
#    s3://terraform-state-bucket/s3/arj-wkld-a-nonprd/us-east-1/complete-app/terraform.tfstate
#
# 6. Post-deployment:
#    - Get KMS key ARNs from terraform outputs
#    - Update the kms_master_key_id in S3 bucket configs with real ARNs
#    - Create new PR with updated ARNs
# =============================================================================
