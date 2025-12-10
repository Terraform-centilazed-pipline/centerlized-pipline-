# 🚀 Complete Centralized Terraform Controller - Workflow Guide

> **Enterprise-Grade Multi-Account Terraform Deployment Platform**  
> Auto-discovery • Policy Validation • Automated Deployment • Full Audit Trail

---

## 📚 Table of Contents

1. [Architecture Overview](#-architecture-overview)
2. [How It Works - Step by Step](#-how-it-works---step-by-step)
3. [Repository Structure](#-repository-structure)
4. [Workflow Modes](#-workflow-modes)
5. [Security Gates](#-security-gates)
6. [File Discovery & Processing](#-file-discovery--processing)
7. [Branch Strategy](#-branch-strategy)
8. [Real-World Scenarios](#-real-world-scenarios)
9. [Troubleshooting](#-troubleshooting)
10. [Best Practices](#-best-practices)

---

## 🏗️ Architecture Overview

### High-Level Components

```
┌─────────────────────────────────────────────────────────────────┐
│                    YOUR INFRASTRUCTURE REPOS                     │
│  (dev-deployment, prod-deployment, staging-deployment, etc.)    │
│                                                                  │
│  Accounts/                                                       │
│    ├── account-1/                                               │
│    │   ├── us-east-1/                                           │
│    │   │   ├── project-1/                                       │
│    │   │   │   ├── terraform.tfvars  ← You edit these          │
│    │   │   │   └── deployment.json                              │
│    │   │   └── project-2/                                       │
│    │   │       ├── terraform.tfvars                             │
│    │   │       └── deployment.json                              │
│    │   └── eu-west-1/                                           │
│    └── account-2/                                               │
└─────────────────────────────────────────────────────────────────┘
                          │
                          │ Git Push
                          ↓
┌─────────────────────────────────────────────────────────────────┐
│                  GITHUB ACTIONS (Source Repo)                    │
│  - Auto-create PR                                                │
│  - Dispatch event to Controller                                  │
└─────────────────────────────────────────────────────────────────┘
                          │
                          │ Repository Dispatch
                          ↓
┌─────────────────────────────────────────────────────────────────┐
│           CENTRALIZED CONTROLLER REPOSITORY                      │
│  ┌────────────────────────────────────────────────────────┐    │
│  │  1. Deployment Discovery                                │    │
│  │     - Auto-detect changed accounts                      │    │
│  │     - Find associated tfvars & JSON files               │    │
│  │     - Build deployment matrix                           │    │
│  └────────────────────────────────────────────────────────┘    │
│                          ↓                                       │
│  ┌────────────────────────────────────────────────────────┐    │
│  │  2. Terraform Plan (Parallel Processing)                │    │
│  │     - Run plan for each deployment                      │    │
│  │     - Generate JSON outputs for OPA                     │    │
│  │     - Capture resource changes                          │    │
│  └────────────────────────────────────────────────────────┘    │
│                          ↓                                       │
│  ┌────────────────────────────────────────────────────────┐    │
│  │  3. OPA Policy Validation                               │    │
│  │     - Validate all plans against policies               │    │
│  │     - Check: tags, naming, security, compliance         │    │
│  │     - Severity levels: Critical, High, Medium, Low      │    │
│  └────────────────────────────────────────────────────────┘    │
│                          ↓                                       │
│  ┌────────────────────────────────────────────────────────┐    │
│  │  4. PR Comment & Auto-Merge                             │    │
│  │     - Post detailed results to PR                       │    │
│  │     - Auto-merge if OPA passed + approved               │    │
│  │     - Block if violations found                         │    │
│  └────────────────────────────────────────────────────────┘    │
│                          ↓                                       │
│  ┌────────────────────────────────────────────────────────┐    │
│  │  5. Terraform Apply (Post-Merge)                        │    │
│  │     - Deploy to actual infrastructure                   │    │
│  │     - Post deployment results                           │    │
│  │     - Update audit trail                                │    │
│  └────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

### Key Innovation: **Auto-Discovery**

Unlike traditional approaches that require manual configuration, this system:
- ✅ Automatically discovers changed accounts from file paths
- ✅ Processes multiple deployments in parallel
- ✅ No pipeline updates needed for new accounts
- ✅ Scales infinitely

---

## 🔄 How It Works - Step by Step

### Phase 1: Developer Makes Changes

```bash
# Developer edits configuration
cd Accounts/aws-dev-account/us-east-1/s3-project/
vim terraform.tfvars  # Edit S3 bucket configuration

# Commit and push
git add .
git commit -m "Add new S3 bucket for analytics"
git push origin feature/new-s3-bucket
```

**What Happens:**
1. GitHub Actions in source repo detects push
2. Auto-creates PR: "🔧 Terraform configuration updates for [aws-dev-account]"
3. Sends `repository_dispatch` event to Controller

---

### Phase 2: Centralized Controller - Validation Mode

#### Step 1: **Checkout Repositories**

```yaml
# Controller workflow receives dispatch event
action: 'validate'
pr_number: 123
pr_head_ref: 'feature/new-s3-bucket'  # PR branch
base_ref: 'main'                       # Target branch
changed_files: [
  "Accounts/aws-dev-account/us-east-1/s3-project/terraform.tfvars",
  "Accounts/aws-dev-account/us-east-1/s3-project/deployment.json"
]
```

**Checkout Logic:**
- **Controller Repo**: Always checkout `main` (policies & scripts)
- **Source Repo (Validation)**: Checkout PR branch (`pr_head_ref`)
- **OPA Policies**: Always checkout latest

#### Step 2: **Deployment Discovery**

```python
# Python orchestrator auto-discovers deployments
terraform-deployment-orchestrator-enhanced.py discover \
  --changed-files "Accounts/aws-dev-account/.../terraform.tfvars ..." \
  --output-summary deployments.json

# Output: deployments.json
{
  "deployments": [
    {
      "account_name": "aws-dev-account",
      "region": "us-east-1",
      "project": "s3-project",
      "deployment_dir": "Accounts/aws-dev-account/us-east-1/s3-project",
      "tfvars_file": "terraform.tfvars",
      "json_file": "deployment.json",
      "environment": "development"
    }
  ],
  "total_deployments": 1
}
```

**Discovery Intelligence:**
- ✅ Finds all related files (`.tfvars`, `.json`, `.yaml`)
- ✅ Deduplicates multiple files in same folder
- ✅ Validates file existence before processing
- ✅ Supports multiple tfvars per deployment

#### Step 3: **Terraform Plan (Parallel)**

```bash
# Orchestrator runs terraform plan for each deployment
for deployment in deployments:
  cd ${deployment.deployment_dir}
  
  # Initialize Terraform
  terraform init \
    -backend-config="bucket=terraform-state-bucket" \
    -backend-config="key=${account}/${region}/${project}/terraform.tfstate"
  
  # Run plan with JSON output
  terraform plan \
    -var-file="${deployment.tfvars_file}" \
    -out=tfplan
  
  # Convert to JSON for OPA
  terraform show -json tfplan > plan.json
```

**Plan Output:**
```json
{
  "resource_changes": [
    {
      "type": "aws_s3_bucket",
      "change": {
        "actions": ["create"],
        "after": {
          "bucket": "analytics-data-dev",
          "tags": {
            "Environment": "development",
            "Project": "analytics",
            "ManagedBy": "terraform"
          }
        }
      }
    }
  ]
}
```

#### Step 4: **OPA Policy Validation**

```bash
# Python OPA validator processes all plans
opa-validator.py \
  --opa-policies ../opa-policies/terraform \
  --plans-dir canonical-plan \
  --output opa-results.json

# Validates each resource against policies:
# - Required tags present?
# - Naming conventions followed?
# - Security best practices met?
# - Compliance requirements satisfied?
```

**OPA Results:**
```json
{
  "summary": {
    "plans_validated": 1,
    "total_violations": 0,
    "critical_violations": 0,
    "high_violations": 0,
    "services_detected": ["s3"]
  },
  "validation_status": "passed"
}
```

#### Step 5: **Post PR Comment**

Controller posts comprehensive comment to PR:

```markdown
## 🚀 Centralized Terraform Controller Results

> ✅ **Overall Status**: 🟢 **APPROVED**
> 📦 **Source**: `dev-deployment`
> 🔀 **PR**: [#123](link) (branch: `feature/new-s3-bucket`)

### 📊 Terraform Plan Summary

| Metric | Value |
|--------|-------|
| 📋 Total Deployments | **1** |
| ✅ Successful Plans | **1** |
| 🔄 Has Changes | **Yes** |

### ✅ Plan Validation Results

#### 🎯 aws-dev-account / us-east-1 / s3-project

| | |
|---|---|
| 🏗️ Services | s3 |
| 🌍 Environment | development |
| 👤 Commit Author | developer-name |

**📊 Change Summary** (1 total operations):

| Operation | Count | Description |
|-----------|-------|-------------|
| 🟢 **Create** | **1** resource(s) | New resources will be provisioned |

### 🛡️ OPA Policy Validation

✅ **Status**: **PASSED** - All policies compliant!

| Metric | Value |
|--------|-------|
| 📋 Plans Validated | **1** |
| ✅ Policy Compliance | **100%** |

**What happens next?**
1. ✅ This PR will be **automatically merged** after approval
2. 🚀 Terraform **apply** will execute to deploy resources
```

---

### Phase 3: PR Approval & Merge

#### Approval Check

```python
# handle_pr_merge.py checks for PR approval
if opa_status == "passed":
    if pr_is_approved():
        # Build audit trail commit message
        commit_msg = f"""[Terraform] {pr_title}

Merged after approval and OPA validation

PR #{pr_number}: {pr_title}
Author: {pr_author}
Approved-by: {approver}
Branch: {pr_head_ref} to {base_ref}

Files changed ({file_count}):
{changed_files_list}

OPA: PASSED
Workflow: {workflow_url}
PR Link: {pr_url}
Merged at: {timestamp}"""
        
        # Auto-merge PR
        merge_pr(commit_message=commit_msg)
        add_labels(["opa-passed", "ready-for-review"])
```

---

### Phase 4: Terraform Apply (Post-Merge)

#### Apply Trigger

When PR is merged:
1. Source repo detects merge event
2. Checks for `opa-passed` label (security gate)
3. If present, sends `terraform_apply` dispatch to Controller

#### Apply Mode Execution

**Key Difference: Branch Checkout**

```yaml
# Apply mode uses MERGED branch (base_ref), not PR branch
ref: ${{ 
  github.event.client_payload.action == 'apply' 
    && github.event.client_payload.base_ref      # ← Uses 'main' (or develop/staging)
    || github.event.client_payload.pr_head_ref   # ← Plan mode uses PR branch
}}
```

**Why This Matters:**
- ✅ Deploys code that was actually merged
- ✅ Works with any branching strategy (main/develop/staging)
- ✅ Prevents deploying from deleted PR branches

#### Apply Discovery

```bash
# Apply mode discovery with file filtering
FILTERED_FILES=$(echo "$CHANGED_FILES_JSON" | jq -r '.[] | select(
  (endswith(".tfvars") or endswith(".json")) and
  (startswith("Accounts/") or startswith("configs/"))
)' | tr '\n' ' ')

# Discover deployments with working directory
python3 terraform-deployment-orchestrator-enhanced.py discover \
  --changed-files "$FILTERED_FILES" \
  --working-dir "$(pwd)" \          # ← Ensures correct path resolution
  --output-summary deployments.json
```

**File Filtering:**
- ✅ Only processes deployment files (`.tfvars`, `.json`)
- ✅ Excludes workflow files (`.github/workflows/*.yml`)
- ✅ Only includes `Accounts/` or `configs/` paths

#### Apply Execution

```bash
# Run terraform apply for each deployment
terraform-deployment-orchestrator-enhanced.py apply \
  --changed-files "$FILTERED_FILES" \
  --output-summary apply-results.json

# Results posted back to original PR:
{
  "summary": {
    "total": 1,
    "successful": 1,
    "failed": 0
  },
  "successful": [
    {
      "deployment": {
        "account_name": "aws-dev-account",
        "region": "us-east-1",
        "project": "s3-project"
      },
      "resources_created": 1,
      "resources_updated": 0,
      "resources_destroyed": 0
    }
  ]
}
```

---

## 📁 Repository Structure

### Centralized Controller Repository

```
centerlized-pipline-/
├── .github/
│   └── workflows/
│       └── centralized-controller.yml    # Main orchestration workflow
│
├── scripts/
│   ├── terraform-deployment-orchestrator-enhanced.py  # Core discovery & execution
│   ├── opa-validator.py                               # OPA policy validation
│   ├── pre-deployment-validator.py                    # Pre-flight checks
│   └── handle_pr_merge.py                             # Auto-merge logic
│
├── templates/
│   └── terraform-backend-template.tf     # Backend configuration template
│
├── accounts.yaml                         # Account metadata
├── approvers-config.yaml                 # Who can override OPA
└── deployment-rules.yaml                 # Deployment constraints
```

### Source/Dev Repository

```
dev-deployment/
├── .github/
│   └── workflows/
│       └── pr-workflow.yml               # PR creation & dispatch
│
├── Accounts/
│   ├── aws-dev-account/
│   │   ├── us-east-1/
│   │   │   ├── s3-project/
│   │   │   │   ├── terraform.tfvars     # Your configuration
│   │   │   │   ├── deployment.json      # Deployment metadata
│   │   │   │   └── README.md
│   │   │   └── ec2-project/
│   │   │       ├── terraform.tfvars
│   │   │       └── deployment.json
│   │   └── eu-west-1/
│   │       └── rds-project/
│   │           ├── terraform.tfvars
│   │           └── deployment.json
│   │
│   ├── aws-prod-account/
│   │   └── us-east-1/
│   │       └── vpc-project/
│   │           ├── terraform.tfvars
│   │           └── deployment.json
│   │
│   └── aws-staging-account/
│       └── ...
│
└── README.md
```

### OPA Policies Repository

```
opa-policies/
├── terraform/
│   ├── naming.rego              # Naming conventions
│   ├── tagging.rego             # Required tags
│   ├── s3.rego                  # S3-specific policies
│   ├── ec2.rego                 # EC2-specific policies
│   ├── security.rego            # Security best practices
│   └── compliance.rego          # Compliance requirements
│
└── README.md
```

---

## 🔀 Workflow Modes

### Mode 1: **Validate (Plan)**

**Trigger:** PR created or updated  
**Action:** `validate`  
**Branch:** Checkout PR branch (`pr_head_ref`)

**Steps:**
1. Get changed files from PR API
2. Filter deployment files only
3. Discover deployments
4. Run terraform plan
5. OPA validation
6. Post results to PR
7. Wait for approval

### Mode 2: **Merge**

**Trigger:** PR approved  
**Action:** `merge`  
**Branch:** Still on PR branch

**Steps:**
1. Check OPA status from labels
2. If passed + approved → auto-merge
3. If failed → check for special approver override
4. Build audit trail commit message
5. Merge PR with squash commit

### Mode 3: **Apply (Deploy)**

**Trigger:** PR merged  
**Action:** `apply`  
**Branch:** Checkout target branch (`base_ref`) ← **KEY DIFFERENCE**

**Steps:**
1. Get changed files from merge event payload
2. **Filter deployment files** (exclude workflow YAML)
3. Discover deployments with `--working-dir`
4. Run terraform apply
5. Post deployment results to original PR

---

## 🔐 Security Gates

### Gate 1: Pre-Deployment Validation

**When:** Before terraform plan  
**Checks:**
- File structure correctness
- Required files present
- Valid JSON/YAML syntax
- Account metadata exists

**Failure:** PR closed immediately

### Gate 2: OPA Policy Validation

**When:** After terraform plan  
**Checks:**
- Required tags present
- Naming conventions followed
- Security best practices met
- Compliance requirements satisfied

**Severity Levels:**
- 🔴 **Critical**: Must fix (blocks merge)
- 🟠 **High**: Should fix (blocks merge)
- 🟡 **Medium**: Review recommended
- 🔵 **Low**: Nice to have

**Failure Options:**
- **Regular Users**: Completely blocked
- **Special Approvers**: Can override with justification

### Gate 3: PR Approval

**When:** After OPA validation passes  
**Who:** Any authorized reviewer  
**Result:** Auto-merge when approved

### Gate 4: Apply Label Check

**When:** PR merge triggers apply  
**Checks:** PR has `opa-passed` label  
**Failure:** Apply blocked (security violation)

---

## 🔍 File Discovery & Processing

### Discovery Algorithm

```python
def find_deployments(changed_files):
    """
    Auto-discover deployments from changed files
    
    Logic:
    1. Parse file paths to extract account/region/project
    2. Find all related files in same deployment folder
    3. Deduplicate using file-based tracking (not folder-based)
    4. Validate file existence
    """
    seen_files = set()  # Track unique files
    deployments = []
    
    for file_path in changed_files:
        # Skip non-deployment files
        if not file_path.startswith('Accounts/'):
            continue
        
        if not file_path.endswith(('.tfvars', '.json', '.yaml', '.yml')):
            continue
        
        # Parse path: Accounts/account-name/region/project/file.tfvars
        parts = Path(file_path).parts
        account_name = parts[1]
        region = parts[2]
        project = parts[3]
        
        deployment_dir = Path("Accounts") / account_name / region / project
        
        # Find all deployment files in this folder
        tfvars_files = list(deployment_dir.glob("*.tfvars"))
        json_files = list(deployment_dir.glob("*.json"))
        
        # Create deployment entry for each unique tfvars
        for tfvars_file in tfvars_files:
            if str(tfvars_file) in seen_files:
                continue
            
            seen_files.add(str(tfvars_file))
            
            deployments.append({
                "account_name": account_name,
                "region": region,
                "project": project,
                "deployment_dir": str(deployment_dir),
                "tfvars_file": tfvars_file.name,
                "json_file": json_files[0].name if json_files else None
            })
    
    return deployments
```

### File Filtering (Apply Mode)

```bash
# Filter changed files to only include deployment files
FILTERED_FILES=$(echo "$CHANGED_FILES_JSON" | jq -r '.[] | select(
  # Include only configuration files
  (endswith(".tfvars") or endswith(".json") or endswith(".yaml") or endswith(".yml")) and
  
  # Include only deployment directories
  (startswith("Accounts/") or startswith("configs/"))
)' | tr '\n' ' ')
```

**Why Filtering Matters:**
- ❌ **Without filtering**: Workflow YAML files contaminate discovery
- ✅ **With filtering**: Only actual deployment files processed
- ✅ **Result**: Clean, accurate deployment detection

---

## 🌿 Branch Strategy

### Dynamic Branch Checkout

```yaml
# Conditional checkout based on action
ref: ${{ 
  github.event.client_payload.action == 'apply' 
    && github.event.client_payload.base_ref      # Apply: Target branch (main/develop/staging)
    || github.event.client_payload.pr_head_ref   # Plan: PR branch (feature/xyz)
}}
```

### Supported Branching Models

#### GitFlow

```
PR: feature/new-s3 → develop
Plan Mode: Checkout feature/new-s3
Apply Mode: Checkout develop ✅

PR: release/v1.0 → main
Plan Mode: Checkout release/v1.0
Apply Mode: Checkout main ✅
```

#### GitHub Flow

```
PR: feature/new-s3 → main
Plan Mode: Checkout feature/new-s3
Apply Mode: Checkout main ✅
```

#### Trunk-Based

```
PR: feature/hotfix → main
Plan Mode: Checkout feature/hotfix
Apply Mode: Checkout main ✅

PR: feature/staging-test → staging
Plan Mode: Checkout feature/staging-test
Apply Mode: Checkout staging ✅
```

### Why Dynamic Branching?

**Problem with Hardcoded 'main':**
```yaml
# Bad: Hardcoded branch
ref: ${{ github.event.client_payload.action == 'apply' && 'main' || ... }}
```

❌ Fails when merging to `develop`  
❌ Fails when merging to `staging`  
❌ Only works for simple GitHub Flow

**Solution with Dynamic base_ref:**
```yaml
# Good: Dynamic branch
ref: ${{ github.event.client_payload.action == 'apply' && github.event.client_payload.base_ref || ... }}
```

✅ Works with any target branch  
✅ Supports complex branching strategies  
✅ Deploys what was actually merged

---

## 🎯 Real-World Scenarios

### Scenario 1: Single Account, Single Change ✅

**Action:** Add new S3 bucket

```bash
# Edit file
vim Accounts/aws-dev/us-east-1/s3-project/terraform.tfvars

# Push
git add . && git commit -m "Add analytics bucket" && git push
```

**Workflow:**
1. PR auto-created: #123
2. Discovery finds: 1 deployment (aws-dev/us-east-1/s3-project)
3. Plan runs: 1 resource to create
4. OPA validates: PASSED
5. Approved → Auto-merged
6. Apply runs: 1 bucket created ✅

### Scenario 2: Multiple Accounts, Multiple Changes ✅

**Action:** Update configs across 3 accounts

```bash
# Edit multiple files
vim Accounts/aws-dev/us-east-1/s3-project/terraform.tfvars
vim Accounts/aws-staging/us-east-1/s3-project/terraform.tfvars
vim Accounts/aws-prod/us-east-1/s3-project/terraform.tfvars

# Push all changes
git add . && git commit -m "Update S3 configs across environments" && git push
```

**Workflow:**
1. PR auto-created: #124
2. Discovery finds: **3 deployments** (parallel processing)
3. Plan runs: 3 plans simultaneously
4. OPA validates: All 3 plans → PASSED
5. Approved → Auto-merged
6. Apply runs: All 3 buckets updated ✅

### Scenario 3: OPA Violation - Blocked ❌

**Action:** Create bucket without required tags

```hcl
# terraform.tfvars (missing Environment tag)
bucket_name = "my-new-bucket"
tags = {
  Project = "analytics"
  # Missing: Environment = "development"
}
```

**Workflow:**
1. PR auto-created: #125
2. Discovery finds: 1 deployment
3. Plan runs: 1 resource to create
4. OPA validates: **FAILED** (missing required tag)
5. Labels added: `opa-failed`, `blocked`
6. Comment posted: "❌ Policy violations found"
7. PR **cannot be merged** (blocked) ❌
8. Developer fixes → Push update → Re-validation

### Scenario 4: OPA Override (Special Approver) ⚠️

**Action:** Emergency production fix

```bash
# Critical hotfix needed despite OPA concerns
vim Accounts/aws-prod/us-east-1/vpc-project/terraform.tfvars
git add . && git commit -m "Emergency: Fix production network issue" && git push
```

**Workflow:**
1. PR auto-created: #126
2. OPA validates: FAILED (security concern)
3. Special approver (@pragadeeswarpa) approves
4. Posts comment: "OVERRIDE: Production outage requires immediate fix. Will remediate in follow-up PR #127"
5. Auto-merged with warning labels: `opa-override`, `special-approval`
6. Apply runs with audit trail: "⚠️ OPA OVERRIDE by @pragadeeswarpa"
7. Follow-up PR created to fix violation ✅

### Scenario 5: JSON-Only Changes ✅

**Action:** Update deployment metadata

```json
// deployment.json (no tfvars changes)
{
  "environment": "development",
  "cost_center": "engineering-updated",
  "owner": "new-team"
}
```

**Workflow:**
1. PR auto-created: #127
2. Discovery finds: Associated `terraform.tfvars` via glob pattern
3. Plan runs: Using existing tfvars with updated JSON metadata
4. OPA validates: PASSED
5. Apply runs: Metadata updated ✅

**Key:** JSON changes trigger associated tfvars discovery automatically

### Scenario 6: Multiple tfvars in Same Folder ✅

**Action:** Deploy with environment-specific configs

```
Accounts/aws-dev/us-east-1/multi-env-project/
├── terraform-dev.tfvars
├── terraform-staging.tfvars
├── deployment-dev.json
└── deployment-staging.json
```

```bash
# Edit both
vim terraform-dev.tfvars terraform-staging.tfvars
git add . && git commit -m "Update both dev and staging configs" && git push
```

**Workflow:**
1. PR auto-created: #128
2. Discovery finds: **2 deployments** (same folder, different tfvars)
3. Plan runs: 2 plans (dev and staging)
4. OPA validates: Both plans → PASSED
5. Apply runs: Both environments updated ✅

**Key:** File-based deduplication (not folder-based) enables this

### Scenario 7: Workflow File + Deployment File ✅

**Action:** Update workflow and configuration together

```bash
# Edit both workflow and config
vim .github/workflows/pr-workflow.yml
vim Accounts/aws-dev/us-east-1/s3-project/terraform.tfvars
git add . && git commit -m "Update workflow and add S3 bucket" && git push
```

**Workflow:**
1. PR auto-created: #129
2. Changed files: `[".github/workflows/pr-workflow.yml", "Accounts/.../terraform.tfvars"]`
3. **File filtering** removes workflow YAML
4. Discovery finds: 1 deployment (only config file)
5. Plan runs: Only for actual infrastructure change
6. Apply runs: Only deploys S3 bucket ✅

**Key:** Workflow YAML excluded from deployment discovery

---

## 🐛 Troubleshooting

### Issue 1: "Found 0 deployments" in Apply Mode

**Symptoms:**
```
Apply mode - filtered deployment files: 
ℹ️ No deployments found for apply
```

**Causes:**
1. ❌ Workflow YAML files in changed files list
2. ❌ Missing `--working-dir` parameter
3. ❌ Wrong branch checked out

**Solutions:**
```bash
# Check 1: File filtering
FILTERED_FILES=$(echo "$CHANGED_FILES_JSON" | jq -r '.[] | select(
  (endswith(".tfvars") or endswith(".json")) and
  (startswith("Accounts/") or startswith("configs/"))
)')

# Check 2: Working directory parameter
python3 orchestrator.py discover \
  --changed-files "$FILTERED_FILES" \
  --working-dir "$(pwd)"  # ← Must be present

# Check 3: Branch checkout
ref: ${{ base_ref }}  # Not hardcoded 'main'
```

### Issue 2: Duplicate Method Override

**Symptoms:**
- Multiple tfvars in same folder not processed
- Only first file discovered

**Cause:**
```python
# Bad: Folder-based deduplication
deployment_paths = set()
if deployment_dir in deployment_paths:
    continue  # Skips second tfvars!
```

**Solution:**
```python
# Good: File-based deduplication
seen_files = set()
if str(tfvars_file) in seen_files:
    continue
seen_files.add(str(tfvars_file))  # Allows multiple tfvars per folder
```

### Issue 3: Files Not Found in Apply Mode

**Symptoms:**
```
Checking if files exist:
  ❌ Accounts/test/terraform.tfvars not found
```

**Cause:**
- Checked out wrong branch (PR branch instead of target branch)

**Solution:**
```yaml
# Ensure dynamic branch checkout
ref: ${{ 
  action == 'apply' 
    && base_ref          # ← Target branch (main/develop/staging)
    || pr_head_ref 
}}
```

### Issue 4: OPA Validation Errors

**Symptoms:**
```
❌ OPA validation error - unexpected exit code: 2
No OPA results file found
```

**Causes:**
1. OPA binary not installed
2. Policy files syntax errors
3. Plan JSON structure mismatch

**Solutions:**
```bash
# Check OPA installation
opa version

# Test policy syntax
opa fmt policy.rego --diff

# Test policy loading
opa eval -d policies/ "data"

# Validate plan JSON structure
jq 'keys' plan.json
```

---

## ✅ Best Practices

### 1. Repository Organization

```
# Good: Clear hierarchy
Accounts/
  ├── aws-account-name/
  │   ├── us-east-1/
  │   │   ├── project-name/
  │   │   │   ├── terraform.tfvars
  │   │   │   └── deployment.json

# Bad: Flat structure
Accounts/
  ├── aws-dev-s3.tfvars
  ├── aws-prod-s3.tfvars
  └── aws-staging-s3.tfvars
```

### 2. Naming Conventions

```
# Tfvars files
terraform.tfvars              # Standard
terraform-{env}.tfvars        # Environment-specific

# JSON files
deployment.json               # Metadata
deployment-{env}.json         # Environment-specific

# Avoid
config.tfvars                 # Too generic
my-awesome-config.tfvars      # Non-standard
```

### 3. Branching Strategy

```
# Good: Feature branches
feature/add-s3-bucket
feature/update-vpc-config
hotfix/prod-security-issue

# Good: Environment branches
develop  ← Feature PRs
staging  ← Release candidates
main     ← Production

# Bad: Direct commits
main ← Direct commit (bypasses validation!)
```

### 4. Commit Messages

```
# Good: Descriptive
Add S3 bucket for analytics data storage
Update VPC configuration for multi-AZ setup
Fix security group rules for production RDS

# Bad: Vague
Update config
Fix stuff
Changes
```

### 5. PR Descriptions

```markdown
# Good: Detailed
## Summary
Adding new S3 bucket for analytics team

## Changes
- New bucket: analytics-data-prod
- Versioning enabled
- Encryption: AES256
- Lifecycle policy: 90 days

## Impacts
- New monthly cost: ~$50
- Storage: Up to 1TB
- Access: Analytics team only

# Bad: Empty
(no description)
```

### 6. OPA Policy Design

```rego
# Good: Clear severity levels
violation[msg] {
  resource := input.resource_changes[_]
  resource.type == "aws_s3_bucket"
  not resource.change.after.tags.Environment
  
  msg := {
    "severity": "high",
    "message": "S3 bucket missing required 'Environment' tag",
    "resource": resource.address
  }
}

# Bad: Unclear severity
deny[msg] {
  # Missing severity level
  msg := "Bucket has no tags"
}
```

### 7. Error Handling

```python
# Good: Graceful degradation
try:
    deployments = discover_deployments(changed_files)
except FileNotFoundError as e:
    logger.error(f"File not found: {e}")
    return {"deployments": [], "error": str(e)}
except Exception as e:
    logger.error(f"Discovery failed: {e}")
    return {"deployments": [], "error": "Unknown error"}

# Bad: Silent failure
try:
    deployments = discover_deployments(changed_files)
except:
    pass  # No logging, no error handling
```

---

## 📊 Metrics & Monitoring

### Key Metrics to Track

1. **Deployment Success Rate**
   - Target: >95% successful applies
   - Track failures by account/region

2. **OPA Validation Pass Rate**
   - Target: >90% pass rate
   - Track common violations

3. **Average PR Merge Time**
   - Target: <2 hours for dev, <24 hours for prod
   - Track approval bottlenecks

4. **Policy Override Frequency**
   - Target: <5% of all PRs
   - Audit all overrides

5. **Discovery Accuracy**
   - Target: 100% correct deployment detection
   - Track false positives/negatives

### Monitoring Dashboards

```yaml
# GitHub Actions metrics (native)
- Workflow run duration
- Success/failure rates
- Action usage minutes

# Custom metrics (CloudWatch/Datadog)
- Deployments per day/week
- OPA violation trends
- Most violated policies
- Busiest accounts/regions
```

---

## 🚀 Advanced Features

### Parallel Deployment Processing

```python
# Orchestrator processes multiple deployments concurrently
async def process_deployments(deployments):
    tasks = [
        asyncio.create_task(run_plan(deployment))
        for deployment in deployments
    ]
    results = await asyncio.gather(*tasks)
    return results
```

**Benefits:**
- 10 accounts: ~5 minutes (parallel) vs ~50 minutes (sequential)
- Scales with account count

### Intelligent Caching

```yaml
# Terraform plugins (shared across all runs)
- uses: actions/cache@v4
  with:
    path: ~/.terraform.d/plugin-cache
    key: terraform-plugins-${{ terraform_version }}

# Terraform modules (per-controller repo)
- uses: actions/cache@v4
  with:
    path: **/.terraform/modules
    key: terraform-modules-${{ hashFiles('main.tf') }}

# OPA policies (shared)
- uses: actions/cache@v4
  with:
    path: opa-policies
    key: opa-policies-${{ hashFiles('**/*.rego') }}
```

**Benefits:**
- 60% faster workflow runs
- Reduced network usage

### Dynamic Backend Configuration

```python
# Auto-generate backend config per deployment
backend_config = f"""
terraform {{
  backend "s3" {{
    bucket = "terraform-state-{account_id}"
    key    = "{account}/{region}/{project}/terraform.tfstate"
    region = "us-east-1"
    
    dynamodb_table = "terraform-locks"
    encrypt        = true
  }}
}}
"""
```

**Benefits:**
- Isolated state per deployment
- No manual backend config needed

---

## 🎓 Learning Path

### For Developers (Using the System)

1. ✅ Understand repository structure
2. ✅ Learn tfvars file format
3. ✅ Know how to create PRs
4. ✅ Understand OPA validation results
5. ✅ Know when approval is needed

### For DevOps Engineers (Maintaining the System)

1. ✅ Master GitHub Actions workflows
2. ✅ Understand Python orchestrator logic
3. ✅ Learn OPA policy language
4. ✅ Know Terraform state management
5. ✅ Understand multi-account AWS setup
6. ✅ Master git branching strategies
7. ✅ Debug workflow failures

### For Architects (Designing Similar Systems)

1. ✅ Auto-discovery patterns
2. ✅ Event-driven architecture
3. ✅ Policy-as-code implementation
4. ✅ Multi-tenant deployment strategies
5. ✅ Security gate design
6. ✅ Audit trail best practices

---

## 📚 Additional Resources

### Documentation
- [Terraform Best Practices](docs/TERRAFORM-BEST-PRACTICES.md)
- [OPA Policy Guide](../opa-policies/README.md)
- [Troubleshooting Guide](docs/TROUBLESHOOTING.md)

### Tools
- [Terraform](https://www.terraform.io/)
- [Open Policy Agent](https://www.openpolicyagent.org/)
- [GitHub Actions](https://docs.github.com/en/actions)

### Community
- GitHub Issues: Report bugs
- Discussions: Ask questions
- Pull Requests: Contribute improvements

---

## 🏆 Success Criteria

Your system is working correctly when:

✅ **Discovery**
- Automatically finds all changed deployments
- No manual configuration needed for new accounts
- Handles multiple tfvars per folder

✅ **Validation**
- OPA validates all plans before merge
- Critical violations block deployment
- Special approvers can override with justification

✅ **Deployment**
- Apply only runs for opa-passed PRs
- Files found in correct branch
- Parallel processing works correctly

✅ **Audit**
- Every merge has detailed commit message
- PR comments show full validation results
- Override justifications are captured

✅ **Reliability**
- 95%+ successful deployments
- <5% false positives from OPA
- Clear error messages on failures

---

## 🎯 Quick Reference Card

```bash
# Repository Dispatch Events
terraform_pr      → Validate (Plan + OPA)
terraform_apply   → Deploy (Apply)
terraform_merge   → Check approval + merge

# Workflow Actions
validate → Plan mode (PR branch)
apply    → Deploy mode (target branch)
merge    → Approval check + auto-merge

# Key Files
terraform.tfvars               → Your configuration
deployment.json                → Metadata
terraform-deployment-orchestrator-enhanced.py → Discovery engine
opa-validator.py               → Policy validation
handle_pr_merge.py             → Auto-merge logic

# Labels
opa-passed          → OPA validation succeeded
opa-failed          → OPA validation failed
blocked             → Cannot merge (no override)
requires-special-approval → Need special approver
opa-override        → Special approver overrode
ready-to-merge      → Approved + validated

# Common Commands
# Discover deployments
python3 orchestrator.py discover --changed-files "..." --debug

# Run plan
python3 orchestrator.py plan --changed-files "..." --debug

# Run apply
python3 orchestrator.py apply --changed-files "..." --debug

# Validate with OPA
python3 opa-validator.py --plans-dir canonical-plan --debug
```

---

**🌟 Your centralized Terraform controller is enterprise-grade, scalable, and production-ready!**

For questions or issues, check the troubleshooting section or open a GitHub issue.
