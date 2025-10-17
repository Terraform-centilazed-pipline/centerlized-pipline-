# S3 Bucket Template - Simple Application Data
# Generated: {{GENERATION_DATE}}
# Account: {{ACCOUNT_NAME}} ({{ACCOUNT_ID}})
# Region: {{REGION}}
# Project: {{PROJECT_NAME}}

accounts = {
  "{{ACCOUNT_ID}}" = {
    id           = "{{ACCOUNT_ID}}"
    account_id   = "{{ACCOUNT_ID}}"
    account_name = "{{ACCOUNT_NAME}}"
    environment  = "{{ENVIRONMENT}}"
    regions      = ["{{REGION}}"]
  }
}

s3_buckets = {
  "{{BUCKET_KEY}}" = {
    bucket_name        = "{{BUCKET_NAME}}"
    account_key        = "{{ACCOUNT_ID}}"
    region_code        = "{{REGION_CODE}}"
    force_destroy      = {{FORCE_DESTROY}}
    versioning_enabled = {{VERSIONING_ENABLED}}
    bucket_policy_file = "accounts/{{ACCOUNT_NAME}}/{{REGION}}/{{PROJECT_NAME}}/{{BUCKET_KEY}}.json"
    
    encryption = {
      sse_algorithm      = "aws:kms"
      kms_master_key_id  = "{{KMS_KEY_ID}}"  # Explicit KMS key ARN required for every region
      bucket_key_enabled = true
    }
    
    # VPC Endpoint Configuration (for reference only)
    # Interface VPC Endpoint: {{VPC_INTERFACE_ENDPOINT}}
    # Gateway VPC Endpoint: {{VPC_GATEWAY_ENDPOINT}}
    # Policy uses: {{VPC_ENDPOINT_TYPE}} endpoint ({{VPC_ENDPOINT_ID}})
    
    # Public Access Block - Always enabled for secure buckets
    public_access_block = {
      block_public_acls       = true
      block_public_policy     = true
      ignore_public_acls      = true
      restrict_public_buckets = true
    }
    
    tags = {
      Name        = "{{BUCKET_NAME}}"
      ManagedBy   = "terraform"
      Project     = "{{PROJECT_NAME}}"
      Environment = "{{ENVIRONMENT}}"
      Owner       = "{{OWNER}}"
      CostCenter  = "{{COST_CENTER}}"
      Account     = "{{ACCOUNT_ID}}"
      Region      = "{{REGION}}"
      VPCAccess   = "true"
      AccessType  = "vpc-endpoint-only"
    }
  }
}

# Common Tags
common_tags = {
  ManagedBy   = "terraform"
  Project     = "{{PROJECT_NAME}}"
  Environment = "{{ENVIRONMENT}}"
  Owner       = "{{OWNER}}"
  CostCenter  = "{{COST_CENTER}}"
  Account     = "{{ACCOUNT_NAME}}"
  Region      = "{{REGION}}"
}