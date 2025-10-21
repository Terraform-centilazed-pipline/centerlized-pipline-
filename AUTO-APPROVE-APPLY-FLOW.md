# ✅ Auto-Approve & Apply Flow - Complete Implementation

## 🎯 Flow Summary

```
PR Created → Plan & OPA Validation
                    ↓
            ┌───────┴───────┐
            ↓               ↓
       OPA PASSED      OPA FAILED
            ↓               ↓
    ✅ AUTO-MERGE    ❌ CLOSE PR
            ↓          (with comment)
    🚀 AUTO-APPLY
```

## 📋 Detailed Workflow

### **Step 1: PR Created in Dev Repo**
```yaml
dev-deployment PR → dispatch-to-controller.yml
                 → Sends repository_dispatch event
                 → Event type: terraform_pr
```

### **Step 2: Centralized Controller - Plan & Validate**
```yaml
Job: terraform-controller
├─ Checkout repos (controller, source, opa-policies, tf-modules)
├─ Get changed files from PR
├─ Discover deployments (s3-deployment-manager.py discover)
├─ Terraform Plan (s3-deployment-manager.py plan)
│  └─ Creates: plan-results.json, terraform-json/, canonical-plan/
├─ OPA Validation (on canonical-plan/plan.json)
│  └─ validation_status: passed | failed
├─ Post PR Comment (with plan results)
└─ Handle PR based on OPA result
```

### **Step 3A: OPA PASSED → Auto-Approve & Merge**
```yaml
- name: 🔀 Handle PR - Auto-merge if OPA Passed
  if: steps.opa.outputs.validation_status == 'passed'
  
  Actions:
  ✅ Auto-merge PR with squash
  ✅ Commit message: "[Terraform] Auto-approved: OPA validation passed"
  ✅ Post success comment to PR
  ✅ Set output: merged=true, merge_sha=<sha>
  ✅ Trigger apply workflow
```

**PR Comment (Success)**:
```markdown
✅ **PR Auto-Approved & Merged!**

🛡️ OPA validation passed - all security policies compliant
🔀 Changes have been merged to `main`
🚀 Terraform apply will begin automatically...

**Merge SHA**: `abc123...`
```

### **Step 3B: OPA FAILED → Close PR**
```yaml
- name: 🔀 Handle PR - Close if OPA Failed
  if: steps.opa.outputs.validation_status == 'failed'
  
  Actions:
  ❌ Close PR
  ❌ Post violation details comment
  ❌ Set output: merged=false
```

**PR Comment (Failed)**:
```markdown
❌ **PR Closed: Policy Violations**

🛡️ OPA validation failed with **X violations**

This PR has been automatically closed due to security policy violations.

**Required Actions**:
1. Review the OPA validation results above
2. Fix all policy violations in your configuration
3. Create a new PR with corrected changes

---
*Security policies must pass before changes can be merged.*
```

### **Step 4: Trigger Terraform Apply**
```yaml
- name: 🚀 Trigger Terraform Apply
  if: steps.merge.outputs.merged == 'true'
  
  Action:
  - Dispatch repository_dispatch event
  - Event type: terraform_apply
  - Payload: source repo, PR number, merge SHA
```

### **Step 5: Terraform Apply Job**
```yaml
Job: terraform-apply
├─ Triggered by: repository_dispatch (terraform_apply)
├─ Checkout repos (from main/merged branch)
├─ Get merged PR files
├─ Discover deployments (s3-deployment-manager.py discover)
├─ Terraform Apply (s3-deployment-manager.py apply)
│  └─ Creates: apply-results.json
│  └─ Applies ALL deployments from merged PR
└─ Post apply results to original PR
```

**Apply Results Comment**:
```markdown
## 🚀 Terraform Apply Results

**Merged PR**: #123
**Applied to**: `main` branch

### 📊 Apply Summary
| Metric | Count |
|--------|-------|
| 📋 Total Deployments | 2 |
| ✅ Successful Applies | 2 |
| ❌ Failed Applies | 0 |

### 📋 Deployment Details
| Deployment | Status | Message |
|------------|--------|---------|
| test-4-poc-1 | ✅ | Applied successfully |
| arj-wkld-a-prd | ✅ | Applied successfully |

✅ **All deployments applied successfully!**
```

## 🔄 Complete Timeline Example

```
T+0s:  Developer creates PR in dev-deployment
       └─ Changes: Accounts/test-4-poc-1/test-4-poc-1.tfvars

T+10s: dispatch-to-controller.yml triggers
       └─ Sends repository_dispatch to centralized controller

T+15s: terraform-controller job starts
       ├─ Discovers 1 deployment
       ├─ Runs terraform plan
       └─ Creates plan artifacts

T+45s: OPA validation runs
       └─ Result: ✅ PASSED (0 violations)

T+50s: Auto-merge triggered
       ├─ PR merged to main with squash
       └─ PR comment posted: "Auto-Approved & Merged!"

T+55s: Apply dispatch triggered
       └─ repository_dispatch event: terraform_apply

T+60s: terraform-apply job starts
       ├─ Checks out main branch
       ├─ Discovers deployments from merged PR
       └─ Runs terraform apply

T+90s: Apply completes
       └─ PR comment posted: "Apply Results: 1/1 successful"

DONE ✅
```

## 🎛️ Configuration

### Required Secrets (Both Repos)
```yaml
# dev-deployment repo:
GT_APP_ID: <GitHub App ID>
GT_APP_PRIVATE_KEY: <GitHub App Private Key>

# centerlized-pipline- repo:
GT_APP_ID: <GitHub App ID>
GT_APP_PRIVATE_KEY: <GitHub App Private Key>
AWS_TERRAFORM_ROLE_ARN: <AWS IAM Role ARN>
```

### Workflow Triggers
```yaml
# centralized-controller.yml
on:
  repository_dispatch:
    types: 
      - terraform_pr      # Triggered on PR creation
      - terraform_apply   # Triggered after auto-merge
```

## ✅ Benefits of This Approach

1. **Fully Automated**: Zero manual intervention if OPA passes
2. **Security First**: No deploy without policy validation
3. **Clear Feedback**: Detailed comments at every stage
4. **Multi-Account**: Handles multiple deployments in one flow
5. **Audit Trail**: Complete workflow logs in GitHub Actions
6. **Fast Feedback**: Developers know immediately if policies fail
7. **Consistent**: Same flow every time, no human errors

## 🛡️ Safety Features

- ✅ OPA must pass before merge
- ✅ Failed policies = PR closed immediately
- ✅ Apply only runs on merged code (main branch)
- ✅ Each deployment tracked individually
- ✅ Failed applies don't block successful ones
- ✅ All results posted to PR for audit

## 📊 Key Outputs

### terraform-controller job creates:
- `deployments.json` - All discovered deployments
- `plan-results.json` - Plan summary with counts
- `terraform-json/*.json` - Plans for OPA validation
- `plan-markdown/*.md` - Human-readable plans
- `canonical-plan/plan.json` - Selected plan for OPA
- `opa-result.txt` - Validation results

### terraform-apply job creates:
- `apply-results.json` - Apply summary with counts
- `logs/*.log` - Detailed execution logs
- PR comments with complete results

## 🧪 Testing Checklist

- [ ] Create PR with valid config → Should auto-merge & apply
- [ ] Create PR with policy violations → Should close with comment
- [ ] Create PR with multiple accounts → Should apply all
- [ ] Verify apply runs on main branch (not PR branch)
- [ ] Verify PR comments show complete results
- [ ] Verify artifacts uploaded correctly
- [ ] Check workflow logs for any errors

