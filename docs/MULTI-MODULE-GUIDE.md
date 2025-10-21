# Multi-Module Deployment Architecture

## Overview

Your centralized pipeline now supports **deploying multiple modules in a single tfvars file**. This allows you to deploy S3 buckets, KMS keys, and IAM resources together as a coordinated unit.

## File Structure

```
centerlized-pipline-/
├── main.tf                    ← NEW: Orchestrates all modules
├── variables.tf               ← UPDATED: Added KMS and IAM variables
├── outputs.tf                 ← UPDATED: Outputs from all modules
├── providers.tf               ← Existing: AWS provider config
└── templates/
    ├── complete-multi-module-example.tfvars  ← Complete example
    └── multi-module-example.tfvars           ← Simple example

tf-module/Module/
├── S3/                        ← S3 bucket module
├── KMS/                       ← KMS key module
└── IAM/                       ← IAM users/roles module
```

## How main.tf Works

### 1. **Module Declarations**

```hcl
# S3 Module - creates bucket map
module "s3" {
  count  = length(local.processed_s3_buckets) > 0 ? 1 : 0
  source = "../tf-module/Module/S3"
  
  common_tags = var.common_tags
  s3_buckets  = local.processed_s3_buckets  # Map of buckets
}

# KMS Module - creates keys with for_each
module "kms" {
  for_each = local.processed_kms_keys
  source   = "../tf-module/Module/KMS"
  
  description = each.value.description
  policy_content = each.value.policy_content
  # ... more config
}

# IAM Module - creates users/roles map
module "iam" {
  count  = (length(local.merged_iam_users) + length(local.merged_iam_roles)) > 0 ? 1 : 0
  source = "../tf-module/Module/IAM"
  
  users  = local.merged_iam_users   # Map of users
  roles  = local.merged_iam_roles   # Map of roles
  tags   = var.common_tags
}
```

### 2. **Module Patterns**

| Module | Pattern | Reason |
|--------|---------|--------|
| **S3** | `count` with map | S3 module accepts `s3_buckets = { ... }` map |
| **KMS** | `for_each` | KMS module creates ONE key per call, so we iterate |
| **IAM** | `count` with maps | IAM module accepts `users = { ... }` and `roles = { ... }` maps |

### 3. **Local Processing**

```hcl
locals {
  # Load from YAML or variables
  yaml_config = var.yaml_config_file != "" ? yamldecode(file(var.yaml_config_file)) : {}
  
  # Merge YAML + tfvars
  merged_s3_buckets = merge(
    try(local.yaml_config.s3_buckets, {}),
    var.s3_buckets
  )
  
  # Process S3: load policy files, clean metadata
  processed_s3_buckets = {
    for k, v in local.merged_s3_buckets : k => merge(v, {
      bucket_policy = v.bucket_policy_file != null ? file(v.bucket_policy_file) : v.bucket_policy
      # Remove fields S3 module doesn't expect
      bucket_policy_file = null
      account_key        = null
      region_code        = null
    })
  }
  
  # Same for KMS and IAM...
}
```

## Using Multiple Modules in One Deployment

### Simple Example: S3 + KMS

```hcl
# File: dev-deployment/Accounts/arj-wkld-a-nonprd/us-east-1/my-app.tfvars

common_tags = {
  Environment = "nonprod"
  Project     = "my-app"
}

# Create KMS key
kms_keys = {
  "app-key" = {
    description         = "Encryption key for my app"
    enable_key_rotation = true
    policy = jsonencode({
      Version = "2012-10-17"
      Statement = [
        {
          Sid    = "Enable IAM User Permissions"
          Effect = "Allow"
          Principal = { AWS = "arn:aws:iam::123456789012:root" }
          Action   = "kms:*"
          Resource = "*"
        }
      ]
    })
    aliases = ["app-key"]
  }
}

# Create S3 bucket using the KMS key
s3_buckets = {
  "my-bucket" = {
    bucket_name   = "my-app-bucket-nonprod"
    account_key   = "arj-wkld-a-nonprd"
    region_code   = "use1"
    
    versioning_enabled = true
    
    encryption = {
      sse_algorithm      = "aws:kms"
      kms_master_key_id  = "arn:aws:kms:us-east-1:123456789012:key/abc-123"
      bucket_key_enabled = true
    }
  }
}
```

### Complete Example: S3 + KMS + IAM

See `templates/complete-multi-module-example.tfvars` for a full example with:
- 2 KMS keys
- 3 S3 buckets
- 2 IAM users
- 1 IAM role

## Deployment Flow

```
1. Developer commits tfvars with multiple module configs
   ↓
2. GitHub Actions triggered
   ↓
3. Checkout all repos:
   - dev-deployment (source tfvars)
   - centerlized-pipline- (main.tf)
   - tf-module (Module/S3, Module/KMS, Module/IAM)
   - OPA-Poclies (policy validation)
   ↓
4. terraform init
   Downloads: Module/S3 + Module/KMS + Module/IAM
   ↓
5. terraform plan
   Plans: S3 resources + KMS resources + IAM resources
   Creates JSON plan for OPA
   ↓
6. OPA validation
   Validates ALL resources against policies
   ↓
7. Post PR comment
   Shows planned changes for ALL modules
   ↓
8. Auto-merge (pass) or Auto-close (fail)
   ↓
9. terraform apply (on main branch)
   Deploys ALL modules together atomically
   All resources in ONE state file
```

## State File Structure

When you deploy multiple modules, they all go into **one state file**:

```
State Key: s3/arj-wkld-a-nonprd/us-east-1/my-app/terraform.tfstate

Resources:
├── module.s3[0].aws_s3_bucket.buckets["my-bucket"]
├── module.s3[0].aws_s3_bucket_versioning.versioning["my-bucket"]
├── module.s3[0].aws_s3_bucket_server_side_encryption_configuration.encryption["my-bucket"]
├── module.kms["app-key"].aws_kms_key.this
├── module.kms["app-key"].aws_kms_alias.this[0]
├── module.iam[0].aws_iam_user.users["app-user"]
└── module.iam[0].aws_iam_role.roles["app-role"]
```

## Outputs

### Basic Outputs (from main.tf)

```hcl
output "deployment_summary" {
  value = {
    account_id   = "123456789012"
    region       = "us-east-1"
    s3_buckets   = 3
    kms_keys     = 2
    iam_users    = 2
    iam_roles    = 1
    deployed_at  = "2025-10-17T10:30:00Z"
  }
}

output "s3_bucket_arns" {
  value = {
    "my-bucket"     = "arn:aws:s3:::my-app-bucket-nonprod"
    "logs-bucket"   = "arn:aws:s3:::my-app-logs-nonprod"
    "backup-bucket" = "arn:aws:s3:::my-app-backup-nonprod"
  }
}

output "kms_key_ids" {
  value = {
    "app-key"       = "abc-123-def-456"
    "sensitive-key" = "xyz-789-uvw-012"
  }
}

output "iam_user_arns" {
  value = {
    "app-developer" = "arn:aws:iam::123456789012:user/app-developer"
    "app-deployer"  = "arn:aws:iam::123456789012:user/app-deployer"
  }
}
```

### Detailed Outputs (from outputs.tf)

```hcl
output "s3_buckets_detailed"
output "bucket_versioning"
output "bucket_encryption"
output "bucket_lifecycle"
output "kms_keys_detailed"
output "iam_users_detailed"
```

## Benefits of Multi-Module Deployment

### ✅ Pros

1. **Atomic Deployments**: All resources deployed/destroyed together
2. **Simplified Dependencies**: KMS keys and S3 buckets managed in one place
3. **Single State File**: Easier to manage, no cross-state dependencies
4. **Consistent Tagging**: Common tags applied across all modules
5. **Coordinated Planning**: See all changes in one plan output
6. **Policy Validation**: OPA validates all resources together

### ⚠️ Considerations

1. **Blast Radius**: One bad config affects all modules in the deployment
2. **Sequential Processing**: `s3-deployment-manager.py` processes deployments one at a time
3. **State Lock**: Large deployments take longer, holding state lock
4. **KMS Key ARNs**: Must use placeholder first, then update after KMS keys are created

## When to Use vs. Separate Deployments

### ✅ Use Multi-Module When:
- Resources are tightly coupled (S3 bucket + its KMS key)
- Same lifecycle (deployed/destroyed together)
- Same team owns all resources
- Need atomic operations

### ✅ Use Separate Deployments When:
- Resources have different owners/teams
- Different update frequencies (one stable, one changes often)
- Need independent control
- Want to minimize blast radius

## Migration from Old Structure

Your old structure was missing `main.tf`. Now:

**Before:**
```
centerlized-pipline-/
├── providers.tf    ← AWS provider
├── variables.tf    ← Variables only
└── outputs.tf      ← Broken outputs (referenced non-existent modules)
```

**After:**
```
centerlized-pipline-/
├── main.tf         ← NEW: Calls S3/KMS/IAM modules
├── providers.tf    ← AWS provider
├── variables.tf    ← Added KMS + IAM variables
└── outputs.tf      ← Fixed: Outputs from actual modules
```

## Next Steps

1. **Review the examples**:
   - `templates/multi-module-example.tfvars` (S3 only)
   - `templates/complete-multi-module-example.tfvars` (S3 + KMS + IAM)

2. **Test with simple deployment**:
   - Start with S3 only
   - Add KMS keys
   - Add IAM resources

3. **Update existing tfvars**:
   - They still work! (S3 only deployments)
   - Optionally add `kms_keys` and `iam_users/iam_roles` sections

4. **Commit and test**:
   ```bash
   cd /Users/pragadeeswarpa/Desktop/Personal_DevOps/OPA-test/centerlized-pipline-
   git add main.tf variables.tf outputs.tf templates/
   git commit -m "feat: add multi-module support (S3 + KMS + IAM)"
   git push
   ```

## Validation

Run terraform validate:
```bash
cd centerlized-pipline-
terraform init -backend=false
terraform validate
```

Should show: ✅ Success! The configuration is valid.
