# Complete Workflow Flow

## 📊 End-to-End Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                      DEV REPOSITORY WORKFLOW                         │
└─────────────────────────────────────────────────────────────────────┘

1. Developer pushes .tfvars changes to feature branch
   ↓
2. Auto-create PR job runs
   - Creates PR automatically
   - PR Title: "🔧 Terraform configuration updates for [accounts]"
   ↓
3. notify-controller job runs (on PR opened/updated)
   - Collects PR details (number, title, branch, author, changed files)
   - Sends repository_dispatch event: "terraform_pr"
   ↓
   
┌─────────────────────────────────────────────────────────────────────┐
│                   CONTROLLER REPOSITORY WORKFLOW                     │
└─────────────────────────────────────────────────────────────────────┘

4. Centralized Controller receives "terraform_pr" event
   - Clones dev repo at PR branch
   - Detects changed files
   ↓
5. Checkov validation (if .tfvars changed)
   - Validates Terraform files
   - Checks security compliance
   ↓
6. OPA Policy validation
   - Validates against custom policies
   - Checks: tags, naming, compliance
   - Outputs: validation_status (passed/failed)
   ↓
7. Python Script: handle_pr_merge.py
   ├─ If OPA PASSED:
   │  ├─ Check for PR approval
   │  │  ├─ No approval yet
   │  │  │  ├─ Post comment: "Waiting for approval"
   │  │  │  └─ Exit (wait for approval)
   │  │  └─ Approved
   │  │     ├─ Add labels: opa-passed, ready-to-merge
   │  │     ├─ Build dynamic commit message:
   │  │     │  - PR #, title, author, approver
   │  │     │  - Changed files list
   │  │     │  - OPA status, workflow URL
   │  │     │  - Timestamp
   │  │     ├─ Merge PR (squash)
   │  │     ├─ Set output: merged=true, merge_sha=[sha]
   │  │     └─ Post success comment
   │  │
   └─ If OPA FAILED:
      ├─ Check for special approver
      │  ├─ No special approver
      │  │  ├─ Add labels: opa-failed, blocked, requires-special-approval
      │  │  ├─ Post blocking comment
      │  │  ├─ Set output: merged=false, blocked=true
      │  │  └─ Exit (completely blocked)
      │  │
      │  └─ Special approver found
      │     ├─ Check for OVERRIDE comment
      │     │  ├─ No justification yet
      │     │  │  ├─ Request justification comment
      │     │  │  └─ Exit (wait for justification)
      │     │  │
      │     │  └─ Justification provided
      │     │     ├─ Add labels: opa-override, special-approval
      │     │     ├─ Build commit message with OVERRIDE warning
      │     │     ├─ Merge PR (squash)
      │     │     ├─ Set output: merged=true, override=true
      │     │     └─ Post override warning comment
   ↓
8. Trigger Terraform Apply (only if merged=true)
   - Sends apply dispatch to controller
   ↓
   
┌─────────────────────────────────────────────────────────────────────┐
│               DEV REPOSITORY - APPLY TRIGGER                         │
└─────────────────────────────────────────────────────────────────────┘

9. trigger-apply job (on PR merge)
   - Check if PR has "opa-passed" label
   ├─ No opa-passed label
   │  └─ BLOCK apply (security check)
   │
   └─ Has opa-passed label
      ├─ Get merged PR details
      ├─ Get changed files list
      └─ Send repository_dispatch event: "terraform_apply"
   ↓
   
┌─────────────────────────────────────────────────────────────────────┐
│            CONTROLLER REPOSITORY - APPLY WORKFLOW                    │
└─────────────────────────────────────────────────────────────────────┘

10. Execute Terraform Apply
    - Checkout main branch
    - Run terraform apply for changed accounts
    - Post results back to original PR
```

## 🔑 Key Security Gates

### Gate 1: OPA Validation
- **What**: Policy compliance check
- **When**: On PR creation/update
- **Result**: 
  - PASS → Proceed to approval check
  - FAIL → Block or require special approval

### Gate 2: PR Approval
- **What**: Human review required
- **When**: After OPA passes
- **Who**: Any authorized reviewer
- **Result**: 
  - Approved → Auto-merge with audit trail
  - Not approved → Wait

### Gate 3: Special Approver Override (OPA Failed)
- **What**: Override OPA failures with justification
- **When**: OPA fails
- **Who**: Only special approvers (pragadeeswarpa)
- **Requires**: Comment with "OVERRIDE" + justification
- **Result**: Merge with warning labels

### Gate 4: Apply Label Check
- **What**: Verify OPA passed before apply
- **When**: On PR merge
- **Check**: PR has "opa-passed" label
- **Result**: 
  - Label present → Trigger apply
  - No label → Block apply

## 📝 Commit Message Format

### OPA Passed - Regular Merge
```
[Terraform] Add new S3 bucket configuration

Merged after approval and OPA validation

PR #123: Add new S3 bucket configuration
Author: developer-user
Approved-by: pragadeeswarpa
Branch: feature/new-bucket to main

Files changed (5):
  - Accounts/test-poc-3/test-poc-3.tfvars
  - Accounts/test-poc-3/test-poc-3.json
  - terraform/s3.tf
  - terraform/variables.tf
  - terraform/outputs.tf

OPA: PASSED
Workflow: https://github.com/Terraform-centilazed-pipline/centerlized-pipline-/actions/runs/12345
PR Link: https://github.com/org/dev-deployment/pull/123
Merged at: 2025-11-29 14:30:00 UTC
```

### OPA Failed - Special Override
```
[Terraform][OVERRIDE] Emergency production fix

Merged after approval and OPA validation

PR #124: Emergency production fix
Author: developer-user
Approved-by: pragadeeswarpa
Branch: hotfix/prod-issue to main

Files changed (2):
  - Accounts/prod-account/prod.tfvars
  - terraform/main.tf

OPA: PASSED
Workflow: https://github.com/Terraform-centilazed-pipline/centerlized-pipline-/actions/runs/12346
PR Link: https://github.com/org/dev-deployment/pull/124
Merged at: 2025-11-29 15:45:00 UTC

⚠️ OPA OVERRIDE by @pragadeeswarpa
```

## 🏷️ PR Labels Used

| Label | When Applied | Meaning |
|-------|-------------|---------|
| `opa-passed` | OPA validation succeeds | Security policies passed |
| `ready-to-merge` | After approval with OPA passed | Ready for auto-merge |
| `opa-failed` | OPA validation fails | Security policy violations |
| `blocked` | OPA failed, no special approver | Cannot merge at all |
| `requires-special-approval` | OPA failed, regular user | Needs special approver override |
| `opa-override` | Special approver overrides | OPA failure was overridden |
| `special-approval` | Override was justified | Special approval granted |

## 🔄 State Transitions

```
PR Created
    ↓
OPA Running
    ↓
    ├─→ OPA Passed
    │      ↓
    │   Waiting for Approval
    │      ↓
    │   Approved
    │      ↓
    │   Merged ✅
    │      ↓
    │   Apply Triggered
    │
    └─→ OPA Failed
           ↓
           ├─→ Regular User
           │      ↓
           │   Blocked 🚫
           │
           └─→ Special Approver
                  ↓
                  ├─→ No Justification
                  │      ↓
                  │   Waiting for OVERRIDE Comment
                  │
                  └─→ Justified
                         ↓
                      Merged ⚠️
                         ↓
                      Apply Triggered
```

## 🎯 Requirements Met

✅ **Dynamic Commit Messages**: Includes author, approver, files, timestamps  
✅ **Approval Required**: No auto-merge without human review  
✅ **OPA Blocking**: Failed OPA prevents merge (auto or manual)  
✅ **Special Override**: Designated users can override with justification  
✅ **Apply Gate**: Only opa-passed PRs trigger terraform apply  
✅ **Full Audit Trail**: Every commit shows complete history  
✅ **Clean Code**: Python script instead of complex YAML JavaScript  

## 🧪 Testing Scenarios

### Scenario 1: Happy Path
1. Push changes → PR auto-created ✅
2. OPA validates → PASSED ✅
3. Reviewer approves PR ✅
4. Auto-merge with audit trail ✅
5. Apply triggers automatically ✅

### Scenario 2: Needs Approval
1. Push changes → PR auto-created ✅
2. OPA validates → PASSED ✅
3. No approval yet → Comment posted, waits ⏳
4. Reviewer approves → Auto-merge ✅
5. Apply triggers ✅

### Scenario 3: OPA Fails - Regular User
1. Push changes → PR auto-created ✅
2. OPA validates → FAILED ❌
3. Labels added: opa-failed, blocked 🚫
4. Cannot merge (blocked) ❌
5. No apply trigger ❌

### Scenario 4: OPA Fails - Special Override
1. Push changes → PR auto-created ✅
2. OPA validates → FAILED ❌
3. Special approver approves ✅
4. Posts OVERRIDE comment with justification ✅
5. Auto-merge with warning ⚠️
6. Apply triggers ✅

### Scenario 5: Merge without OPA Pass
1. Someone manually merges PR ❌
2. Apply trigger checks for opa-passed label ✅
3. No label found → Apply BLOCKED 🚫
4. Security maintained ✅
```
