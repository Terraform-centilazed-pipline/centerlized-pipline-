# Quick Reference: Normal vs Enhanced Orchestrator

## Backend Key Patterns

```
Normal:    s3/{account_name}/{region}/{project}/terraform.tfstate
Enhanced:  {account_name}/{service}/{resource_name}/{resource_name}.tfstate

Examples:
Normal:    s3/my-aws-account/us-east-1/kms-encryption/terraform.tfstate
Enhanced:  my-aws-account/kms/customer-master-key-prod/customer-master-key-prod.tfstate
```

## Command Usage

### Normal Orchestrator
```bash
python3 terraform-deployment-orchestrator.py plan \
  --changed-files "Accounts/my-account/us-east-1/kms/kms.tfvars" \
  --output-summary results.json
```

### Enhanced Orchestrator v2.0
```bash
python3 terraform-deployment-orchestrator-enhanced.py plan \
  --changed-files "Accounts/my-account/kms/kms.tfvars" \
  --output-summary results.json

# Discovery mode
python3 terraform-deployment-orchestrator-enhanced.py discover

# Dry run
python3 terraform-deployment-orchestrator-enhanced.py plan --dry-run

# With filters
python3 terraform-deployment-orchestrator-enhanced.py plan \
  --account my-aws-account \
  --region us-east-1 \
  --environment prod
```

## When to Use Which

### Use Normal → Region-based, stable, legacy systems
### Use Enhanced → Resource-based, multi-region, service organization

## Key Features in Enhanced v2.0

✅ Resource name extraction (S3 buckets, KMS aliases, IAM roles, Lambda functions)
✅ Service detection (14 AWS services supported)
✅ Tfvars HCL validation
✅ Enhanced PR comments with version info
✅ Discovery and dry-run modes
✅ No duplicate service names (kms/kms → kms)
✅ Full account names (not shortened)
✅ Generic for all services (not KMS-specific)

## Files Created

1. `terraform-deployment-orchestrator-enhanced.py` - Enhanced v2.0 script (905 lines)
2. `ORCHESTRATOR_COMPARISON.md` - Detailed comparison guide
3. `BUG_FIXES_v2.0.md` - All bug fixes documented
4. `QUICK_REFERENCE.md` - This file

## Status

✅ Both scripts syntax-validated
✅ All bugs fixed
✅ Ready for testing
✅ Can coexist without conflicts
