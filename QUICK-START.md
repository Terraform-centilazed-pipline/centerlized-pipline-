# Quick Start - 5 Minute Setup

## TL;DR

```bash
# 1. Create GitHub App
Go to: Org Settings → GitHub Apps → New
Permissions: Actions, Contents, Issues, PRs, Workflows (Read & Write)
Webhook: DISABLED ❌
Generate private key → Save .pem file

# 2. Install app on repos
centerlized-pipline-, dev-deployment, OPA-Poclies, tf-module

# 3. Add secrets to repos
GITHUB_APP_ID=123456
GITHUB_APP_PRIVATE_KEY=<paste .pem>
AWS_TERRAFORM_ROLE_ARN=arn:aws:iam::xxx:role/TerraformExecutionRole

# 4. Done! Create a PR and watch it work
```

## Full Setup Guide

See [GITHUB-APP-SETUP.md](./GITHUB-APP-SETUP.md) for detailed instructions.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Developer Experience                     │
└─────────────────────────────────────────────────────────────┘
                              │
                    1. Edit terraform file
                    2. Create PR
                              ↓
┌─────────────────────────────────────────────────────────────┐
│              Dev Repo: trigger-controller.yml                │
│                        (20 lines)                            │
└─────────────────────────────────────────────────────────────┘
                              │
                   Uses: workflow_call
                              ↓
┌─────────────────────────────────────────────────────────────┐
│         Controller Repo: controller-simple.yml               │
│                                                              │
│  Step 1: 🔍 Discover    (s3-deployment-manager.py discover) │
│  Step 2: 📋 Plan        (s3-deployment-manager.py plan)     │
│  Step 3: 🛡️  OPA        (opa eval on plan JSON)            │
│  Step 4: 💬 Comment     (Post results to PR)                │
│  Step 5: 🔀 Merge/Close (Auto-merge ✅ or close ❌)         │
│  Step 6: 🚀 Apply       (s3-deployment-manager.py apply)    │
└─────────────────────────────────────────────────────────────┘
                              │
                    Result posted to PR
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                    Auto-Merge or Close                       │
│  ✅ OPA Pass → Merge → Deploy                               │
│  ❌ OPA Fail → Close → Create Issue                         │
└─────────────────────────────────────────────────────────────┘
```

## Files Needed

### Controller Repo (centerlized-pipline-)

```
.github/workflows/
  └── controller-simple.yml          ← Main controller (already created)

scripts/
  └── s3-deployment-manager.py       ← Your existing script

GITHUB-APP-SETUP.md                  ← Setup instructions
README-SIMPLE.md                     ← Documentation
```

### Dev Repo (dev-deployment)

```
.github/workflows/
  └── trigger-controller.yml         ← Simple 20-line trigger

Accounts/
  └── ...terraform configs...        ← Your existing structure

scripts/
  └── s3-deployment-manager.py       ← Copy from controller repo
```

## Secrets Setup Visual

```
┌──────────────────────────────────────────────────────────────┐
│              GitHub App (created once)                        │
│  App ID: 123456                                              │
│  Private Key: terraform-controller.pem                       │
└──────────────────────────────────────────────────────────────┘
                      │
        ┌─────────────┴─────────────┬──────────────┐
        ↓                           ↓              ↓
┌──────────────────┐    ┌──────────────────┐   ┌──────────────┐
│ Controller Repo  │    │   Dev Repo 1     │   │  Dev Repo 2  │
│                  │    │                  │   │              │
│ Secrets:         │    │ Secrets:         │   │ Secrets:     │
│ • APP_ID         │    │ • APP_PRIVATE_KEY│   │ • APP_...    │
│ • APP_PRIVATE_KEY│    │ • AWS_ROLE_ARN   │   │ • AWS_...    │
│ • AWS_ROLE_ARN   │    │                  │   │              │
└──────────────────┘    └──────────────────┘   └──────────────┘
```

## Permission Matrix

| Permission | Level | Controller Needs | Dev Repo Needs |
|------------|-------|------------------|----------------|
| Actions | Read & Write | ✅ Trigger workflows | ✅ Call controller |
| Contents | Read & Write | ✅ Clone all repos | ✅ Read configs |
| Issues | Read & Write | ✅ Create violations | ❌ No |
| Pull Requests | Read & Write | ✅ Comment, merge, close | ❌ No |
| Workflows | Read & Write | ✅ Trigger workflows | ✅ Call controller |

## Test Checklist

```bash
# 1. Check GitHub App
□ App created
□ Private key downloaded
□ App installed on all 4 repos
□ Permissions correct (see GITHUB-APP-SETUP.md)

# 2. Check Secrets
□ Controller repo has 3 secrets
□ Dev repo has 2 secrets
□ Values are correct (no extra spaces)

# 3. Check Workflows
□ controller-simple.yml in controller repo main branch
□ trigger-controller.yml in dev repo

# 4. Test
□ Create PR with terraform change
□ Workflow runs automatically
□ Comment posted to PR
□ PR auto-merged or closed
```

## Expected PR Comment

When you create a PR, you'll see:

```markdown
## 🚀 Terraform Controller Results

**Branch**: `my-feature-branch`

### 📊 Plan Summary
- **Successful**: ✅ 2
- **Failed**: ❌ 0
- **Has Changes**: true

### 🛡️ OPA Validation
✅ **Status**: PASSED - No policy violations

### 📋 arj-wkld-a-nonprd-us-east-1-my-bucket

**Status**: 🔄 Changes Detected

<details><summary><strong>🔍 Click to view terraform plan</strong></summary>

```terraform
Terraform will perform the following actions:

  # aws_s3_bucket.this will be created
  + resource "aws_s3_bucket" "this" {
      + bucket = "my-new-bucket"
      ...
    }

Plan: 1 to add, 0 to change, 0 to destroy.
```

</details>

---

*Terraform Controller • [View Run](https://github.com/...)*
```

Then **automatically**:
- ✅ PR merged if OPA passes
- ❌ PR closed if OPA fails

## Comparison

### Before (your current workflow)
```
Dev Repo
├── .github/workflows/
│   └── s3-infrastructure-deployment.yml    ← 400+ lines
│   └── Multiple jobs, complex logic
│   └── Duplicated in every dev repo
└── Manual merge required
```

### After (this approach)
```
Dev Repo
├── .github/workflows/
│   └── trigger-controller.yml              ← 20 lines!
└── Auto-merge/close

Controller Repo
└── .github/workflows/
    └── controller-simple.yml               ← All logic here
```

## Benefits

| Benefit | Before | After |
|---------|--------|-------|
| **Dev workflow size** | 400+ lines | 20 lines |
| **Logic location** | Duplicated | Centralized |
| **Update effort** | Update each repo | Update once |
| **Merge process** | Manual | Automatic |
| **External services** | None | None |
| **Cost** | $0 | $0 |
| **Setup time** | Complex | 5 minutes |

## Troubleshooting

### "Unable to find reusable workflow"
```bash
# Make sure controller-simple.yml is in main branch
git checkout main
git pull
ls .github/workflows/controller-simple.yml  # Should exist
```

### "Bad credentials"
```bash
# Check secrets are set correctly
# Go to repo Settings → Secrets → Actions
# Verify GITHUB_APP_PRIVATE_KEY has full .pem content
```

### Workflow doesn't trigger
```bash
# Check paths in trigger-controller.yml match your files
# Example: if files are in configs/, update paths:
paths:
  - 'configs/**/*.tfvars'
```

### Can't merge PR
```bash
# Check GitHub App has "Pull requests: Read & Write"
# Check branch protection rules allow app to merge
```

## Support

- 📖 Detailed setup: [GITHUB-APP-SETUP.md](./GITHUB-APP-SETUP.md)
- 📝 Full docs: [README-SIMPLE.md](./README-SIMPLE.md)
- 🔍 Existing workflow: Check `S3_Mgmt/` for working example

## Next Steps

1. ✅ Follow [GITHUB-APP-SETUP.md](./GITHUB-APP-SETUP.md) to create GitHub App
2. ✅ Add secrets to repos
3. ✅ Commit workflows
4. ✅ Create test PR
5. ✅ Watch automation work! 🎉
