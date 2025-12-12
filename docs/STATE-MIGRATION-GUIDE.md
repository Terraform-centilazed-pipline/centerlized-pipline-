# State Migration Guide

## Overview

This guide covers migrating from **granular single-resource states** to **multi-resource combined states** with automatic backup and validation.

## Architecture Patterns

### Pattern 1: Ultra-Granular Resource Isolation (Default)

**Each individual resource gets its own state file:**

```
s3/arj-wkld-a-prd/us-east-1/test-poc-3/arj-test-bucket/terraform.tfstate     (1 S3 bucket)
s3/arj-wkld-a-prd/us-east-1/test-poc-3/arj-backup-bucket/terraform.tfstate   (another S3 bucket)
iam/arj-wkld-a-prd/us-east-1/test-poc-3/arj-admin-role/terraform.tfstate     (1 IAM role)
kms/arj-wkld-a-prd/us-east-1/test-poc-3/arj-encryption-key/terraform.tfstate (1 KMS key)
```

**Benefits:**
- ✅ Independent deployments per service
- ✅ Isolated blast radius (S3 error doesn't block IAM)
- ✅ Team separation (S3 team vs IAM team)
- ✅ Faster plan/apply for single resource changes

**Use When:**
- Resources are independent (no dependencies)
- Different teams manage different resources
- Want maximum flexibility and isolation

### Pattern 2: Multi-Resource State (After Migration)

**Multiple resources in one state file:**

```
multi/arj-wkld-a-prd/us-east-1/test-poc-3/terraform.tfstate (S3 + IAM + KMS)
```

**Benefits:**
- ✅ Single source of truth
- ✅ Easier dependency management (S3 → IAM role)
- ✅ Atomic updates (all resources change together)
- ✅ Simpler state management

**Use When:**
- Resources have dependencies (S3 bucket → IAM policy)
- Need atomic updates across multiple resources
- Single team manages all resources

## Migration Workflow

### Step 1: Automatic Backup

**Before any migration, states are automatically backed up:**

```bash
# Original states (resource-level)
s3/arj-wkld-a-prd/us-east-1/test-poc-3/arj-test-bucket/terraform.tfstate
iam/arj-wkld-a-prd/us-east-1/test-poc-3/arj-admin-role/terraform.tfstate

# Backups (with timestamp)
backups/2025-12-12_14-30-00_migration_s3/s3/arj-wkld-a-prd/us-east-1/test-poc-3/arj-test-bucket/terraform.tfstate
backups/2025-12-12_14-30-00_migration_iam/iam/arj-wkld-a-prd/us-east-1/test-poc-3/arj-admin-role/terraform.tfstate
```

**Backup Retention:** Backups are kept permanently in S3. You can manually delete old backups after verification.

### Step 2: State Download & Validation

**Script downloads and validates each state:**

```bash
⬇️  Downloading state: s3/arj-wkld-a-prd/us-east-1/test-poc-3/arj-test-bucket/terraform.tfstate
✅ Downloaded to: /tmp/s3-arj-test-bucket.tfstate

📊 Validating: s3-arj-test-bucket.tfstate
   Version: 4
   Terraform: 1.5.0
   Resources: 1
   Types: aws_s3_bucket
```

### Step 3: State Merge

**States are merged into single combined state:**

```bash
🔀 Merging 2 state files...
   ✓ Loaded: s3.tfstate (3 resources)
   ✓ Loaded: iam.tfstate (2 resources)
✅ Merged state created: 5 total resources
```

**Merge Logic:**
- Combines all resources from source states
- Preserves resource addresses (no state mv needed)
- Updates serial number to highest value
- Maintains Terraform version compatibility

### Step 4: Validation

**Merged state is validated before upload:**

```bash
📊 Validating merged state:
   Version: 4
   Terraform: 1.5.0
   Resources: 5
   Types: aws_s3_bucket, aws_iam_role, aws_iam_role_policy
✅ Validation passed
```

### Step 5: Upload New State

**Merged state uploaded to multi/ path:**

```bash
⬆️  Uploading state: multi/arj-wkld-a-prd/us-east-1/test-poc-3/combined/terraform.tfstate
✅ Uploaded to: s3://my-terraform-state-bucket/...
```

### Step 6: Update Terraform Configuration

**Update tfvars to use new project name (remove service suffix):**

```hcl
# Before (granular states)
project     = "test-poc-3-s3"   # Generated: test-poc-3-s3-s3
environment = "production"

# After (multi-resource state)
project     = "test-poc-3"      # Generated: test-poc-3 (no suffix)
environment = "production"
```

**CRITICAL:** Resource keys must stay the same to prevent destroy+recreate:

```hcl
# DON'T CHANGE THIS
s3_buckets = {
  "test-poc-3" = {  # ← Keep this key the same!
    bucket_name = "arj-test-poc-3-use1-prd"
    ...
  }
}

iam_roles = {
  "test-poc-3-role" = {  # ← Keep this key the same!
    role_name = "arj-test-poc-3-role"
    ...
  }
}
```

### Step 7: Verification

**Run terraform plan to verify 0 changes:**

```bash
cd Accounts/test-poc-3
terraform init -reconfigure  # Re-initialize with new backend key
terraform plan

# Should show:
# No changes. Your infrastructure matches the configuration.
```

**If plan shows recreates:**
- ❌ **DO NOT APPLY!**
- Check resource keys match state
- Check project name is correct (no service suffix)
- Use rollback if needed

### Step 8: Cleanup (Optional)

**After verification, old states can be deleted:**

```bash
# Delete old granular states
aws s3 rm s3://my-terraform-state-bucket/s3/arj-wkld-a-prd/us-east-1/test-poc-3-s3/terraform.tfstate
aws s3 rm s3://my-terraform-state-bucket/iam/arj-wkld-a-prd/us-east-1/test-poc-3-iam/terraform.tfstate

# Keep backups for rollback (delete after 30 days)
```

## Migration Examples

### Example 1: Dry Run (Test Migration)

**Check what will happen without making changes:**

```bash
python scripts/migrate-terraform-state.py \
  --project test-poc-3 \
  --account arj-wkld-a-prd \
  --region us-east-1 \
  --services s3 iam \
  --bucket my-terraform-state-bucket \
  --dry-run
```

**Output:**
```
📋 Migration Plan:
   Sources:
     • s3: s3/arj-wkld-a-prd/us-east-1/test-poc-3/arj-test-bucket/terraform.tfstate
     • iam: iam/arj-wkld-a-prd/us-east-1/test-poc-3/arj-admin-role/terraform.tfstate
   Target:
     • multi: multi/arj-wkld-a-prd/us-east-1/test-poc-3/combined/terraform.tfstate

⚠️  DRY RUN MODE - No changes will be made
✅ Dry run completed - no changes made
```

### Example 2: Live Migration (S3 + IAM)

**Migrate two granular states to one multi-resource state:**

```bash
python scripts/migrate-terraform-state.py \
  --project test-poc-3 \
  --account arj-wkld-a-prd \
  --region us-east-1 \
  --services s3 iam \
  --bucket my-terraform-state-bucket

# Confirm: yes
```

**Output:**
```
STEP 1: BACKUP SOURCE STATES
📦 Backing up state...
✅ Backup created: backups/2025-12-12_14-30-00_migration_s3/...
✅ Backup created: backups/2025-12-12_14-30-00_migration_iam/...

STEP 2: DOWNLOAD SOURCE STATES
⬇️  Downloading state: s3/arj-wkld-a-prd/us-east-1/test-poc-3/arj-test-bucket/...
✅ Downloaded to: /tmp/s3-arj-test-bucket.tfstate
⬇️  Downloading state: iam/arj-wkld-a-prd/us-east-1/test-poc-3/arj-admin-role/...
✅ Downloaded to: /tmp/iam-arj-admin-role.tfstate

STEP 3: VALIDATE SOURCE STATES
📊 Validating: s3-arj-test-bucket.tfstate
   Resources: 1
📊 Validating: iam-arj-admin-role.tfstate
   Resources: 1

STEP 4: MERGE STATES
🔀 Merging 2 state files...
✅ Merged state created: 2 total resources

STEP 5: VALIDATE MERGED STATE
📊 Validating merged state:
   Resources: 2
✅ Validation passed

STEP 6: UPLOAD MERGED STATE
⬆️  Uploading state: multi/arj-wkld-a-prd/us-east-1/test-poc-3/combined/terraform.tfstate
✅ Uploaded successfully

MIGRATION COMPLETED SUCCESSFULLY
✅ Migrated from 2 granular states to 1 multi-resource state

📦 Backups available:
   • s3: s3://bucket/backups/2025-12-12_14-30-00_migration_s3/...
   • iam: s3://bucket/backups/2025-12-12_14-30-00_migration_iam/...

⚠️  IMPORTANT NEXT STEPS:
   1. Update your tfvars to use project name: 'test-poc-3' (remove -service suffix)
   2. Run 'terraform plan' to verify 0 changes
   3. If plan shows recreates, use backups to rollback
   4. Delete old granular states after verification
```

### Example 3: Rollback to Backup

**If migration went wrong, restore from backup:**

```bash
python scripts/migrate-terraform-state.py \
  --rollback \
  --backup-key "backups/2025-12-12_14-30-00_migration_s3/s3/arj-wkld-a-prd/us-east-1/test-poc-3/arj-test-bucket/terraform.tfstate" \
  --bucket my-terraform-state-bucket

# Confirm: yes
```

**Output:**
```
TERRAFORM STATE ROLLBACK
Backup:  s3://bucket/backups/2025-12-12_14-30-00_migration_s3/...
Restore: s3://bucket/s3/arj-wkld-a-prd/us-east-1/test-poc-3/arj-test-bucket/terraform.tfstate

Proceed with rollback? (yes/no): yes
✅ State restored from backup
```

## Troubleshooting

### Problem: Terraform plan shows recreates after migration

**Symptoms:**
```
Plan: 5 to add, 0 to change, 5 to destroy.
```

**Cause:** Resource keys changed in tfvars

**Solution:**
1. Check resource keys in tfvars match state
2. Verify project name has no service suffix
3. Rollback if needed

### Problem: Migration fails with "No states downloaded"

**Symptoms:**
```
⚠️  State not found (may be new resource)
❌ No states downloaded - migration failed
```

**Cause:** Source states don't exist yet (fresh deployment)

**Solution:**
- This is normal for new deployments
- Deploy resources first, then migrate later
- Skip migration if starting fresh with multi-resource state

### Problem: Merged state has wrong serial number

**Symptoms:**
```
Error: state serial number conflict
```

**Cause:** Local state serial higher than merged state

**Solution:**
- Script uses `max(serial)` from all source states
- Run `terraform refresh` to sync serial
- Or restore backup and retry migration

## Best Practices

### When to Use Granular States

✅ **Independent resources** - No dependencies between S3 and IAM  
✅ **Different teams** - S3 team deploys independently from IAM team  
✅ **High-change resources** - Frequently update S3, rarely touch IAM  
✅ **Risk isolation** - Don't want S3 error to block IAM deployment  

### When to Migrate to Multi-Resource

✅ **Dependencies exist** - S3 bucket needs IAM role attached  
✅ **Atomic updates** - All resources must change together  
✅ **Single ownership** - One team manages all resources  
✅ **Simplified management** - Prefer one state over multiple  

### Migration Planning Checklist

- [ ] Run dry-run to validate migration plan
- [ ] Verify all source states exist in S3
- [ ] Backup states manually (script does this automatically)
- [ ] Schedule migration during low-traffic window
- [ ] Update tfvars with correct project name
- [ ] Test terraform plan before apply
- [ ] Keep rollback command ready
- [ ] Document migration in team wiki

## State File Locations Reference

### Ultra-Granular States (Per Resource)

```
s3/{account}/{region}/{project}/{resource_name}/terraform.tfstate
iam/{account}/{region}/{project}/{resource_name}/terraform.tfstate
kms/{account}/{region}/{project}/{resource_name}/terraform.tfstate
lambda/{account}/{region}/{project}/{resource_name}/terraform.tfstate
rds/{account}/{region}/{project}/{resource_name}/terraform.tfstate
vpc/{account}/{region}/{project}/{resource_name}/terraform.tfstate
```

**Example:**
```
s3/arj-wkld-a-prd/us-east-1/test-poc-3/arj-test-bucket/terraform.tfstate
s3/arj-wkld-a-prd/us-east-1/test-poc-3/arj-backup-bucket/terraform.tfstate
iam/arj-wkld-a-prd/us-east-1/test-poc-3/arj-admin-role/terraform.tfstate
```

### Multi-Resource State

```
multi/{account}/{region}/{project}/combined/terraform.tfstate
```

### Backups

```
backups/{timestamp}_{reason}/{original_path}/terraform.tfstate

Example:
backups/2025-12-12_14-30-00_migration_s3/s3/arj-wkld-a-prd/us-east-1/test-poc-3/arj-test-bucket/terraform.tfstate
```

## Script Reference

### migrate-terraform-state.py

**Location:** `scripts/migrate-terraform-state.py`

**Required Arguments:**
- `--bucket` - S3 bucket containing state files
- `--project` - Project name (e.g., test-poc-3)
- `--account` - Account name (e.g., arj-wkld-a-prd)
- `--services` - Space-separated service list (e.g., s3 iam kms)

**Optional Arguments:**
- `--region` - AWS region (default: us-east-1)
- `--dry-run` - Show plan without making changes
- `--rollback` - Restore from backup
- `--backup-key` - Backup key to restore from
- `--target-key` - Target key to restore to

**Exit Codes:**
- `0` - Success
- `1` - Failure

## Support

For issues or questions:
1. Check troubleshooting section above
2. Review migration logs for errors
3. Use `--dry-run` to test migration plan
4. Keep backups for at least 30 days
5. Rollback if terraform plan shows recreates
