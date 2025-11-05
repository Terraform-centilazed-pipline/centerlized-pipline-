package terraform.s3

import rego.v1

# =============================================================================
# TERRAFORM S3 PLAN VALIDATION POLICY v4.0.0 - ENHANCED SECURITY
# =============================================================================
# 
# Validates S3 resource configurations in Terraform plans against enterprise
# security standards and golden template compliance.
#
# SECURITY APPROACH:
# - Block all Allow statements in bucket policies (zero trust)
# - Enforce golden template: exactly 3 Deny statements
# - Require VPC endpoint access only
# - Mandate KMS encryption with explicit key ARNs
# - Enforce compliance tags and naming conventions
#
# DOCUMENTATION: See docs/S3-SECURITY-POLICY-GUIDE.md for detailed usage guide
# =============================================================================

# --- GOLDEN TEMPLATE STRUCTURE DEFINITIONS ---

# Expected golden policy structure (3 required statements)
golden_policy_structure := {
    "version": "2012-10-17",
    "required_statements": [
        {
            "effect": "Deny",
            "actions": ["s3:PutObject", "s3:GetObject", "s3:DeleteObject"],
            "condition_type": "ArnNotLike",
            "condition_key": "aws:PrincipalArn",
            "description": "Principal restriction statement"
        },
        {
            "effect": "Deny", 
            "actions": ["s3:PutObject", "s3:GetObject", "s3:DeleteObject"],
            "condition_type": "StringNotEquals",
            "condition_key": "aws:SourceVpce",
            "description": "VPC endpoint restriction statement"
        },
        {
            "effect": "Deny",
            "actions": ["s3:PutObject"],
            "condition_type": "StringNotEquals", 
            "condition_key": "s3:x-amz-server-side-encryption-aws-kms-key-id",
            "description": "KMS encryption requirement statement"
        }
    ]
}

# Expected golden tfvars structure
golden_tfvars_structure := {
    "required_fields": [
        "accounts",
        "s3_buckets", 
        "common_tags"
    ],
    "bucket_required_fields": [
        "bucket_name",
        "account_key", 
        "region_code",
        "force_destroy",
        "versioning_enabled",
        "bucket_policy_file",
        "encryption",
        "public_access_block",
        "tags"
    ],
    "encryption_required_fields": [
        "sse_algorithm",
        "kms_master_key_id",
        "bucket_key_enabled"
    ],
    "required_encryption_values": {
        "sse_algorithm": "aws:kms",
        "bucket_key_enabled": true
    },
    "public_access_block_required": {
        "block_public_acls": true,
        "block_public_policy": true, 
        "ignore_public_acls": true,
        "restrict_public_buckets": true
    },
    "required_tags": [
        "Name", "ManagedBy", "Project", "Environment", "Owner", 
        "CostCenter", "Account", "Region", "VPCAccess", "AccessType"
    ],
    "required_tag_values": {
        "ManagedBy": "terraform",
        "VPCAccess": "true",
        "AccessType": "vpc-endpoint-only"
    }
}

# =============================================================================
# TERRAFORM PLAN VALIDATION - CORRECT APPROACH
# =============================================================================
# Validate S3 resource configuration in Terraform plan
# Focus on: bucket settings, encryption, tags, public access, naming
# NOT policy document content (that's handled separately)

# Validate S3 bucket configuration
violations[msg] if {
    some i
    resource := input.resource_changes[i]
    resource.type == "aws_s3_bucket"
    some action in resource.change.actions
    action in ["create", "update"]
    
    bucket_config := resource.change.after
    
    # Check bucket naming convention
    not valid_bucket_name(bucket_config.bucket)
    
    msg := {
        "policy": "terraform.s3.bucket_naming_violation",
        "severity": "high",
        "resource": resource.address,
        "message": sprintf("S3 bucket name '%s' does not follow naming convention", [bucket_config.bucket]),
        "remediation": "Bucket name must follow pattern: {account}-{project}-{region}-{environment}",
        "current_value": bucket_config.bucket
    }
}

# Validate S3 bucket encryption
violations[msg] if {
    some i
    resource := input.resource_changes[i]
    resource.type == "aws_s3_bucket_server_side_encryption_configuration"
    some action in resource.change.actions
    action in ["create", "update"]
    
    encryption_config := resource.change.after
    
    # Check if KMS encryption is enabled
    not kms_encryption_enabled(encryption_config)
    
    msg := {
        "policy": "terraform.s3.encryption_not_kms",
        "severity": "critical",
        "resource": resource.address,
        "message": "S3 bucket must use KMS encryption",
        "remediation": "Set sse_algorithm to 'aws:kms' and provide kms_master_key_id",
        "security_risk": "Unencrypted or AES256 encrypted buckets are not compliant"
    }
}

# Validate S3 public access block
violations[msg] if {
    some i
    resource := input.resource_changes[i]
    resource.type == "aws_s3_bucket_public_access_block"
    some action in resource.change.actions
    action in ["create", "update"]
    
    public_access := resource.change.after
    
    # Check if all public access is blocked
    not all_public_access_blocked(public_access)
    
    msg := {
        "policy": "terraform.s3.public_access_not_blocked",
        "severity": "critical",
        "resource": resource.address,
        "message": "S3 bucket must block all public access",
        "remediation": "Set all public access block options to true",
        "current_config": public_access
    }
}

# Validate S3 bucket tags
violations[msg] if {
    some i
    resource := input.resource_changes[i]
    resource.type == "aws_s3_bucket"
    some action in resource.change.actions
    action in ["create", "update"]
    
    bucket_config := resource.change.after
    
    # Check required tags
    missing_tags := missing_required_tags(bucket_config.tags)
    count(missing_tags) > 0
    
    msg := {
        "policy": "terraform.s3.missing_required_tags",
        "severity": "medium",
        "resource": resource.address,
        "message": sprintf("S3 bucket missing required tags: %v", [missing_tags]),
        "remediation": "Add all required tags to bucket configuration",
        "missing_tags": missing_tags,
        "required_tags": ["Name", "Environment", "Project", "ManagedBy"]
    }
}

# Validate S3 bucket policy exists and follows golden template
violations[msg] if {
    some i
    resource := input.resource_changes[i]
    resource.type == "aws_s3_bucket_policy"
    some action in resource.change.actions
    action in ["create", "update"]
    
    policy_string := resource.change.after.policy
    bucket_key := extract_bucket_from_address(resource.address)
    
    # Basic validation - ensure policy exists and is not empty
    not policy_string
    
    msg := {
        "policy": "terraform.s3.missing_bucket_policy",
        "severity": "critical",
        "resource": resource.address,
        "bucket": bucket_key,
        "message": sprintf("S3 bucket policy missing for %s", [bucket_key]),
        "remediation": "Bucket must have a policy that follows golden template structure",
        "security_risk": "Bucket without policy may allow unauthorized access"
    }
}

# --- CRITICAL SECURITY VALIDATION RULES ---

# CRITICAL: Validate against dangerous Allow statements
# This is the most important security check - prevents public bucket access
violations[msg] if {
    some i
    resource := input.resource_changes[i]
    resource.type == "aws_s3_bucket_policy"
    some action in resource.change.actions
    action in ["create", "update"]
    
    policy_string := resource.change.after.policy
    bucket_key := extract_bucket_from_address(resource.address)
    
    # Ensure policy exists
    policy_string
    
    # SECURITY CHECK: Detect dangerous Allow statements
    dangerous_allows := detect_dangerous_allow_statements(policy_string)
    count(dangerous_allows) > 0
    
    msg := {
        "policy": "terraform.s3.dangerous_allow_statements",
        "severity": "critical",
        "resource": resource.address,
        "bucket": bucket_key,
        "message": sprintf("SECURITY VIOLATION: Bucket %s policy contains dangerous Allow statements", [bucket_key]),
        "dangerous_statements": dangerous_allows,
        "remediation": "Remove all Allow statements. Use only Deny statements with VPC endpoint and principal restrictions",
        "security_risk": "Allow statements can grant unauthorized public access to S3 bucket",
        "template_reference": "Use golden template from /templates/s3-bucket-policy.json"
    }
}

# CRITICAL SECURITY: Validate bucket policy matches golden template structure
violations[msg] if {
    some i
    resource := input.resource_changes[i]
    resource.type == "aws_s3_bucket_policy"
    some action in resource.change.actions
    action in ["create", "update"]
    
    policy_string := resource.change.after.policy
    bucket_key := extract_bucket_from_address(resource.address)
    
    # Ensure policy exists
    policy_string
    
    # Basic validation - check if policy can be parsed and has basic structure
    not valid_policy_structure(policy_string)
    
    msg := {
        "policy": "terraform.s3.policy_structure_invalid",
        "severity": "critical", 
        "resource": resource.address,
        "bucket": bucket_key,
        "message": sprintf("S3 bucket policy for %s does not follow golden template structure", [bucket_key]),
        "remediation": "Policy must follow golden template with required Deny statements for security",
        "template_reference": "Use golden template from /templates/s3-bucket-policy.json"
    }
}

# CRITICAL SECURITY: Enforce golden template compliance
violations[msg] if {
    some i
    resource := input.resource_changes[i]
    resource.type == "aws_s3_bucket_policy"
    some action in resource.change.actions
    action in ["create", "update"]
    
    policy_string := resource.change.after.policy
    bucket_key := extract_bucket_from_address(resource.address)
    
    # Ensure policy exists and is structurally valid
    policy_string
    valid_policy_structure(policy_string)
    
    # SECURITY CHECK: Must follow golden template pattern
    not follows_golden_template_pattern(policy_string)
    
    msg := {
        "policy": "terraform.s3.golden_template_violation",
        "severity": "critical",
        "resource": resource.address,
        "bucket": bucket_key,
        "message": sprintf("SECURITY VIOLATION: Bucket %s policy does not follow mandatory golden template", [bucket_key]),
        "remediation": "Policy must have exactly 3 Deny statements: Principal restriction, VPC endpoint restriction, and encryption enforcement",
        "security_risk": "Non-compliant policies may allow unauthorized access or unencrypted data",
        "template_reference": "Use golden template from /templates/s3-bucket-policy.json"
    }
}

# =============================================================================
# TERRAFORM PLAN VALIDATION HELPER FUNCTIONS
# =============================================================================

# Validate encryption configuration against golden template
violations[msg] if {
    some i
    resource := input.resource_changes[i]
    resource.type == "aws_s3_bucket_server_side_encryption_configuration"
    # Check for both create and update actions
    some action in resource.change.actions
    action in ["create", "update"]
    
    bucket_key := extract_bucket_from_address(resource.address)
    
    # Check if encryption matches golden template requirements
    encryption_violations := validate_encryption_against_golden_template(resource)
    count(encryption_violations) > 0
    
    msg := {
        "policy": "terraform.s3.golden_template.encryption_mismatch",
        "severity": "critical",
        "resource": resource.address, 
        "bucket": bucket_key,
        "message": sprintf("Bucket %s encryption does not match golden template requirements", [bucket_key]),
        "encryption_violations": encryption_violations,
        "remediation": "Set sse_algorithm to aws:kms, provide explicit KMS key ARN, enable bucket_key_enabled",
        "security_risk": "Non-compliant encryption settings may not meet security standards",
        "template_reference": "/templates/s3-bucket.tfvars"
    }
}

# Validate public access block against golden template
violations[msg] if {
    some i
    resource := input.resource_changes[i]
    resource.type == "aws_s3_bucket_public_access_block"
    # Check for both create and update actions
    some action in resource.change.actions
    action in ["create", "update"]
    
    bucket_key := extract_bucket_from_address(resource.address)
    
    # Check if public access block matches golden template
    pab_violations := validate_pab_against_golden_template(resource)
    count(pab_violations) > 0
    
    msg := {
        "policy": "terraform.s3.golden_template.public_access_block_mismatch",
        "severity": "critical",
        "resource": resource.address,
        "bucket": bucket_key, 
        "message": sprintf("Bucket %s public access block does not match golden template", [bucket_key]),
        "pab_violations": pab_violations,
        "remediation": "Set all public access block options to true as per golden template",
        "security_risk": "Incorrect public access settings may allow unintended public access",
        "template_reference": "/templates/s3-bucket.tfvars"
    }
}

# Validate tags against golden template
violations[msg] if {
    some i
    resource := input.resource_changes[i]
    resource.type == "aws_s3_bucket"
    # Check for both create and update actions
    some action in resource.change.actions
    action in ["create", "update"]
    
    bucket_key := extract_bucket_from_address(resource.address)
    
    # Check if tags match golden template requirements
    tag_violations := validate_tags_against_golden_template(resource)
    count(tag_violations) > 0
    
    msg := {
        "policy": "terraform.s3.golden_template.tags_mismatch",
        "severity": "medium",
        "resource": resource.address,
        "bucket": bucket_key,
        "message": sprintf("Bucket %s tags do not match golden template requirements", [bucket_key]),
        "tag_violations": tag_violations,
        "remediation": "Add all required tags with correct values as specified in golden template",
        "security_risk": "Missing or incorrect tags affect compliance and access control",
        "template_reference": "/templates/s3-bucket.tfvars"
    }
}

# =============================================================================
# TERRAFORM PLAN VALIDATION HELPER FUNCTIONS
# =============================================================================

# Check if bucket name follows naming convention
valid_bucket_name(bucket_name) if {
    # Pattern: {prefix}-{project}-{region-code}-{environment}
    regex.match("^[a-z0-9][a-z0-9-]+[a-z0-9]$", bucket_name)
    not regex.match(".*--.*", bucket_name)  # No consecutive hyphens
    count(bucket_name) >= 3
    count(bucket_name) <= 63
}

# Check if KMS encryption is properly configured
kms_encryption_enabled(encryption_config) if {
    some rule in encryption_config.rule
    rule.apply_server_side_encryption_by_default.sse_algorithm == "aws:kms"
    rule.apply_server_side_encryption_by_default.kms_master_key_id != null
    rule.apply_server_side_encryption_by_default.kms_master_key_id != ""
}

# Check if all public access is blocked
all_public_access_blocked(public_access_config) if {
    public_access_config.block_public_acls == true
    public_access_config.block_public_policy == true
    public_access_config.ignore_public_acls == true
    public_access_config.restrict_public_buckets == true
}

# Check for missing required tags
missing_required_tags(tags) := missing if {
    required_tags := {"Name", "Environment", "Project", "ManagedBy"}
    provided_tags := {tag | tags[tag]}
    missing := required_tags - provided_tags
}

# Check if tags have correct values
validate_tag_values(tags) := violations if {
    violations := [
        {"tag": "ManagedBy", "expected": "terraform", "actual": tags.ManagedBy} |
        tags.ManagedBy != "terraform"
    ]
}

# Basic policy structure validation (without deep content parsing)
valid_policy_structure(policy_string) if {
    # Try to parse the policy JSON
    policy_doc := json.unmarshal(policy_string)
    
    # Basic structure checks
    policy_doc.Version == "2012-10-17"
    is_array(policy_doc.Statement)
    count(policy_doc.Statement) >= 1
    
    # Check that statements have basic required fields
    every statement in policy_doc.Statement {
        statement.Effect
        statement.Action
    }
}

# --- SECURITY HELPER FUNCTIONS ---

# Check if policy follows golden template pattern (STRICT ENFORCEMENT)
# Returns: true only if policy meets ALL golden template requirements
follows_golden_template_pattern(policy_string) if {
    policy_doc := json.unmarshal(policy_string)
    
    # REQUIREMENT 1: Must have exactly 3 statements (golden template requirement)
    count(policy_doc.Statement) == 3
    
    # REQUIREMENT 2: ALL statements must be Deny (no Allow statements permitted)
    every statement in policy_doc.Statement {
        statement.Effect == "Deny"
    }
    
    # REQUIREMENT 3: Must have required statement types
    has_principal_restriction(policy_doc)
    has_vpc_endpoint_restriction(policy_doc) 
    has_encryption_enforcement(policy_doc)
    
    # REQUIREMENT 4: No public access statements
    not has_public_access_statements(policy_doc)
}

# CRITICAL SECURITY: Detect dangerous Allow statements
detect_dangerous_allow_statements(policy_string) := dangerous_statements if {
    policy_doc := json.unmarshal(policy_string)
    
    dangerous_statements := [statement_info |
        some statement in policy_doc.Statement
        statement.Effect == "Allow"
        
        # Check for dangerous patterns
        danger_type := get_danger_type(statement)
        
        statement_info := {
            "effect": statement.Effect,
            "actions": statement.Action,
            "principal": object.get(statement, "Principal", ""),
            "danger_type": danger_type,
            "risk_level": get_risk_level(statement)
        }
    ]
}

# SECURITY HELPER: Determine danger type of Allow statement
get_danger_type(statement) := danger_type if {
    # Public access via wildcard principal
    statement.Principal == "*"
    danger_type := "public_access_wildcard"
} else := danger_type if {
    # Public access via AWS service principal
    contains(statement.Principal, "AWS")
    contains(statement.Principal, "*")
    danger_type := "public_access_aws_wildcard" 
} else := danger_type if {
    # Any Allow statement is potentially dangerous
    danger_type := "allow_statement_detected"
}

# SECURITY HELPER: Determine risk level
get_risk_level(statement) := "critical" if {
    statement.Principal == "*"
} else := "high" if {
    contains(statement.Principal, "*")
} else := "medium"

# SECURITY HELPER: Check for principal restriction statement
has_principal_restriction(policy_doc) if {
    some statement in policy_doc.Statement
    statement.Effect == "Deny"
    
    # Must have condition checking principal ARN
    condition := statement.Condition
    condition.ArnNotLike["aws:PrincipalArn"]
}

# SECURITY HELPER: Check for VPC endpoint restriction statement  
has_vpc_endpoint_restriction(policy_doc) if {
    some statement in policy_doc.Statement
    statement.Effect == "Deny"
    
    # Must have condition checking VPC endpoint
    condition := statement.Condition
    condition.StringNotEquals["aws:SourceVpce"]
}

# SECURITY HELPER: Check for encryption enforcement statement
has_encryption_enforcement(policy_doc) if {
    some statement in policy_doc.Statement
    statement.Effect == "Deny"
    
    # Must have condition checking encryption
    condition := statement.Condition
    condition.StringNotEquals["s3:x-amz-server-side-encryption"]
}

# SECURITY HELPER: Check for dangerous public access statements
has_public_access_statements(policy_doc) if {
    some statement in policy_doc.Statement
    statement.Principal == "*"
} else if {
    some statement in policy_doc.Statement
    contains(statement.Principal, "*")
}

# =============================================================================
# MAIN.REGO INTEGRATION - DENY RULE  
# =============================================================================

# Return violations directly to maintain object structure
deny := violations

# Extract module key from resource address  
extract_bucket_from_address(address) := bucket_key if {
    parts := split(address, "[\"")
    count(parts) == 2
    end_parts := split(parts[1], "\"]")
    bucket_key := end_parts[0]
}

# Validate encryption configuration against golden template
validate_encryption_against_golden_template(resource) := violations if {
    config := resource.change.after
    
    violations := [violation |
        some rule in config.rule
        some encryption in rule.apply_server_side_encryption_by_default
        
        # Check algorithm
        algorithm_issue := [issue |
            encryption.sse_algorithm != "aws:kms"
            issue := sprintf("sse_algorithm must be 'aws:kms', found: %s", [encryption.sse_algorithm])
        ]
        
        # Check KMS key is provided and not empty
        kms_key_issue := [issue |
            kms_key := object.get(encryption, "kms_master_key_id", "")
            kms_key == ""
            issue := "kms_master_key_id must be provided with explicit KMS key ARN"
        ]
        
        # Check bucket key enabled - look at rule level  
        bucket_key_issue := [issue |
            bucket_key_enabled := object.get(rule, "bucket_key_enabled", false)
            bucket_key_enabled != true
            issue := "bucket_key_enabled must be true"
        ]
        
        all_issues := array.concat(array.concat(algorithm_issue, kms_key_issue), bucket_key_issue)
        violation := all_issues[_]
    ]
}

# Validate public access block against golden template
validate_pab_against_golden_template(resource) := violations if {
    pab := resource.change.after
    required := golden_tfvars_structure.public_access_block_required
    
    violations := [violation |
        some field, expected_value in required
        actual_value := object.get(pab, field, null)
        actual_value != expected_value
        violation := sprintf("%s must be %v, found: %v", [field, expected_value, actual_value])
    ]
}

# Validate tags against golden template  
validate_tags_against_golden_template(resource) := violations if {
    tags := object.get(resource.change.after, "tags", {})
    
    # Check required tags exist
    missing_tags := [tag |
        some tag in golden_tfvars_structure.required_tags
        not object.get(tags, tag, null)
    ]
    
    # Check required tag values
    incorrect_values := [violation |
        some tag, expected_value in golden_tfvars_structure.required_tag_values
        actual_value := object.get(tags, tag, null)
        actual_value != expected_value
        violation := sprintf("Tag %s must be '%s', found: '%s'", [tag, expected_value, actual_value])
    ]
    
    violations := array.concat(
        [sprintf("Missing required tag: %s", [tag]) | tag := missing_tags[_]],
        incorrect_values
    )
}

# =============================================================================
# GOLDEN TEMPLATE POLICY STATEMENT VALIDATORS  
# =============================================================================

# Helper function to normalize Action field to array
normalize_actions(statement) := actions if {
    is_array(statement.Action)
    actions := statement.Action
} else := [statement.Action] if {
    is_string(statement.Action)
}

# Check for principal restriction statement (golden template requirement)
has_principal_restriction(policy_doc) if {
    some statement in policy_doc.Statement
    statement.Effect == "Deny"
    
    # Normalize actions to array
    actions := normalize_actions(statement)
    "s3:PutObject" in actions
    "s3:GetObject" in actions  
    "s3:DeleteObject" in actions
    
    # Must have ArnNotLike condition for aws:PrincipalArn
    some condition_type, condition_value in statement.Condition
    condition_type == "ArnNotLike"
    condition_value["aws:PrincipalArn"]
}

# Check for VPC endpoint restriction statement (golden template requirement)
has_vpc_endpoint_restriction(policy_doc) if {
    some statement in policy_doc.Statement
    statement.Effect == "Deny"
    
    # Normalize actions to array
    actions := normalize_actions(statement)
    "s3:PutObject" in actions
    "s3:GetObject" in actions
    "s3:DeleteObject" in actions
    
    # Must have StringNotEquals condition for aws:SourceVpce
    some condition_type, condition_value in statement.Condition
    condition_type == "StringNotEquals"
    condition_value["aws:SourceVpce"]
}

# Check for KMS encryption requirement statement (golden template requirement)
has_kms_encryption_requirement(policy_doc) if {
    some statement in policy_doc.Statement  
    statement.Effect == "Deny"
    
    # Normalize actions to array
    actions := normalize_actions(statement)
    "s3:PutObject" in actions
    
    # Must have StringNotEquals condition for KMS encryption header
    some condition_type, condition_value in statement.Condition
    condition_type == "StringNotEquals"
    condition_value["s3:x-amz-server-side-encryption-aws-kms-key-id"]
}

# =============================================================================
# MAIN.REGO INTEGRATION - DENY RULE  
# =============================================================================

# Return violations directly to maintain object structure
deny := violations

# Extract module key from resource address
extract_bucket_from_address(address) := bucket_key if {
    parts := split(address, "[\"")
    count(parts) == 2
    end_parts := split(parts[1], "\"]")
    bucket_key := end_parts[0]
}