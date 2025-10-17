# Pure GitHub Actions Controller (NO External Services!)

## Overview

**Pure GitHub-native solution** - NO Lambda, NO webhooks, NO external infrastructure!

- ✅ Dev repos have **1 tiny workflow** (10 lines) - just calls controller
- ✅ Controller repo does everything - plan, OPA, apply
- ✅ All runs in GitHub Actions - nothing external needed
- ✅ Auto-merge or auto-close based on OPA validation

## Architecture

```
Developer Repo
    ↓
    1 simple workflow (trigger-controller.yml)
    ↓
    Uses: workflow_call
    ↓
Controller Repo (centerlized-pipline-)
    └─ controller-simple.yml
        ├─ Step 1: Discover deployments
        ├─ Step 2: Terraform Plan
        ├─ Step 3: OPA Validation
        ├─ Step 4: Post PR Comment
        ├─ Step 5: Auto-Merge/Close PR
        └─ Step 6: Terraform Apply
```

## Setup (5 Minutes!)

### 1. Create GitHub App (for cross-repo access)

1. Go to **Organization Settings** → **Developer Settings** → **GitHub Apps**
2. Click **New GitHub App**
3. Configure:
   ```
   Name: Terraform Controller
   Homepage URL: https://github.com/Terraform-centilazed-pipline/centerlized-pipline-
   Webhook: ❌ DISABLED (we don't need it!)
   
   Permissions:
   - Contents: Read & Write
   - Pull Requests: Read & Write
   - Actions: Read & Write
   ```

4. **Generate private key** (.pem file)
5. **Note the App ID**
6. **Install app** on all repos (controller, dev, OPA, modules)

### 2. Configure Secrets

#### In Controller Repo (`centerlized-pipline-`)

```bash
GITHUB_APP_ID=123456
GITHUB_APP_PRIVATE_KEY=<paste .pem contents>
AWS_TERRAFORM_ROLE_ARN=arn:aws:iam::ACCOUNT:role/TerraformExecutionRole
```

#### In Each Dev Repo (`dev-deployment`, etc.)

```bash
GITHUB_APP_PRIVATE_KEY=<paste .pem contents>
AWS_TERRAFORM_ROLE_ARN=arn:aws:iam::ACCOUNT:role/TerraformExecutionRole
```

### 3. Add Trigger Workflow to Dev Repos

Create `.github/workflows/trigger-controller.yml` in dev repo:

```yaml
name: Trigger Controller

on:
  pull_request:
    paths:
      - 'Accounts/**/*.tfvars'
      - 'Accounts/**/*.yaml'
  push:
    branches: [main]
    paths:
      - 'Accounts/**/*.tfvars'

jobs:
  call-controller:
    uses: Terraform-centilazed-pipline/centerlized-pipline-/.github/workflows/controller-simple.yml@main
    with:
      changed_files: ${{ github.event_name == 'pull_request' && github.event.pull_request.changed_files || 'all' }}
      pr_number: ${{ github.event.pull_request.number || '' }}
      event_type: ${{ github.event_name }}
    secrets:
      APP_PRIVATE_KEY: ${{ secrets.GITHUB_APP_PRIVATE_KEY }}
      AWS_ROLE_ARN: ${{ secrets.AWS_TERRAFORM_ROLE_ARN }}
```

**That's it!** Only 20 lines in dev repo!

### 4. Test

```bash
# In dev repo
git checkout -b test-terraform
vim Accounts/test-account/us-east-1/my-project/terraform.tfvars
git add .
git commit -m "test: update config"
git push origin test-terraform

# Create PR on GitHub
# Watch controller run automatically!
```

## What Happens

1. **Dev creates PR** → trigger workflow runs
2. **Trigger calls controller** (workflow_call)
3. **Controller runs in 1 job**:
   - Discovers deployments (your s3-deployment-manager.py)
   - Runs terraform plan
   - Converts to JSON
   - Runs OPA validation
   - Posts detailed comment to PR
   - **Auto-merges** if OPA passes ✅
   - **Auto-closes** if OPA fails ❌
4. **On merge** → controller runs apply automatically

## File Structure

```
centerlized-pipline-/
├── .github/workflows/
│   └── controller-simple.yml        # Main controller (1 workflow, 6 steps)
├── scripts/
│   └── s3-deployment-manager.py     # Your existing script
└── README-SIMPLE.md                 # This file

dev-deployment/
├── .github/workflows/
│   └── trigger-controller.yml       # ONLY workflow (20 lines!)
├── Accounts/
│   └── ...terraform configs...
└── scripts/
    └── s3-deployment-manager.py     # Same script
```

## Benefits vs Original Approach

### Before (your working flow):
- ❌ Dev repo has complex 400-line workflow
- ❌ All logic duplicated in each dev repo
- ❌ Hard to update policies
- ❌ Manual merge/close

### Now (pure GitHub):
- ✅ Dev repo has 20-line trigger
- ✅ All logic centralized in controller
- ✅ Update once, affects all repos
- ✅ Auto-merge/close
- ✅ NO external services needed!

## Comparison with Terrateam

### Terrateam Approach:
- Uses external webhook server
- Requires Lambda/Cloud Run deployment
- Parses comments for commands
- Costs money for hosting

### This Approach:
- Pure GitHub Actions (FREE!)
- No external infrastructure
- Automatic detection (no commands)
- Just works™

## Troubleshooting

### "Unable to find reusable workflow"
- Make sure controller workflow is committed to `main` branch
- Verify repo path is correct: `Terraform-centilazed-pipline/centerlized-pipline-`

### "Secrets not found"
- Add secrets to BOTH controller and dev repos
- GitHub App must be installed on all repos

### Controller doesn't run
- Check if files changed match `paths:` in trigger
- Verify GitHub App has correct permissions
- Check Actions are enabled on repos

## Migration from Existing Workflow

If you have the existing complex workflow:

```bash
# 1. Backup existing workflow
mv .github/workflows/s3-infrastructure-deployment.yml .github/workflows/s3-infrastructure-deployment.yml.backup

# 2. Add new simple trigger
# (copy trigger-controller.yml from above)

# 3. Test with a PR

# 4. If works, delete backup
rm .github/workflows/s3-infrastructure-deployment.yml.backup
```

## Cost

**$0** - Everything runs in GitHub Actions free tier!
- No Lambda
- No Cloud Run  
- No external services
- Just GitHub Actions

## Summary

| Feature | External Webhook | This Approach |
|---------|-----------------|---------------|
| **Setup Time** | 1-2 hours | 5 minutes |
| **External Services** | Lambda/Cloud Run | None! |
| **Cost** | $5-20/month | $0 |
| **Maintenance** | High | Low |
| **Dev Workflow Size** | 0 lines | 20 lines |
| **Centralized Logic** | ✅ | ✅ |
| **Auto-merge/close** | ✅ | ✅ |

**Winner**: Pure GitHub approach! 🎉
