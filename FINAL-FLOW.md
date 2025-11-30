# ✅ CORRECTED WORKFLOW FLOW

## Step-by-Step Process

### 1️⃣ **PR Created in Dev Repo**
```
Location: dev-deployment repo
Trigger: Developer pushes .tfvars changes
```

### 2️⃣ **Dispatch "Validate" Event**
```
From: dev-deployment/.github/workflows/dispatch-to-controller.yml
Job: validate-pr
Trigger: PR opened/synchronize/reopened
Sends: action='validate' to controller
```

### 3️⃣ **Controller Runs Validation**
```
Location: centerlized-pipline- repo
Runs:
  - Terraform Plan
  - OPA Validation
  - Posts comment to PR
  - Adds labels:
    ✅ opa-passed + ready-for-review (if passed)
    ❌ opa-failed + needs-fixes (if failed)
```

### 4️⃣ **Developer Reviews Comment**
```
Location: dev-deployment PR
Developer sees:
  - Terraform plan output
  - OPA validation results
  - Next steps
```

### 5️⃣ **Reviewer Approves PR**
```
Location: dev-deployment PR
Action: Human clicks "Approve" button
```

### 6️⃣ **Dispatch "Merge" Event**
```
From: dev-deployment/.github/workflows/dispatch-to-controller.yml
Job: trigger-merge
Trigger: pull_request_review + state=='approved'
Sends: action='merge' + approver name to controller
```

### 7️⃣ **Controller Checks and Merges**
```
Location: centerlized-pipline- repo
Python script runs:
  1. Reads PR labels (opa-passed or opa-failed)
  2. Checks who approved
  
  If OPA PASSED:
    → Auto-merge PR ✅
    → Add audit trail to commit
    
  If OPA FAILED + Regular User:
    → Block merge completely 🚫
    → Post comment: "Need special approval"
    
  If OPA FAILED + Special Approver:
    → Check for OVERRIDE comment
    → If justified: Merge with warning ⚠️
    → If not: Ask for justification
```

### 8️⃣ **Apply Trigger (if merged)**
```
Location: dev-deployment repo
Trigger: PR merged
Checks: PR has 'opa-passed' label
Sends: action='apply' to controller
```

### 9️⃣ **Controller Runs Terraform Apply**
```
Location: centerlized-pipline- repo
Runs: terraform apply
Posts: Results back to original PR
```

---

## 🔑 Key Points

### OPA Validation Runs ONCE
- During validation step (when PR opened/updated)
- Results saved as PR labels
- Merge step reads labels, doesn't re-run OPA

### Two Separate Dispatch Events
1. **validate** = Run plan + OPA, post comment
2. **merge** = Check labels + merge if approved

### Approval Flow
```
PR Created
    ↓
OPA Validates (adds label)
    ↓
Human Reviews
    ↓
Human Approves
    ↓
Controller Checks Label
    ↓
    ├─→ opa-passed → Auto-merge ✅
    └─→ opa-failed → Block or Override 🚫
```

### Special Approvers
- Configured in: `config/special-approvers.yaml`
- Can override OPA failures
- Must provide justification comment with "OVERRIDE"

---

## 📝 Configuration Files

### Special Approvers
**File**: `config/special-approvers.yaml`
```yaml
special_approvers:
  - pragadeeswarpa
```

### Python Dependencies
**File**: `scripts/requirements.txt`
```
PyGithub==2.1.1
PyYAML==6.0.1
```

---

## ✅ All Requirements Met

- ✅ Dynamic commit messages with audit trail
- ✅ Approval required before merge
- ✅ OPA failure blocks regular users
- ✅ Special approvers can override with justification
- ✅ Apply only triggers if opa-passed label exists
- ✅ Clean Python code (no JavaScript in YAML)
- ✅ Configurable special approvers list

