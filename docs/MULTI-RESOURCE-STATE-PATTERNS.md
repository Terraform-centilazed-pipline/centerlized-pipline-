# Multi-Resource State Management - Simple Guide

## The Main Question: How Many Resources in One Tfvars File?

This determines your backend state file path and isolation level.

---

## Quick Answer

### 🎯 Put 1 Resource in Each Tfvars (Recommended)

**Example: 3 separate tfvars files**

```
S3/test-poc-3/
├── data-bucket.tfvars      (1 S3 bucket)
├── logs-bucket.tfvars      (1 S3 bucket)  
└── backup-bucket.tfvars    (1 S3 bucket)
```

**What happens:**
```
✅ data-bucket.tfvars   → s3/.../test-poc-3/data-bucket/terraform.tfstate
✅ logs-bucket.tfvars   → s3/.../test-poc-3/logs-bucket/terraform.tfstate
✅ backup-bucket.tfvars → s3/.../test-poc-3/backup-bucket/terraform.tfstate
```

**Result:** Each bucket has its own state file ✅

---

### 🔄 Put Multiple Resources in One Tfvars (Alternative)

**Example: 1 tfvars file with 3 buckets**

```
S3/test-poc-3/
└── test-poc-3.tfvars       (3 S3 buckets in one file)
```

**What happens:**
```
📦 test-poc-3.tfvars → s3/.../test-poc-3/terraform.tfstate
```

**Result:** All 3 buckets share one state file 📦

---

## Visual Comparison

### Option 1: Separate Tfvars Files (1 Resource Each)

```
📁 Your Files:
   ├── bucket-A.tfvars ─────→ State: s3/.../project/bucket-A/terraform.tfstate
   ├── bucket-B.tfvars ─────→ State: s3/.../project/bucket-B/terraform.tfstate
   └── bucket-C.tfvars ─────→ State: s3/.../project/bucket-C/terraform.tfstate

✅ Update bucket-A → Only bucket-A state changes
✅ Delete bucket-B → Only bucket-B affected
✅ Deploy in parallel → All 3 can deploy simultaneously
```

### Option 2: One Tfvars File (3 Resources)

```
📁 Your Files:
   └── all-buckets.tfvars ──→ State: s3/.../project/terraform.tfstate

⚠️  Update bucket-A → Terraform runs on ALL 3 buckets
⚠️  Error on bucket-B → Blocks changes to bucket-A and bucket-C
⚠️  Deploy once → All 3 deploy together (can't deploy individually)
```

---

## How Backend Keys Are Generated

The system looks at your tfvars file and counts resources:

### Case 1: 1 Resource in Tfvars

**File: data-bucket.tfvars**
```hcl
s3_buckets = {
  "data-bucket" = { bucket_name = "arj-data-bucket" }
}
```

**Backend Key:**
```
s3/.../test-poc-3/data-bucket/terraform.tfstate
                  ^^^^^^^^^^^
                  Uses the resource key name
```

---

### Case 2: 2+ Resources in Tfvars

**File: application-buckets.tfvars**
```hcl
s3_buckets = {
  "data-bucket" = { ... }
  "logs-bucket" = { ... }
}
```

**Backend Key:**
```
s3/.../test-poc-3/terraform.tfstate
                  ^^^^^^^^^^^^^^^^^
                  State directly under project (no extra folder!)
```

---

### Case 3: Many Resources Example

**File: many-buckets.tfvars**
```hcl
s3_buckets = {
  "data-bucket"    = { ... }
  "logs-bucket"    = { ... }
  "backup-bucket"  = { ... }
  "archive-bucket" = { ... }
  "temp-bucket"    = { ... }
}
```

**Backend Key:**
```
s3/.../test-poc-3/terraform.tfstate
                  ^^^^^^^^^^^^^^^^^
                  Same path for any count (super clean!)
```

**All these use the same path:**
- 2 buckets: `s3/.../test-poc-3/terraform.tfstate`
- 5 buckets: `s3/.../test-poc-3/terraform.tfstate`
- 100 buckets: `s3/.../test-poc-3/terraform.tfstate`

---

### Case 4: Multiple Services in One Tfvars

**File: everything.tfvars**
```hcl
s3_buckets = { "data-bucket" = { ... } }
iam_roles  = { "admin-role"  = { ... } }
kms_keys   = { "key-1"       = { ... } }
```

**Backend Key:**
```
multi/.../test-poc-3/iam-kms-s3/terraform.tfstate
^^^^^                ^^^^^^^^^^^
multi-service        Shows which services (sorted alphabetically)
```

---

## Simple Decision Guide

### ❓ Question: "I need to deploy 5 S3 buckets. How many tfvars files?"

**Answer depends on your needs:**

---

## ✅ OPTION 1: Create 5 Separate Tfvars Files (Maximum Control)

```
S3/my-project/
├── bucket-1.tfvars  →  s3/.../my-project/bucket-1/terraform.tfstate
├── bucket-2.tfvars  →  s3/.../my-project/bucket-2/terraform.tfstate
├── bucket-3.tfvars  →  s3/.../my-project/bucket-3/terraform.tfstate
├── bucket-4.tfvars  →  s3/.../my-project/bucket-4/terraform.tfstate
└── bucket-5.tfvars  →  s3/.../my-project/bucket-5/terraform.tfstate
```

**Each tfvars file contains:**
```hcl
project = "my-project"
s3_buckets = {
  "bucket-1" = { bucket_name = "arj-bucket-1-prd" }
}
```

**What you get:**
- ✅ Change bucket-1 → Only bucket-1 affected
- ✅ Delete bucket-3 → Only bucket-3 removed  
- ✅ Deploy all 5 in parallel → Faster CI/CD
- ✅ Different teams own different buckets
- ❌ Manage 5 separate files

**Choose this if:** Each bucket is independent and managed separately

---

## ✅ OPTION 2: Create 1 Tfvars File (Simple Management)

```
S3/my-project/
└── my-project.tfvars  →  s3/.../my-project/terraform.tfstate
```

**The tfvars file contains:**
```hcl
project = "my-project"
s3_buckets = {
  "bucket-1" = { bucket_name = "arj-bucket-1-prd" }
  "bucket-2" = { bucket_name = "arj-bucket-2-prd" }
  "bucket-3" = { bucket_name = "arj-bucket-3-prd" }
  "bucket-4" = { bucket_name = "arj-bucket-4-prd" }
  "bucket-5" = { bucket_name = "arj-bucket-5-prd" }
}
```

**What you get:**
- ✅ Manage 1 file instead of 5
- ✅ All buckets deploy together (atomic)
- ✅ Can reference buckets from each other
- ❌ Change bucket-1 → Terraform checks all 5
- ❌ Error in bucket-3 → Blocks all 5
- ❌ Can't deploy buckets independently

**Choose this if:** All 5 buckets are related (same app/team/purpose)

---

## ✅ OPTION 3: Mix Isolated + Grouped (Smart Approach)

```
S3/my-project/
├── production-critical.tfvars  →  s3/.../my-project/production-critical/terraform.tfstate
└── dev-testing.tfvars          →  s3/.../my-project/terraform.tfstate
```

**production-critical.tfvars (1 important bucket):**
```hcl
s3_buckets = {
  "production-critical" = { bucket_name = "arj-prod-critical" }
}
```

**dev-testing.tfvars (4 dev buckets together):**
```hcl
s3_buckets = {
  "dev-1" = { bucket_name = "arj-dev-1" }
  "dev-2" = { bucket_name = "arj-dev-2" }
  "dev-3" = { bucket_name = "arj-dev-3" }
  "dev-4" = { bucket_name = "arj-dev-4" }
}
```

**What you get:**
- ✅ Production bucket isolated (safe)
- ✅ Dev buckets grouped (convenient)
- ✅ Production changes don't affect dev
- ✅ Dev experiments don't risk production

**Choose this if:** You have critical + non-critical resources

---

## Real Examples to Copy

### Example 1: Website with Data, Logs, and Backups

**Situation:** Need 3 buckets that work together

**Your Choice: Group them** (1 tfvars file)

```
S3/my-website/
└── website-storage.tfvars
```

**website-storage.tfvars:**
```hcl
project     = "my-website"
environment = "production"

s3_buckets = {
  "website-data"   = { bucket_name = "arj-website-data-prd" }
  "website-logs"   = { bucket_name = "arj-website-logs-prd" }
  "website-backup" = { bucket_name = "arj-website-backup-prd" }
}
```

**Backend Key:**
```
s3/arj-wkld-a-prd/us-east-1/my-website/terraform.tfstate
```

**Why group?** All 3 are for the same website, always deploy together

---

### Example 2: Different Applications

**Situation:** Need buckets for 3 separate apps

**Your Choice: Separate them** (3 tfvars files)

```
S3/company-apps/
├── app1-storage.tfvars
├── app2-storage.tfvars
└── app3-storage.tfvars
```

**app1-storage.tfvars:**
```hcl
project = "company-apps"
s3_buckets = {
  "app1-data" = { bucket_name = "arj-app1-data-prd" }
}
```

**Backend Keys:**
```
s3/.../company-apps/app1-data/terraform.tfstate
s3/.../company-apps/app2-data/terraform.tfstate
s3/.../company-apps/app3-data/terraform.tfstate
```

**Why separate?** Each app is independent, different update schedules

---

### Example 3: Production vs Development

**Situation:** 1 production bucket + 5 dev buckets

**Your Choice: Mix** (2 tfvars files)

```
S3/data-platform/
├── production.tfvars       (1 bucket)
└── development.tfvars      (5 buckets)
```

**production.tfvars:**
```hcl
project = "data-platform"
environment = "production"
s3_buckets = {
  "production-data" = { bucket_name = "arj-production-data" }
}
```

**development.tfvars:**
```hcl
project = "data-platform"
environment = "development"
s3_buckets = {
  "dev-bucket-1" = { bucket_name = "arj-dev-1" }
  "dev-bucket-2" = { bucket_name = "arj-dev-2" }
  "dev-bucket-3" = { bucket_name = "arj-dev-3" }
  "dev-bucket-4" = { bucket_name = "arj-dev-4" }
  "dev-bucket-5" = { bucket_name = "arj-dev-5" }
}
```

**Backend Keys:**
```
s3/.../data-platform/production-data/terraform.tfstate
s3/.../data-platform/terraform.tfstate
```

**Why mix?** Production is critical (isolate), dev buckets change often (group for convenience)

---

## Migration Scenarios

### Scenario: Split Multi-Resource State

**Before (one tfvars, 3 buckets):**
```
s3/.../project/terraform.tfstate
```

**After (three tfvars, 1 bucket each):**
```
s3/.../project/bucket-1/terraform.tfstate
s3/.../project/bucket-2/terraform.tfstate
s3/.../project/bucket-3/terraform.tfstate
```

**Steps:**
1. Backup current state
2. Split tfvars into 3 files
3. Use `terraform state mv` to move resources to new states
4. Update project workflows to deploy 3 times

**Use Case:** Need to isolate one critical bucket from others

---

### Scenario: Combine Single-Resource States

**Before (three tfvars, 1 bucket each):**
```
s3/.../project/bucket-1/terraform.tfstate
s3/.../project/bucket-2/terraform.tfstate
s3/.../project/bucket-3/terraform.tfstate
```

**After (one tfvars, 3 buckets):**
```
s3/.../project/terraform.tfstate
```

**Steps:**
1. Backup all 3 states
2. Merge tfvars into single file
3. Use migration script to combine states
4. Verify with `terraform plan` (should show 0 changes)

**Use Case:** Simplify management of related resources

---

## Simple Rules

### ✅ When to Use 1 Tfvars File with Multiple Resources

- ✅ All resources for **same application**
- ✅ Resources **always change together**
- ✅ **Same team** manages all resources
- ✅ Resources **depend on each other** (bucket → IAM policy)

**Example:** Website data + logs + backups = 1 tfvars

---

### ✅ When to Use Separate Tfvars Files (1 Resource Each)

- ✅ Resources are **independent**
- ✅ **Different teams** manage different resources
- ✅ Resources **change at different times**
- ✅ Want to **deploy individually**
- ✅ One resource is **critical** (needs isolation)

**Example:** App1 bucket, App2 bucket, App3 bucket = 3 tfvars

---

### 🎯 Quick Decision Tree

```
START: I have X buckets to deploy

├─ Are they for the same application?
│  ├─ YES → Do they change together?
│  │  ├─ YES → Use 1 tfvars file ✅
│  │  └─ NO → Use separate tfvars files ✅
│  │
│  └─ NO → Use separate tfvars files ✅

├─ Is one bucket critical/production?
│  └─ YES → Isolate it (separate tfvars) ✅
│           Group the rest together ✅
```

---

## Common Questions

### ❓ "I have 10 S3 buckets. Do I really need 10 tfvars files?"

**No!** Group them smartly:

- **Critical buckets** (1-2) → Separate tfvars each
- **Related buckets** (3-5) → Group in 1 tfvars
- **Dev/test buckets** (remaining) → Group in 1 tfvars

**Result:** 3-4 tfvars instead of 10 ✅

---

### ❓ "What happens if I put 10 buckets in one tfvars?"

**Backend key becomes:**
```
s3/.../project/terraform.tfstate
```

**Impact:**
- Change 1 bucket → Terraform processes all 10
- Error in 1 bucket → Blocks all 10
- Can't deploy buckets independently

**Recommendation:** Split into 2-3 groups instead

---

### ❓ "Can I change my mind later?"

**Yes!** Use the migration script to:
- Split 1 tfvars → Multiple tfvars (increase isolation)
- Combine multiple tfvars → 1 tfvars (simplify management)

See [STATE-MIGRATION-GUIDE.md](STATE-MIGRATION-GUIDE.md)

---

## Backend Key Patterns Quick Reference

| Your Tfvars | What Backend Key Looks Like |
|-------------|----------------------------|
| **1 resource** | `s3/.../project/bucket-name/terraform.tfstate` |
| **2+ resources** | `s3/.../project/terraform.tfstate` |
| **S3 + IAM** | `multi/.../project/iam-s3/terraform.tfstate` |
| **S3 + IAM + KMS** | `multi/.../project/iam-kms-s3/terraform.tfstate` |

**Examples:**
- 1 bucket: `s3/.../project/data-bucket/terraform.tfstate` ✅ (has subfolder)
- 2+ buckets: `s3/.../project/terraform.tfstate` ✅ (no subfolder!)
- Multi-service: `multi/.../project/iam-s3/terraform.tfstate` ✅ (has subfolder)

---

## Final Recommendation

**Start here:**
1. **Production/Critical** → 1 tfvars per resource (isolate)
2. **Application resources** → Group related ones (convenience)
3. **Dev/Test** → Group many together (speed)

**Example structure:**
```
S3/my-project/
├── production-main.tfvars          (1 critical bucket)
├── application.tfvars              (3 app buckets)
└── development.tfvars              (5 dev buckets)
```

**This gives you:** Safety + Convenience + Speed ✅
