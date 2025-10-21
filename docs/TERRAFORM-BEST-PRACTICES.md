# Terraform Best Practices - File Organization

## ✅ Proper Structure (Current)

```
centerlized-pipline-/
├── main.tf              # Resources, modules, data sources, locals
├── variables.tf         # All variable declarations
├── outputs.tf           # All output declarations
├── providers.tf         # Provider configurations
├── terraform.tfvars     # Variable values (gitignored)
└── versions.tf          # Terraform and provider version constraints (optional)
```

## File Responsibilities

### 1. `main.tf` - Core Configuration

**Purpose**: Define resources, modules, data sources, and local values

**Should contain:**
- `terraform {}` block (version constraints)
- `data` sources
- `locals` blocks
- `resource` blocks
- `module` blocks

**Should NOT contain:**
- ❌ `variable` declarations
- ❌ `output` declarations
- ❌ `provider` configurations (keep in providers.tf)

**Example:**
```hcl
# main.tf

terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.7"
    }
  }
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  environment = "production"
  tags = merge(var.common_tags, {
    Environment = local.environment
  })
}

module "s3" {
  source = "../tf-module/Module/S3"
  
  common_tags = local.tags
  s3_buckets  = var.s3_buckets
}

module "kms" {
  for_each = var.kms_keys
  
  source = "../tf-module/Module/KMS"
  
  description = each.value.description
  tags        = local.tags
}
```

### 2. `variables.tf` - Input Variables

**Purpose**: Declare all input variables

**Should contain:**
- Only `variable` blocks
- Variable descriptions
- Variable types
- Default values
- Validation rules

**Should NOT contain:**
- ❌ Resources
- ❌ Modules
- ❌ Outputs
- ❌ Variable values (those go in terraform.tfvars)

**Example:**
```hcl
# variables.tf

variable "common_tags" {
  description = "Common tags to be applied to all resources"
  type        = map(string)
  default = {
    ManagedBy = "terraform"
  }
}

variable "s3_buckets" {
  description = "Map of S3 buckets to create"
  type = map(object({
    bucket_name        = string
    versioning_enabled = optional(bool, true)
    encryption = optional(object({
      sse_algorithm     = string
      kms_master_key_id = string
    }))
  }))
  default = {}
  
  validation {
    condition = alltrue([
      for k, v in var.s3_buckets : v.encryption != null
    ])
    error_message = "All S3 buckets must have encryption configured."
  }
}

variable "kms_keys" {
  description = "Map of KMS keys to create"
  type = map(object({
    description         = string
    enable_key_rotation = optional(bool, true)
  }))
  default = {}
}
```

### 3. `outputs.tf` - Output Values

**Purpose**: Declare all output values

**Should contain:**
- Only `output` blocks
- Output descriptions
- Output values from resources/modules
- Sensitive flags

**Should NOT contain:**
- ❌ Resources
- ❌ Modules
- ❌ Variables
- ❌ Data sources

**Example:**
```hcl
# outputs.tf

output "deployment_summary" {
  description = "Summary of deployed resources"
  value = {
    account_id = data.aws_caller_identity.current.account_id
    region     = data.aws_region.current.name
    s3_buckets = length(var.s3_buckets)
    kms_keys   = length(var.kms_keys)
  }
}

output "s3_bucket_arns" {
  description = "Map of S3 bucket ARNs"
  value = {
    for k, v in module.s3.s3_buckets : k => v.arn
  }
}

output "kms_key_ids" {
  description = "Map of KMS key IDs"
  value = {
    for k, v in module.kms : k => v.key_id
  }
}

output "kms_key_arns" {
  description = "Map of KMS key ARNs for S3 bucket configuration"
  value = {
    for k, v in module.kms : k => v.key_arn
  }
}

output "iam_access_keys" {
  description = "IAM access key secrets"
  value       = module.iam.access_key_secrets
  sensitive   = true  # Don't show in plan/apply output
}
```

### 4. `providers.tf` - Provider Configuration

**Purpose**: Configure providers

**Should contain:**
- `provider` blocks
- Provider aliases
- Provider authentication
- Backend configuration

**Example:**
```hcl
# providers.tf

terraform {
  backend "s3" {
    bucket  = "terraform-state-bucket"
    encrypt = true
    
    assume_role = {
      role_arn     = "arn:aws:iam::123456789012:role/TerraformRole"
      session_name = "terraform-backend"
    }
  }
}

provider "aws" {
  region = "us-east-1"
  
  assume_role {
    role_arn     = "arn:aws:iam::123456789012:role/TerraformRole"
    session_name = "terraform-session"
  }
  
  default_tags {
    tags = var.common_tags
  }
}

# Secondary region provider
provider "aws" {
  alias  = "us_west_2"
  region = "us-west-2"
  
  assume_role {
    role_arn = "arn:aws:iam::123456789012:role/TerraformRole"
  }
}
```

### 5. `terraform.tfvars` - Variable Values (Optional)

**Purpose**: Set variable values

**Should contain:**
- Variable value assignments
- Environment-specific values

**Should be:**
- ⚠️ Gitignored (if contains sensitive data)
- Or use `*.auto.tfvars` for auto-loading

**Example:**
```hcl
# terraform.tfvars (or dev.tfvars, prod.tfvars)

common_tags = {
  Environment = "production"
  Project     = "my-app"
  Owner       = "platform-team"
}

s3_buckets = {
  "app-data" = {
    bucket_name        = "my-app-data-prod"
    versioning_enabled = true
    encryption = {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = "arn:aws:kms:us-east-1:123456789012:key/abc-123"
    }
  }
}

kms_keys = {
  "app-key" = {
    description         = "Encryption key for application data"
    enable_key_rotation = true
  }
}
```

## Why This Separation?

### ✅ Benefits

1. **Readability**: Each file has a clear purpose
2. **Maintainability**: Easy to find what you're looking for
3. **Collaboration**: Multiple people can work on different files
4. **Version Control**: Cleaner diffs, easier code reviews
5. **Reusability**: Variables and outputs clearly defined
6. **CI/CD**: Easier to generate documentation automatically

### ❌ Anti-Patterns

**Don't do this:**
```hcl
# main.tf (BAD - everything in one file)

variable "bucket_name" {
  type = string
}

resource "aws_s3_bucket" "this" {
  bucket = var.bucket_name
}

output "bucket_arn" {
  value = aws_s3_bucket.this.arn
}

provider "aws" {
  region = "us-east-1"
}
```

**Do this instead:**
```hcl
# variables.tf
variable "bucket_name" {
  type = string
}

# main.tf
resource "aws_s3_bucket" "this" {
  bucket = var.bucket_name
}

# outputs.tf
output "bucket_arn" {
  value = aws_s3_bucket.this.arn
}

# providers.tf
provider "aws" {
  region = "us-east-1"
}
```

## Output Organization Best Practices

### Group outputs logically

```hcl
# outputs.tf

# =============================================================================
# DEPLOYMENT SUMMARY
# =============================================================================

output "deployment_summary" { ... }

# =============================================================================
# S3 OUTPUTS
# =============================================================================

output "s3_buckets" { ... }
output "s3_bucket_arns" { ... }
output "s3_bucket_names" { ... }

# =============================================================================
# KMS OUTPUTS  
# =============================================================================

output "kms_keys" { ... }
output "kms_key_ids" { ... }
output "kms_key_arns" { ... }

# =============================================================================
# IAM OUTPUTS
# =============================================================================

output "iam_users" { ... }
output "iam_roles" { ... }

# =============================================================================
# SENSITIVE OUTPUTS
# =============================================================================

output "iam_access_keys" {
  value     = ...
  sensitive = true
}
```

### Output naming conventions

```hcl
# Good naming
output "s3_bucket_arns"       # Plural, descriptive
output "kms_key_ids"          # Plural, clear purpose
output "deployment_summary"   # Clear intent

# Avoid
output "buckets"              # Too vague
output "output1"              # Not descriptive
output "data"                 # Too generic
```

### Output descriptions

```hcl
# Good descriptions
output "kms_key_arns" {
  description = "Map of KMS key ARNs for S3 bucket encryption configuration"
  value       = { for k, v in module.kms : k => v.key_arn }
}

# Not helpful
output "kms_key_arns" {
  description = "KMS keys"  # Too vague
  value       = { for k, v in module.kms : k => v.key_arn }
}
```

## What We Fixed

### Before (Wrong):
```hcl
# main.tf
module "s3" { ... }
module "kms" { ... }
module "iam" { ... }

output "s3_buckets" { ... }        # ❌ Outputs in main.tf
output "kms_keys" { ... }          # ❌ Outputs in main.tf
output "deployment_summary" { ... } # ❌ Outputs in main.tf
```

### After (Correct):
```hcl
# main.tf
module "s3" { ... }
module "kms" { ... }
module "iam" { ... }
# No outputs here ✅

# outputs.tf
output "deployment_summary" { ... }  # ✅ All outputs here
output "s3_buckets" { ... }          # ✅
output "kms_keys" { ... }            # ✅
```

## Terraform Command Impact

### terraform plan
```bash
# Reads:
- main.tf        (resources, modules, data)
- variables.tf   (variable declarations)
- providers.tf   (provider config)
- terraform.tfvars (variable values)

# Displays:
- outputs.tf     (shows what outputs will be created)
```

### terraform apply
```bash
# Creates resources from main.tf
# Sets output values from outputs.tf
```

### terraform output
```bash
# Only reads outputs.tf
$ terraform output
$ terraform output s3_bucket_arns
$ terraform output -json
```

## Documentation Generation

Many tools auto-generate docs from structure:

```bash
# terraform-docs
terraform-docs markdown table . > README.md

# Generates sections:
- Providers (from providers.tf)
- Inputs (from variables.tf)  
- Outputs (from outputs.tf)
- Resources (from main.tf)
```

## Summary

| File | Purpose | Contains | Does NOT Contain |
|------|---------|----------|------------------|
| `main.tf` | Core logic | `data`, `locals`, `resource`, `module` | `variable`, `output`, `provider` |
| `variables.tf` | Input declarations | `variable` only | Resources, outputs, values |
| `outputs.tf` | Output declarations | `output` only | Resources, modules, variables |
| `providers.tf` | Provider config | `provider`, `backend` | Resources, outputs |
| `terraform.tfvars` | Variable values | Variable assignments | Declarations |

**Golden Rule**: One concern per file. Keep it clean, keep it organized! 🎯
