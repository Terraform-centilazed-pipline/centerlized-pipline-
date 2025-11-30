# 🚀 Centralized Terraform Pipeline - Version 2 Architecture

## 📊 Complete Workflow Flow with Enhancements

```mermaid
graph TB
    subgraph DEV["🏢 dev-deployment Repository"]
        A[👨‍💻 Developer pushes to feature branch] --> B[🤖 Auto-PR Job]
        B --> C[📝 PR Created automatically]
        C --> D[🔍 dispatch-validate triggered]
        
        D --> |"📤 Dispatch Event<br/>repo: dev-deployment<br/>PR#: 73<br/>action: validate<br/>files: [tfvars]"| E
        
        C --> F[👀 Reviewer approves PR]
        F --> G[✅ dispatch-merge triggered]
        
        G --> |"📤 Dispatch Event<br/>repo: dev-deployment<br/>PR#: 73<br/>action: merge<br/>approver: username"| H
        
        I[🔀 PR Merged to main] --> J[🚀 dispatch-apply triggered]
        J --> |"📤 Dispatch Event<br/>repo: dev-deployment<br/>PR#: 73<br/>action: apply<br/>merge_sha: abc123"| K
    end
    
    subgraph CONTROLLER["🎯 centerlized-pipline- Repository"]
        E[🔔 Controller receives validate] --> L{📋 Event Details<br/>Logged}
        L --> M[📦 Checkout dev repo]
        M --> N[📥 Download tfvars]
        N --> O[⚙️ Terraform Init]
        O --> P[📊 Terraform Plan]
        P --> Q[🔍 OPA Validation]
        
        Q --> |Pass| R[✅ Add Labels<br/>opa-passed<br/>ready-for-review]
        Q --> |Fail| S[❌ Add Labels<br/>opa-failed<br/>needs-fixes<br/>blocked]
        
        R --> T[💬 Comment on PR<br/>✅ Validation passed]
        S --> U[💬 Comment on PR<br/>❌ Validation failed<br/>+ violation details]
        
        H[🔔 Controller receives merge] --> V{📋 Check OPA Status}
        V --> |"Read labels from PR"| W{OPA Status?}
        
        W --> |opa-passed| X[🐍 Python: handle_pr_merge.py]
        W --> |opa-failed| Y{Special Approver?}
        
        X --> Z{Has Approval?}
        Z --> |Yes| AA[🔀 Merge PR with<br/>📝 Dynamic Commit Message]
        Z --> |No| AB[⏸️ Wait for approval]
        
        Y --> |Yes + OVERRIDE comment| AC[⚠️ Merge with Override<br/>Add opa-override label]
        Y --> |No| AD[🚫 Block merge<br/>Add requires-special-approval]
        
        AA --> AE[✨ Commit Message:<br/>PR#73 by @user<br/>Approved by @reviewer<br/>Files: [list]<br/>OPA: passed<br/>Workflow: URL<br/>Timestamp: UTC]
        
        K[🔔 Controller receives apply] --> AF{🔒 Security Gate}
        AF --> |Check labels| AG{Has opa-passed?}
        AG --> |Yes| AH[📦 Checkout at merge SHA]
        AG --> |No| AI[🚫 Block Apply<br/>Missing opa-passed label]
        
        AH --> AJ[⚙️ Terraform Init]
        AJ --> AK[🚀 Terraform Apply]
        AK --> AL[✅ Infrastructure Updated]
        AL --> AM[💬 Comment on PR<br/>✅ Applied successfully]
    end
    
    subgraph LOGGING["📊 Enhanced Logging"]
        AN[🎯 Workflow Run Names]
        AO[📦 Source Repo: dev-deployment]
        AP[🔍 PR Number: #73]
        AQ[📝 PR Title: Config updates]
        AR[🎯 Action: validate/merge/apply]
        AS[👤 Actor: @username]
        AT[🌿 Branch: feature-branch]
        AU[📝 Commit SHA: abc123]
        
        AN --> AO
        AN --> AP
        AN --> AQ
        AN --> AR
        AN --> AS
        AN --> AT
        AN --> AU
    end
    
    subgraph CONFIG["⚙️ Configuration Files"]
        AV[special-approvers.yaml]
        AW[requirements.txt]
        AX[handle_pr_merge.py]
        
        AV --> |Used by| AX
        AW --> |Dependencies| AX
    end
    
    style DEV fill:#e1f5ff
    style CONTROLLER fill:#fff3e0
    style LOGGING fill:#f3e5f5
    style CONFIG fill:#e8f5e9
    
    style Q fill:#fff59d
    style W fill:#fff59d
    style AG fill:#fff59d
    style AA fill:#c8e6c9
    style AL fill:#c8e6c9
    style S fill:#ffcdd2
    style AI fill:#ffcdd2
    style AD fill:#ffcdd2
```

## 🎯 Key Enhancements in V2

### 1. **Enhanced Dispatch Logging** 📊
- **Dev Repository**: Shows detailed context when dispatching
  ```
  🚀 DISPATCHING VALIDATION TO CONTROLLER
  ════════════════════════════════════════
  📦 Source Repo: Terraform-centilazed-pipline/dev-deployment
  🔍 PR #73: 🔧 Terraform configuration updates
  👤 Author: @user
  🌿 Branch: feature → main
  📝 Commit: abc123
  📄 Files Changed: 3
  🎯 Action: VALIDATE
  🎪 Controller: centerlized-pipline-
  ════════════════════════════════════════
  ```

### 2. **Controller Event Details** 🎯
- **Run Name**: `[dev-deployment] validate → PR#73: Config updates`
- **Job Name**: `🚀 dev-deployment → validate (PR#73)`
- **First Step Logs**:
  ```
  ════════════════════════════════════════
  🎯 CENTRALIZED CONTROLLER RECEIVED EVENT
  ════════════════════════════════════════
  📦 Source Repo: dev-deployment
  🔍 PR #73: Config updates
  🎯 Action: validate
  🔔 Trigger: pr_opened_or_updated
  🌿 Branch: feature-branch
  📝 Commit: abc123...
  
  📄 Changed Files:
  Accounts/test/test.tfvars
  ════════════════════════════════════════
  ```

### 3. **Dynamic Commit Messages** 📝
When PR merges, includes full audit trail:
```
Merge PR #73: Terraform configuration updates

Author: @developer
Approved by: @reviewer
Workflow: https://github.com/.../actions/runs/123

Changed files (3):
  - Accounts/test/config.tfvars
  - Accounts/prod/prod.tfvars
  - policies/bucket-policy.json

OPA Validation: ✅ PASSED
Merged at: 2025-11-30T10:30:45Z
Workflow Run: https://github.com/.../actions/runs/123
```

### 4. **Reduced Payload Properties** 🔧
**Before** (12 properties - FAILED):
- source_repo, source_owner, pr_number, pr_title, pr_head_ref, pr_head_sha, pr_author, pr_url, changed_files, action, trigger, timestamp

**After** (10 properties - WORKS):
- **Validate**: source_repo, source_owner, pr_number, pr_title, pr_head_ref, pr_head_sha, pr_author, changed_files, action, trigger
- **Merge**: source_repo, source_owner, pr_number, pr_title, pr_head_ref, pr_head_sha, changed_files, action, approver, trigger
- **Apply**: source_repo, source_owner, pr_number, pr_title, base_ref, merge_sha, merged_by, changed_files, action, trigger

### 5. **OPA Label System** 🏷️
**Labels Applied**:
- ✅ `opa-passed` + `ready-for-review` (validation passed)
- ❌ `opa-failed` + `needs-fixes` + `blocked` (validation failed)
- ⚠️ `requires-special-approval` (OPA failed, needs override)
- 🔓 `opa-override` + `special-approval` (override approved)

**Label-Based Flow**:
1. OPA runs ONCE during validation → adds labels
2. Merge step reads labels (doesn't re-run OPA)
3. Apply step checks for `opa-passed` label (security gate)

### 6. **Python Merge Handler** 🐍
**Script**: `scripts/handle_pr_merge.py`
- Reads OPA status from PR labels
- Checks for approvals
- Handles special approver override with OVERRIDE comments
- Builds dynamic commit message with full audit trail
- Merges via GitHub API

**Special Approver Override**:
```yaml
# config/special-approvers.yaml
special_approvers:
  - pragadeeswarpa
  - senior-engineer
```

## 🔄 Complete Flow Summary

### Phase 1: Validate (PR Open/Update)
1. Developer pushes to feature branch
2. Auto-PR creates PR automatically
3. Dispatch sends validate event to controller
4. Controller runs: checkout → init → plan → OPA
5. OPA adds labels (opa-passed or opa-failed)
6. Comment added to PR with results

### Phase 2: Merge (PR Approval)
1. Reviewer approves PR
2. Dispatch sends merge event to controller
3. Controller reads OPA labels from PR
4. Python script checks:
   - Has opa-passed label? ✅
   - Has approvals? ✅
   - If opa-failed: Is special approver + OVERRIDE comment? ⚠️
5. If all checks pass: Merge with dynamic commit message
6. If blocked: Add blocking labels and comment

### Phase 3: Apply (PR Merged)
1. PR merged to main
2. Dispatch sends apply event to controller
3. Security gate checks for opa-passed label
4. If passed: checkout → init → apply
5. If blocked: Fail with security gate message
6. Comment added with apply results

## 📈 Audit Trail Visibility

**GitHub Actions List View**:
```
🎯 Centralized Terraform Controller
  └─ 🚀 dev-deployment → validate (PR#73)  ✅
  └─ 🚀 dev-deployment → merge (PR#73)     ✅
  └─ 🚀 dev-deployment → apply (PR#73)     ✅
```

**Complete Context Available**:
- Which repo triggered it
- What action was performed
- Which PR number
- Who was involved (author/approver/merger)
- What files changed
- When it happened
- Workflow URL for traceability

## 🚀 Benefits

1. **Full Audit Trail**: Every merge has complete context
2. **Clear Visibility**: Job names show repo, action, PR at a glance
3. **Security Gates**: OPA labels prevent unauthorized changes
4. **Human Oversight**: Approval required + special approver override
5. **Production Grade**: Fail-fast, error handling, defensive programming
6. **10 Property Limit**: Complies with GitHub API constraints
7. **No OPA Re-runs**: Labels cached, read on demand
8. **Dynamic Commit Messages**: Full context in git history

## 📝 Configuration Files

### 1. `dry-run-validation.sh`
Validates all workflows before deployment (34 checks):
- File existence
- YAML syntax
- Required secrets
- Workflow structure
- Python script validation
- Dependencies
- Configuration
- Triggers
- Security gates
- Action routing

### 2. `config/special-approvers.yaml`
```yaml
special_approvers:
  - pragadeeswarpa
  - senior-engineer
```

### 3. `scripts/requirements.txt`
```
PyGithub==2.1.1
PyYAML==6.0.1
```

### 4. `scripts/handle_pr_merge.py`
Main functions:
- `load_special_approvers()`
- `get_pr_approvals()`
- `get_opa_status_from_pr()`
- `build_commit_message()`
- `handle_opa_passed()`
- `handle_opa_failed()`

## 🎓 Next Steps

1. ✅ All workflows validated (34/34 checks passed)
2. ✅ Enhanced logging deployed
3. ✅ Python merge handler configured
4. ✅ Payload properties optimized (10 max)
5. ✅ Dynamic commit messages implemented
6. 🎯 Ready for production use!

---

**Version**: 2.0  
**Last Updated**: November 30, 2025  
**Status**: ✅ Production Ready
