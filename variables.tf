# =============================================================================
# CENTRALIZED TERRAFORM PIPELINE - Variable Definitions
# =============================================================================
# Supports: S3 buckets, KMS keys, IAM users/roles/policies (multi-account).
# LLM RULES FOR TFVARS GENERATION:
#   1. Only set variables for the resources being deployed.
#   2. NEVER set: assume_role_name, terraform_session_name, yaml_config_file (controller-injected).
#   3. Map keys must be unique, lowercase, hyphens only (e.g. "my-bucket", "app-kms-key").
#   4. common_tags must always include: ManagedBy="terraform", Project, Environment, Owner.
# =============================================================================

# ---------------------------------------------------------------------------
# ACCOUNT — REQUIRED in every tfvars file
# ---------------------------------------------------------------------------
variable "accounts" {
  description = "REQUIRED. AWS account map — MUST be set in every tfvars file. Key = 12-digit account ID (e.g. '802860742843'). Fields: id (same 12-digit account ID), account_name (alias), environment ('development'|'staging'|'production'), regions (list of AWS regions). The workflow reads 'environment' from this block for branch mapping."
  type = map(object({
    id           = string
    account_name = string
    environment  = string
    regions      = list(string)
  }))
  default = {}
}

variable "aws_regions" {
  description = "Short-code to full-name region lookup used internally. Pre-populated (use1=us-east-1, usw2=us-west-2, ew1=eu-west-1). DO NOT SET IN TFVARS unless adding a non-default region."
  type = map(object({
    name = string
    code = string
  }))
  default = {
    "use1" = { name = "us-east-1", code = "use1" }
    "usw2" = { name = "us-west-2", code = "usw2" }
    "ew1"  = { name = "eu-west-1", code = "ew1"  }
  }
}

# ---------------------------------------------------------------------------
# S3 BUCKETS — Required: bucket_name, account_key, region_code
# ---------------------------------------------------------------------------
variable "s3_buckets" {
  description = "Map of S3 buckets to create. Key=logical name (e.g. 'app-data'). REQUIRED: bucket_name (globally unique, lowercase, no underscores), account_key (12-digit AWS account ID — NOT alias), region_code (SHORT CODE from aws_regions: 'use1' for us-east-1, 'usw2' for us-west-2, 'ew1' for eu-west-1). For KMS encryption: set encryption.sse_algorithm='aws:kms' and encryption.kms_master_key_id (full KMS ARN). bucket_policy and bucket_policy_file are mutually exclusive."
  type = map(object({
    bucket_name   = string
    account_key   = string      # 12-digit AWS account ID (e.g. "123456789123"), NOT the account name 
    region_code   = string      # SHORT CODE only: "use1" (us-east-1), "usw2" (us-west-2), "ew1" (eu-west-1). Must match a key in aws_regions variable.
    force_destroy = optional(bool, false)   # CONTROLLER-MANAGED: Do not set in tfvars

    # Versioning — set to true to protect against accidental deletion/overwrites
    versioning_enabled = optional(bool, null)

    # Encryption — omit for default AES-256, or provide KMS config below
    encryption = optional(object({
      sse_algorithm      = string           # "aws:kms" for KMS, "AES256" for S3-managed
      kms_master_key_id  = string           # Required when sse_algorithm = "aws:kms"; provide full KMS key ARN
      bucket_key_enabled = optional(bool, true)  # true = reduce KMS API call costs (recommended)
    }), null)

    # Bucket Policy — provide one of the two below, never both
    bucket_policy      = optional(string, null)   # Inline JSON string of the bucket policy
    bucket_policy_file = optional(string, null)   # Path to a .json policy file (relative to working dir)

    tags = optional(map(string), {})  # Merge with common_tags; include Owner, Environment, Project
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

# ---------------------------------------------------------------------------
# CONTROLLER-MANAGED — DO NOT SET IN TFVARS (auto-injected at runtime)
# ---------------------------------------------------------------------------
variable "assume_role_name" {
  description = "IAM role assumed for cross-account deployments. Default: TerraformExecutionRole. DO NOT SET IN TFVARS — controller-injected."
  type    = string
  default = "TerraformExecutionRole"
}

variable "terraform_session_name" {
  description = "AWS STS session name for cross-account role assumption. Format: team-env-deployment-id. DO NOT SET IN TFVARS — controller-injected at runtime."
  type    = string
  default = "terraform-deployment-session"
}

variable "yaml_config_file" {
  description = "Path to optional YAML config file (alternative input for s3_buckets/kms_keys/iam_*). Merged with tfvars; tfvars take precedence. Leave empty when all config is in tfvars. DO NOT SET IN TFVARS — controller-managed."
  type    = string
  default = ""
}

# ---------------------------------------------------------------------------
# COMMON TAGS — applied to ALL resources; merge with per-resource tags
# ---------------------------------------------------------------------------
variable "common_tags" {
  description = "Tags applied to every resource. Has defaults — DO NOT set in tfvars unless customizing. OPA-MANDATORY (pipeline will FAIL without these): ManagedBy='terraform', Project, Environment ('dev'|'staging'|'prod'), Owner. Optional: CostCenter, Application. Per-resource tags override on key conflict."
  type        = map(string)
  default = {
    ManagedBy   = "terraform"
    Project     = "S3-Management"
    Environment = "dev"
    Owner       = "DevOps-Team"
  }
}

variable "kms_key_id" {
  description = "ARN of an existing KMS key shared across all S3 buckets. Leave empty to create new keys via kms_keys or use default AES-256. e.g. 'arn:aws:kms:us-east-1:123456789012:key/mrk-abc123'"
  type    = string
  default = ""
}

variable "iam_role_name" {
  description = "Name of an existing IAM role that needs KMS/S3 access. Used to auto-grant encrypt/decrypt permissions when update_kms_policy=true. Leave empty if managing IAM via iam_roles variable."
  type    = string
  default = ""
}

variable "update_kms_policy" {
  description = "Set true to update the KMS key policy (kms_key_id) to grant iam_role_name encrypt/decrypt access. Requires both kms_key_id and iam_role_name to be set. Default: false."
  type    = bool
  default = false
}

# ---------------------------------------------------------------------------
# KMS KEYS — all fields optional; recommended: description, aliases, tags
# ---------------------------------------------------------------------------
variable "kms_keys" {
  description = "Map of KMS Customer Managed Keys to create. Key=logical name (e.g. 's3-encryption-key'). All fields optional. key_usage: 'ENCRYPT_DECRYPT'(default)|'SIGN_VERIFY'. key_spec: 'SYMMETRIC_DEFAULT'(default)|'RSA_2048'|'RSA_4096'. Always set description and aliases. For BYOK: origin='EXTERNAL'+key_material_base64. policy and policy_file are mutually exclusive."
  type = map(object({
    description              = optional(string)               # Purpose of this KMS key (used in AWS Console)
    key_usage                = optional(string, "ENCRYPT_DECRYPT")  # "ENCRYPT_DECRYPT" or "SIGN_VERIFY"
    key_spec                 = optional(string, "SYMMETRIC_DEFAULT") # Algorithm: "SYMMETRIC_DEFAULT", "RSA_2048", etc.
    multi_region             = optional(bool, false)           # true = create multi-region primary key
    deletion_window_in_days  = optional(number, 30)            # 7–30 days before key is permanently deleted
    enable_key_rotation      = optional(bool, true)            # Recommended: always true for compliance
    rotation_period_in_days  = optional(number, null)          # Custom rotation period (90–2560 days); null = annual
    prevent_destroy          = optional(bool, true)            # Prevent accidental key deletion via terraform destroy
    policy                   = optional(string)                # Inline JSON key policy string (use policy_file for large policies)
    policy_file              = optional(string)                # Path to JSON key policy file (relative to working dir)
    policy_content           = optional(string)                # Auto-resolved by controller; do not set in tfvars
    origin                   = optional(string, "AWS_KMS")     # "AWS_KMS" (default) or "EXTERNAL" for BYOK
    key_material_base64      = optional(string, null)          # Base64 key material for BYOK (origin = "EXTERNAL")
    valid_to                 = optional(string, null)          # Expiry for imported key material; format: "2026-12-31T23:59:59Z"
    custom_key_store_id      = optional(string, null)          # CloudHSM key store ID for XKS keys
    xks_key_id               = optional(string, null)          # External key ID for XKS-backed keys
    enable_separate_multiregion = optional(bool, false)        # Use separate resource for multi-region primary key
    replica_regions          = optional(list(string), [])      # List of regions to replicate multi-region key to
    ignore_changes_attributes = optional(list(string), [])     # Attributes to ignore lifecycle changes on
    aliases                  = optional(list(string), [])      # KMS alias names; example: ["alias/my-app-key"]
    grants = optional(list(object({
      name               = string           # Unique grant name within this key
      grantee_principal  = string           # ARN of IAM user, role, or service that receives the grant
      operations         = list(string)     # Allowed operations: ["Encrypt", "Decrypt", "GenerateDataKey", etc.]
      retiring_principal = optional(string) # ARN of principal allowed to retire the grant
      constraints = optional(object({
        encryption_context_equals = optional(map(string)) # Exact encryption context required for grant use
        encryption_context_subset = optional(map(string)) # Partial encryption context required for grant use
      }))
    })), [])
    tags = optional(map(string), {}) # Merged with common_tags; include Owner, Environment, Project
  }))
  default = {}
}

# ---------------------------------------------------------------------------
# IAM USERS — Required: name
# ---------------------------------------------------------------------------
variable "iam_users" {
  description = "Map of IAM users to create. Key=logical name (e.g. 'deploy-bot'). REQUIRED: name (actual IAM username). create_access_key=true for CI/CD bots; create_login_profile=true for human console users only. Attach managed policies by ARN via policies map {label=ARN}."
  type = map(object({
    name                    = string             # IAM username in AWS (e.g. "svc-deploy-bot")
    path                    = optional(string, "/")  # IAM path (e.g. "/service-accounts/"); default "/"
    permissions_boundary    = optional(string)   # ARN of IAM policy to use as permissions boundary
    force_destroy           = optional(bool, false)  # Delete credentials on destroy; default false
    create_access_key       = optional(bool, false)  # true = create programmatic access key
    create_login_profile    = optional(bool, false)  # true = create console login (human users only)
    password_reset_required = optional(bool, true)   # Force password change on first login
    password_length         = optional(number, 20)   # Auto-generated password length; min 8
    pgp_key                 = optional(string)        # Base64 PGP key to encrypt access key secret
    policies                = optional(map(string), {}) # Map of policy ARNs to attach; key=name, value=ARN
    tags                    = optional(map(string), {}) # Merged with common_tags
  }))
  default = {}
}

# ---------------------------------------------------------------------------
# IAM ROLES — Required: name, assume_role_policy
# ---------------------------------------------------------------------------
variable "iam_roles" {
  description = "Map of IAM roles to create. Key=logical name (e.g. 'lambda-execution'). REQUIRED: name (actual IAM role name), assume_role_policy (inline JSON trust policy string OR path to .json file). Attach managed policies via policies map {label=ARN}. Embed permissions via inline_policies list [{name, policy|policy_file}]."
  type = map(object({
    name                    = string              # IAM role name in AWS
    path                    = optional(string, "/")  # IAM path; default "/"
    description             = optional(string)    # Purpose of this role (shown in AWS Console)
    assume_role_policy      = string              # Trust policy: inline JSON string OR path to .json file
    permissions_boundary    = optional(string)    # ARN of boundary policy
    max_session_duration    = optional(number, 3600)  # Session duration in seconds; 3600–43200
    policies                = optional(map(string), {}) # Managed policy ARNs to attach; key=name, value=ARN
    inline_policies         = optional(list(object({
      name        = string                        # Unique policy name within this role
      policy      = optional(string, null)        # Inline JSON policy document string
      policy_file = optional(string, null)        # Path to JSON policy file (alternative to inline policy)
    })), [])
    tags                    = optional(map(string), {}) # Merged with common_tags
  }))
  default = {}
}

# ---------------------------------------------------------------------------
# IAM POLICIES (standalone managed) — Required: name
# ---------------------------------------------------------------------------
variable "iam_policies" {
  description = "Map of standalone IAM managed policies to create. Key=logical name (e.g. 's3-read-policy'). REQUIRED: name (actual policy name, unique per account). Provide policy via policy_document (inline JSON) OR policy_file (path to .json) — mutually exclusive. Reference via role_policy_attachments using policy_type='customer_managed'."
  type = map(object({
    name            = string                      # IAM policy name in AWS
    path            = optional(string, "/")       # IAM path; default "/"
    description     = optional(string)            # Human-readable policy description
    policy_document = optional(string, null)      # Inline JSON policy string (mutually exclusive with policy_file)
    policy_file     = optional(string, null)      # Path to JSON policy file (mutually exclusive with policy_document)
    tags            = optional(map(string), {})   # Merged with common_tags
  }))
  default = {}
}

# ---------------------------------------------------------------------------
# IAM ROLE POLICY ATTACHMENTS — Required: role_key, policy_type
# ---------------------------------------------------------------------------
variable "role_policy_attachments" {
  description = "Map of policy-to-role attachments. Key=logical label (e.g. 'lambda-role-s3-read'). REQUIRED: role_key (key from iam_roles), policy_type ('customer_managed'|'aws_managed'). For customer_managed: set policy_key (key from iam_policies). For aws_managed: set policy_arn (full ARN e.g. 'arn:aws:iam::aws:policy/AmazonS3ReadOnlyAccess')."
  type = map(object({
    role_key    = string                       # Key from iam_roles map that identifies the target role
    policy_key  = optional(string, null)       # Key from iam_policies map (for customer_managed policies)
    policy_arn  = optional(string, null)       # Full ARN of AWS managed policy (for aws_managed policies)
    policy_type = string                       # "customer_managed" or "aws_managed"
  }))
  default = {}
}

