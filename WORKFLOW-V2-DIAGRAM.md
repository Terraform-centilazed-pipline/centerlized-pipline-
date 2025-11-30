# 🚀 Centralized Terraform Pipeline V2 - Visual Diagram

## 📊 Workflow Architecture

```mermaid
flowchart LR
    subgraph DEV[" 🏢 DEV-DEPLOYMENT REPOSITORY "]
        direction TB
        A[👨‍💻 Developer Push] --> B[🤖 Auto-PR]
        B --> C[📝 PR Created]
        
        C --> D1[🔍 PR Open/Update]
        C --> D2[✅ PR Approved]
        C --> D3[🔀 PR Merged]
        
        D1 --> E1[📤 Dispatch: VALIDATE]
        D2 --> E2[📤 Dispatch: MERGE]
        D3 --> E3[📤 Dispatch: APPLY]
    end
    
    subgraph CTRL[" 🎯 CENTRALIZED CONTROLLER "]
        direction TB
        
        subgraph VAL[" 🔍 VALIDATE PHASE "]
            V1[📦 Checkout Code] --> V2[⚙️ Terraform Init]
            V2 --> V3[📊 Terraform Plan]
            V3 --> V4[🔍 OPA Validation]
            V4 -->|Pass| V5[✅ Add opa-passed label]
            V4 -->|Fail| V6[❌ Add opa-failed label]
        end
        
        subgraph MRG[" ✅ MERGE PHASE "]
            M1{🏷️ Check OPA Labels} -->|opa-passed| M2[🐍 Python Script]
            M1 -->|opa-failed| M3{Special Approver?}
            M2 -->|Has Approval| M4[🔀 Merge with Audit Trail]
            M3 -->|Yes + OVERRIDE| M5[⚠️ Merge with Override]
            M3 -->|No| M6[🚫 Block Merge]
        end
        
        subgraph APP[" 🚀 APPLY PHASE "]
            A1{🔒 Security Gate} -->|opa-passed exists| A2[📦 Checkout]
            A1 -->|No label| A3[🚫 Block Apply]
            A2 --> A4[⚙️ Terraform Init]
            A4 --> A5[🚀 Terraform Apply]
            A5 --> A6[✅ Infrastructure Updated]
        end
    end
    
    E1 -.->|Event| VAL
    E2 -.->|Event| MRG
    E3 -.->|Event| APP
    
    V5 -.->|Labels| C
    V6 -.->|Labels| C
    M4 -.->|Commit| DEV
    A6 -.->|Comment| C
    
    style DEV fill:#e3f2fd,stroke:#1976d2,stroke-width:3px
    style CTRL fill:#fff3e0,stroke:#f57c00,stroke-width:3px
    style VAL fill:#e8f5e9,stroke:#388e3c,stroke-width:2px
    style MRG fill:#fff9c4,stroke:#f9a825,stroke-width:2px
    style APP fill:#fce4ec,stroke:#c2185b,stroke-width:2px
    
    style V5 fill:#c8e6c9,stroke:#2e7d32
    style V6 fill:#ffcdd2,stroke:#c62828
    style M4 fill:#c8e6c9,stroke:#2e7d32
    style M6 fill:#ffcdd2,stroke:#c62828
    style A3 fill:#ffcdd2,stroke:#c62828
    style A6 fill:#c8e6c9,stroke:#2e7d32
```

---

## 🔄 Data Flow Details

```mermaid
sequenceDiagram
    participant Dev as 👨‍💻 Developer
    participant DevRepo as 📦 dev-deployment
    participant GHA as 🔔 GitHub Actions
    participant Ctrl as 🎯 Controller
    participant OPA as 🔍 OPA Engine
    participant Python as 🐍 Merge Script
    
    Note over Dev,Python: PHASE 1: VALIDATE
    Dev->>DevRepo: git push feature-branch
    DevRepo->>GHA: Auto-create PR
    GHA->>Ctrl: Dispatch validate event
    Note right of Ctrl: repo: dev-deployment<br/>PR: 73<br/>action: validate
    Ctrl->>Ctrl: terraform init + plan
    Ctrl->>OPA: Validate plan
    OPA-->>Ctrl: Pass/Fail result
    Ctrl->>DevRepo: Add labels (opa-passed/failed)
    Ctrl->>DevRepo: Comment with results
    
    Note over Dev,Python: PHASE 2: MERGE
    Dev->>DevRepo: Approve PR
    GHA->>Ctrl: Dispatch merge event
    Note right of Ctrl: PR: 73<br/>action: merge<br/>approver: username
    Ctrl->>DevRepo: Read OPA labels
    Ctrl->>Python: handle_pr_merge.py
    Python->>Python: Check approvals
    Python->>DevRepo: Merge with audit trail
    Note right of DevRepo: Commit includes:<br/>- PR details<br/>- Approver<br/>- Files changed<br/>- OPA status
    
    Note over Dev,Python: PHASE 3: APPLY
    DevRepo->>GHA: PR merged to main
    GHA->>Ctrl: Dispatch apply event
    Note right of Ctrl: PR: 73<br/>action: apply<br/>merge_sha: abc123
    Ctrl->>DevRepo: Check opa-passed label
    Ctrl->>Ctrl: terraform apply
    Ctrl->>DevRepo: Comment: Applied successfully
```

---

## 🏷️ Label-Based Flow

```mermaid
stateDiagram-v2
    [*] --> PR_Created: Push to feature branch
    
    PR_Created --> OPA_Running: Dispatch validate
    
    OPA_Running --> OPA_Passed: ✅ Validation successful
    OPA_Running --> OPA_Failed: ❌ Validation failed
    
    OPA_Passed --> Waiting_Approval: Add opa-passed label
    OPA_Failed --> Blocked: Add opa-failed label
    
    Waiting_Approval --> Ready_Merge: PR approved
    Blocked --> Special_Review: Special approver needed
    
    Ready_Merge --> Merged: Python merges PR
    Special_Review --> Override_Merge: Override approved
    Special_Review --> Permanently_Blocked: No override
    
    Merged --> Security_Gate: Dispatch apply
    Override_Merge --> Security_Gate: Dispatch apply
    
    Security_Gate --> Applying: opa-passed label found
    Security_Gate --> Apply_Blocked: No opa-passed label
    
    Applying --> [*]: Infrastructure updated
    Apply_Blocked --> [*]: Apply failed
    Permanently_Blocked --> [*]: Merge blocked
```

---

## 📋 Enhanced Logging Output

```mermaid
graph TD
    A[🎯 Workflow Run] --> B[Run Name Display]
    B --> C["[dev-deployment] validate → PR#73: Config updates"]
    
    A --> D[Job Name Display]
    D --> E["🚀 dev-deployment → validate (PR#73)"]
    
    A --> F[Event Details Log]
    F --> G["📦 Source: dev-deployment<br/>🔍 PR #73: Config updates<br/>🎯 Action: validate<br/>🌿 Branch: feature<br/>📝 Commit: abc123<br/>📄 Files: 3"]
    
    A --> H[Commit Message]
    H --> I["Merge PR #73: Config updates<br/>Author: @dev<br/>Approved by: @reviewer<br/>Files: config.tfvars<br/>OPA: ✅ PASSED<br/>Workflow: URL<br/>Merged at: 2025-11-30"]
    
    style A fill:#e1f5ff
    style C fill:#c8e6c9
    style E fill:#fff9c4
    style G fill:#e8f5e9
    style I fill:#f3e5f5
```

---

## ⚙️ Component Architecture

```mermaid
graph TB
    subgraph FILES[" 📁 Configuration Files "]
        F1[special-approvers.yaml]
        F2[requirements.txt]
        F3[handle_pr_merge.py]
        F4[dry-run-validation.sh]
    end
    
    subgraph WORKFLOWS[" 🔄 GitHub Workflows "]
        W1[dispatch-to-controller.yml]
        W2[centralized-controller.yml]
    end
    
    subgraph LABELS[" 🏷️ PR Labels "]
        L1[opa-passed]
        L2[opa-failed]
        L3[ready-for-review]
        L4[needs-fixes]
        L5[blocked]
        L6[requires-special-approval]
        L7[opa-override]
        L8[special-approval]
    end
    
    W1 --> |Triggers| W2
    W2 --> |Applies| LABELS
    W2 --> |Executes| F3
    F3 --> |Reads| F1
    F3 --> |Uses| F2
    F4 --> |Validates| W1
    F4 --> |Validates| W2
    
    style FILES fill:#e8f5e9
    style WORKFLOWS fill:#e3f2fd
    style LABELS fill:#fff3e0
```

---

## 🎯 Key Features Summary

| Feature | Description | Benefit |
|---------|-------------|---------|
| 🔍 **OPA Labels** | Cached validation results | No re-runs, faster merges |
| 🐍 **Python Handler** | Smart merge logic | Custom approval rules |
| 📝 **Dynamic Commits** | Full audit trail in git | Complete traceability |
| 🔒 **Security Gates** | Label-based checks | Prevent unauthorized changes |
| 📊 **Enhanced Logging** | Detailed context display | Easy debugging |
| ⚠️ **Special Override** | Senior approver bypass | Emergency flexibility |
| 📋 **10 Properties** | Optimized payload | GitHub API compliant |
| ✅ **Dry-Run Validation** | Pre-deployment checks | Catch errors early |

---

## 📈 Audit Trail Example

**GitHub Actions View:**
```
🎯 Centralized Terraform Controller
  ├─ 🚀 dev-deployment → validate (PR#73)   ✅ 2m 34s
  ├─ 🚀 dev-deployment → merge (PR#73)      ✅ 45s  
  └─ 🚀 dev-deployment → apply (PR#73)      ✅ 3m 12s
```

**Git Commit History:**
```
456abc Merge PR #73: Update S3 bucket configuration
       Author: @developer
       Approved by: @senior-engineer
       Files changed (2):
         - Accounts/prod/s3.tfvars
         - Accounts/prod/policy.json
       OPA Validation: ✅ PASSED
       Workflow: https://github.com/.../actions/runs/123
       Merged at: 2025-11-30T10:45:23Z
```

---

**Version**: 2.0  
**Status**: ✅ Production Ready  
**Last Updated**: November 30, 2025
