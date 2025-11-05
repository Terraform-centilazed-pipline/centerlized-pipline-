# S3 Security Policy Documentation

## Overview
This document provides comprehensive guidance for the S3 security validation policy (`comprehensive.rego`) used in the centralized Terraform pipeline.

## Policy Purpose
The S3 security policy validates S3 resource configurations in Terraform plans against enterprise security standards and golden template compliance. It enforces strict security controls and prevents dangerous configurations.

## Security Approach
- **ZERO TRUST**: Block all Allow statements in bucket policies
- **GOLDEN TEMPLATE**: Enforce mandatory 3-statement Deny-only policy structure
- **VPC ONLY**: Require VPC endpoint access restrictions
- **ENCRYPTION**: Mandate KMS encryption with explicit key ARNs
- **COMPLIANCE**: Enforce required tags and naming conventions

## Validation Scope

### Critical Security Checks
- Dangerous Allow statements detection and blocking
- Golden template structure compliance (exactly 3 Deny statements)
- Public access prevention (Principal: "*" blocked)
- VPC endpoint restriction enforcement
- Encryption enforcement validation

### Configuration Validation
- Bucket naming conventions and force_destroy settings
- KMS encryption with explicit key ARN requirements
- Public access block configuration (all 4 settings must be true)
- Required compliance tags with golden template values

### Resource Types Monitored
- `aws_s3_bucket`: Core bucket configuration and compliance
- `aws_s3_bucket_server_side_encryption_configuration`: KMS encryption
- `aws_s3_bucket_public_access_block`: Public access restrictions
- `aws_s3_bucket_policy`: Policy structure and security validation

## Golden Template Requirements

### S3 Bucket Policy Structure
The bucket policy MUST have exactly these 3 Deny statements:

1. **Principal Restriction**: ArnNotLike condition on aws:PrincipalArn
2. **VPC Endpoint Restriction**: StringNotEquals condition on aws:SourceVpce  
3. **Encryption Enforcement**: StringNotEquals condition on s3:x-amz-server-side-encryption

### Required Tags
- **Name**: Bucket identifier
- **Environment**: dev/staging/prod
- **Project**: Project/application name
- **ManagedBy**: terraform
- **AccessType**: vpc-endpoint-only (golden template)
- **VPCAccess**: true (golden template)

## Usage Guide

### Local Testing
```bash
# Test policy violations
opa eval -d OPA-Poclies/terraform -i test-plan.json "data.terraform.s3.deny"

# Test with validation summary
opa eval -d OPA-Poclies/terraform -i test-plan.json "data.terraform.main.validate_plan"

# Create test plan
terraform plan -out=plan.tfplan
terraform show -json plan.tfplan > test-plan.json
```

### Pipeline Integration
- Policy is automatically called by `centralized-controller.yml` workflow
- Results appear in GitHub Actions logs and PR comments
- Violations block deployment based on severity levels

## Adding New Validation Rules

### Basic Rule Structure
```rego
violations[msg] if {
    # Resource selection
    some i
    resource := input.resource_changes[i]
    resource.type == "aws_s3_bucket_policy"
    some action in resource.change.actions
    action in ["create", "update"]
    
    # Your validation logic here
    your_validation_condition
    
    # Structured violation message
    msg := {
        "policy": "terraform.s3.your_new_policy",
        "severity": "critical|high|medium|low",
        "resource": resource.address,
        "message": "Description of the violation",
        "remediation": "How to fix the issue",
        "security_risk": "Business impact explanation"
    }
}
```

### Severity Levels
- **critical**: Blocks deployment, immediate attention required
- **high**: Security risk, should be fixed before deployment
- **medium**: Compliance issue, fix in next iteration
- **low**: Best practice recommendation

## Common Customization Examples

### Adding Custom Tag Validation
1. Update `required_tags` in `missing_required_tags` function
2. Add validation logic in `validate_tag_values` function
3. Update golden template tag requirements

### Environment-Specific Rules
```rego
violations[msg] if {
    # Check if this is a production environment
    bucket_config.tags.Environment == "prod"
    # Apply stricter rules for production
    stricter_production_validation
}
```

### Adding New Resource Type Support
1. Add resource type to main validation logic
2. Create helper functions for resource-specific validation
3. Add golden template requirements if applicable
4. Update documentation and test cases

## Troubleshooting

### Common Issues
- **JSON parsing error**: Check Terraform plan JSON format
- **No violations detected**: Verify resource types and actions in plan
- **Syntax error**: Validate OPA policy syntax with `opa test`
- **Helper function undefined**: Check function names and imports

### Debugging Tips
```bash
# Test individual functions
opa eval -d . "data.terraform.s3.function_name(test_input)"

# Check input structure
opa eval -d . -i plan.json "input.resource_changes[0]"

# Validate JSON
# Use online JSON validators for complex structures

# Debug with print statements
# Add print("Debug:", variable) in policy for debugging
```

## Policy Maintenance

### Regular Updates
- Review and update golden template requirements quarterly
- Add new AWS S3 security features as they become available
- Update severity levels based on threat landscape changes
- Enhance remediation guidance based on common issues

### Version Control
- Update version number in header when making changes
- Document breaking changes in commit messages
- Test with representative Terraform plans before deployment
- Consider backward compatibility for existing deployments

## Learning Resources
- [OPA Documentation](https://www.openpolicyagent.org/docs/)
- [Terraform S3 Provider](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/s3_bucket)
- [AWS S3 Security Best Practices](https://docs.aws.amazon.com/s3/latest/userguide/security-best-practices.html)
- [REGO Language Guide](https://www.openpolicyagent.org/docs/latest/policy-language/)

## Support
- **Policy issues**: Check GitHub Issues in the repository
- **Security questions**: Contact security team
- **Terraform questions**: Reference Terraform S3 provider documentation
- **OPA syntax**: Reference Open Policy Agent documentation