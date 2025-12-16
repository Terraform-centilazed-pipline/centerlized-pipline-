# Terraform Orchestrator Configuration Guide

This document describes all configuration options for the Terraform Deployment Orchestrator.

## Overview

All configuration values can be customized via environment variables or use sensible defaults. This allows easy adaptation to different environments without code changes.

## Configuration Options

### AWS Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `TERRAFORM_STATE_BUCKET` | `terraform-elb-mdoule-poc` | S3 bucket for Terraform state storage |
| `TERRAFORM_ASSUME_ROLE` | `TerraformExecutionRole` | IAM role name to assume for state operations |
| `AWS_REGION` | `us-east-1` | Default AWS region for operations |

**Example:**
```yaml
env:
  TERRAFORM_STATE_BUCKET: my-terraform-state-bucket
  TERRAFORM_ASSUME_ROLE: MyTerraformRole
  AWS_REGION: us-west-2
```

### Backend Key Pattern

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `BACKEND_KEY_PATTERN` | `{service_part}/{account_name}/{region}/{project}/{resource_path}/terraform.tfstate` | Pattern for state file paths |
| `BACKEND_KEY_MULTI_SERVICE_PREFIX` | `multi` | Prefix for multi-service deployments |

**Default Patterns:**
- Single service: `s3/arj-wkld-a-prd/us-east-1/test-poc-3/bucket-name/terraform.tfstate`
- Multi service: `multi/arj-wkld-a-prd/us-east-1/test-poc-3/iam-s3/terraform.tfstate`

### State Migration & Backup

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `STATE_BACKUP_PREFIX` | `backups` | S3 prefix for state backups |
| `STATE_BACKUP_ENABLED` | `true` | Enable automatic state backups before migration |
| `STATE_AUTO_MIGRATION_ENABLED` | `true` | Auto-detect and migrate old state locations |
| `STATE_OLD_LOCATION_CLEANUP` | `true` | Delete old state after successful migration |

**Example:**
```yaml
env:
  STATE_BACKUP_PREFIX: state-backups
  STATE_BACKUP_ENABLED: true
  STATE_AUTO_MIGRATION_ENABLED: true
  STATE_OLD_LOCATION_CLEANUP: false  # Keep old state for safety
```

### Audit Logging

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `AUDIT_LOG_ENABLED` | `true` | Enable audit logging to S3 |
| `AUDIT_LOG_BUCKET` | Same as `TERRAFORM_STATE_BUCKET` | S3 bucket for audit logs |
| `AUDIT_LOG_PREFIX` | `audit-logs` | S3 prefix for audit logs |

**Audit Log Path Format:**
```
{AUDIT_LOG_PREFIX}/{account_name}/{project}/{action}-{timestamp}.json
```

**Example:**
```
audit-logs/arj-wkld-a-prd/test-poc-3/plan-20251216-163448.json
```

### Terraform Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `TERRAFORM_LOCK_ENABLED` | `true` | Enable Terraform state locking |
| `TERRAFORM_LOCK_TABLE` | `null` | DynamoDB table for state locking (optional) |

### Execution Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `MAX_PARALLEL_DEPLOYMENTS` | `0` (auto) | Maximum parallel deployments (0 = CPU count * 2) |
| `DEPLOYMENT_TIMEOUT_SECONDS` | `3600` | Timeout for each deployment (1 hour) |
| `ORCHESTRATOR_DEBUG` | `true` | Enable debug output |

## Usage Examples

### Production Configuration

```yaml
# .github/workflows/centralized-controller.yml
env:
  # Production settings
  TERRAFORM_STATE_BUCKET: prod-terraform-state-bucket
  TERRAFORM_ASSUME_ROLE: TerraformProductionRole
  AWS_REGION: us-east-1
  
  # Strict backup and safety
  STATE_BACKUP_ENABLED: true
  STATE_OLD_LOCATION_CLEANUP: false  # Keep old state in production
  
  # Audit logging
  AUDIT_LOG_ENABLED: true
  AUDIT_LOG_BUCKET: prod-audit-logs
  AUDIT_LOG_PREFIX: terraform-audit
  
  # Performance
  MAX_PARALLEL_DEPLOYMENTS: 4
  DEPLOYMENT_TIMEOUT_SECONDS: 7200  # 2 hours
  
  # Logging
  ORCHESTRATOR_DEBUG: false  # Less verbose in production
```

### Development Configuration

```yaml
# .github/workflows/dev-controller.yml
env:
  # Dev settings
  TERRAFORM_STATE_BUCKET: dev-terraform-state
  TERRAFORM_ASSUME_ROLE: TerraformDevRole
  AWS_REGION: us-west-2
  
  # Aggressive cleanup for dev
  STATE_BACKUP_ENABLED: true
  STATE_OLD_LOCATION_CLEANUP: true
  
  # Debug enabled
  ORCHESTRATOR_DEBUG: true
```

### Custom Backend Key Pattern

```yaml
env:
  # Custom pattern: {region}/{account}/{service}/{project}.tfstate
  BACKEND_KEY_PATTERN: "{region}/{account_name}/{service_part}/{project}.tfstate"
  BACKEND_KEY_MULTI_SERVICE_PREFIX: "combined"
  
  # Results in:
  # us-east-1/arj-wkld-a-prd/s3/test-poc-3.tfstate
  # us-east-1/arj-wkld-a-prd/combined/test-poc-3.tfstate (multi-service)
```

## Validation

To validate your configuration:

```bash
# Check environment variables are set
env | grep TERRAFORM
env | grep STATE
env | grep AUDIT

# Test with dry-run
python3 scripts/terraform-deployment-orchestrator-enhanced.py plan \
  --changed-files 'S3/test-poc-3/test-poc-3.tfvars' \
  --working-dir ./source-repo \
  --debug
```

## Migration Notes

### Changing Backend Key Pattern

⚠️ **Warning:** Changing `BACKEND_KEY_PATTERN` will cause state migration!

**Safe migration steps:**
1. Enable backups: `STATE_BACKUP_ENABLED=true`
2. Disable cleanup: `STATE_OLD_LOCATION_CLEANUP=false`
3. Update pattern in environment
4. Run plan to trigger migration
5. Verify new state location
6. After validation, enable cleanup

### Changing State Bucket

⚠️ **Critical:** Changing `TERRAFORM_STATE_BUCKET` requires manual state migration!

**Steps:**
1. Copy all state files to new bucket:
   ```bash
   aws s3 sync s3://old-bucket/ s3://new-bucket/
   ```
2. Update environment variable
3. Verify state is accessible
4. Keep old bucket for 30 days minimum

## Troubleshooting

### State Migration Issues

**Problem:** Old state detected on every run
**Solution:** Ensure `STATE_OLD_LOCATION_CLEANUP=true` and role has `s3:DeleteObject` permission

**Problem:** Access denied during migration
**Solution:** Verify `TERRAFORM_ASSUME_ROLE` has permissions on both source and destination

### Audit Log Issues

**Problem:** Audit logs not appearing
**Solution:** Check `AUDIT_LOG_ENABLED=true` and bucket permissions

**Problem:** Access denied when saving logs
**Solution:** Ensure `TERRAFORM_ASSUME_ROLE` has write access to `AUDIT_LOG_BUCKET`

## Best Practices

1. **Always enable backups** in production: `STATE_BACKUP_ENABLED=true`
2. **Use separate audit bucket** in production for security
3. **Set reasonable timeouts** based on infrastructure size
4. **Test configuration changes** in dev environment first
5. **Document custom patterns** in your README
6. **Monitor audit logs** regularly for compliance

## See Also

- [IAM Policy Setup Guide](IAM-POLICY-SETUP-GUIDE.md)
- [Multi-Module Deployment Guide](MULTI-MODULE-GUIDE.md)
- [State Migration Guide](../README.md#state-migration)
