# 🎯 REAL Centralized Terraform Controller

## Architecture Overview

This is the **CORRECT** centralized model - like Terrateam!

```
┌────────────────────────────────────────────────────────────────────┐
│ Dev Repository (dev-deployment)                                    │
│ ├─ Developer commits tfvars                                        │
│ ├─ Creates Pull Request                                            │
│ └─ dispatch-to-controller.yml sends event →                        │
└────────────────────────────────────────────────────────────────────┘
                           │
                           │ repository_dispatch
                           │
┌────────────────────────────────────────────────────────────────────┐
│ Centralized Repository (centerlized-pipline-)                      │
│                                                                     │
│ centralized-controller.yml receives event                          │
│ ├─ Checkouts dev repo PR branch                                    │
│ ├─ Gets changed tfvars files                                       │
│ ├─ Uses CENTRALIZED main.tf                                        │
│ ├─ Uses CENTRALIZED scripts                                        │
│ ├─ Runs Terraform plan                                             │
│ ├─ Validates with OPA policies                                     │
│ ├─ Posts results to dev repo PR                                    │
│ └─ Auto-merges or closes PR                                        │
└────────────────────────────────────────────────────────────────────┘
```

## Key Differences from Previous Approach

### ❌ OLD (workflow_call - WRONG!)
- Workflow runs in **dev repo context**
- Uses dev repo's resources
- Needs secrets in every dev repo
- Can't use centralized main.tf properly

### ✅ NEW (repository_dispatch - CORRECT!)
- Workflow runs in **centralized repo context**
- Uses centralized main.tf, scripts, policies
- Secrets only in centralized repo
- Dev repo just triggers the event

## How It Works

### 1. Developer Workflow

```bash
# Developer makes changes
cd dev-deployment
vim Accounts/test/bucket.tfvars

# Create PR
git checkout -b feature/new-bucket
git add Accounts/test/bucket.tfvars
git commit -m "Add new S3 bucket"
git push origin feature/new-bucket

# Create PR on GitHub
# → dispatch-to-controller.yml automatically triggers
```

### 2. Dispatch Event (runs in dev repo)

File: `dev-deployment/.github/workflows/dispatch-to-controller.yml`

**What it does:**
- ✅ Detects PR with tfvars changes
- ✅ Sends `repository_dispatch` event to centralized repo
- ✅ Includes PR details (number, branch, files, etc.)
- ✅ That's it! No terraform, no OPA, just notify

### 3. Centralized Controller (runs in centralized repo)

File: `centerlized-pipline-/.github/workflows/centralized-controller.yml`

**What it does:**
1. **Receives dispatch event** from dev repo
2. **Checkouts 4 repos:**
   - centerlized-pipline- (for main.tf and scripts)
   - dev-deployment PR branch (for tfvars)
   - OPA-Poclies (for policies)
   - tf-module (for modules)
3. **Gets changed files** from PR
4. **Runs terraform plan** using centralized `main.tf`
5. **Validates with OPA** using centralized policies
6. **Posts comment** to dev repo PR with results
7. **Auto-merges** if OPA passes, **closes** if OPA fails

## Secrets Configuration

### Dev Repos (dev-deployment)

Only needs **2 secrets** for dispatch:

```
GT_APP_ID              - GitHub App ID
GT_APP_PRIVATE_KEY     - GitHub App private key
```

Go to: `https://github.com/Terraform-centilazed-pipline/dev-deployment/settings/secrets/actions`

### Centralized Repo (centerlized-pipline-)

Needs **3 secrets** for full operation:

```
GT_APP_ID              - GitHub App ID (same as dev)
GT_APP_PRIVATE_KEY     - GitHub App private key (same as dev)
AWS_TERRAFORM_ROLE_ARN - AWS IAM role for terraform
```

Go to: `https://github.com/Terraform-centilazed-pipline/centerlized-pipline-/settings/secrets/actions`

## Files Structure

```
dev-deployment/
└── .github/workflows/
    └── dispatch-to-controller.yml    ← Triggers centralized controller

centerlized-pipline-/
├── .github/workflows/
│   └── centralized-controller.yml    ← Main controller (does everything!)
├── main.tf                            ← Centralized terraform config
├── variables.tf
├── outputs.tf
├── providers.tf
└── scripts/
    └── s3-deployment-manager.py       ← Deployment scripts
```

## Testing

### Step 1: Add Secrets

**To dev-deployment:**
```
GT_APP_ID
GT_APP_PRIVATE_KEY
```

**To centerlized-pipline-:**
```
GT_APP_ID
GT_APP_PRIVATE_KEY
AWS_TERRAFORM_ROLE_ARN
```

### Step 2: Create Test PR

```bash
cd dev-deployment
git checkout -b test/dispatch
echo '# test change' >> Accounts/test-4-poc-1/test-4-poc-1.tfvars
git add .
git commit -m "test: trigger centralized controller"
git push origin test/dispatch
```

### Step 3: Create PR on GitHub

Go to: `https://github.com/Terraform-centilazed-pipline/dev-deployment/pulls`

Create PR from `test/dispatch` to `main`

### Step 4: Watch the Magic! ✨

1. **dev-deployment** → PR created
2. **dev-deployment** → `dispatch-to-controller.yml` runs
3. **dev-deployment** → Sends event to centralized repo
4. **centerlized-pipline-** → `centralized-controller.yml` triggers!
5. **centerlized-pipline-** → Runs all terraform/OPA
6. **dev-deployment** → PR gets comment with results
7. **dev-deployment** → PR auto-merges or closes

## Advantages

✅ **True centralization** - All logic in one place
✅ **Single source of truth** - One main.tf, one set of scripts
✅ **Easy to update** - Update centralized repo, all dev repos benefit
✅ **Minimal dev repo setup** - Just one tiny dispatch workflow
✅ **Better security** - AWS credentials only in centralized repo
✅ **Easier debugging** - All runs visible in centralized repo
✅ **Scales easily** - Add new dev repos by copying one workflow file

## Comparison with Terrateam

| Feature | Terrateam | This Solution |
|---------|-----------|---------------|
| Centralized Logic | ✅ Yes | ✅ Yes |
| Auto-merge on Success | ✅ Yes | ✅ Yes |
| Auto-close on Failure | ✅ Yes | ✅ Yes |
| PR Comments | ✅ Yes | ✅ Yes |
| Policy Validation | ✅ Yes (Sentinel) | ✅ Yes (OPA) |
| Multi-repo Support | ✅ Yes | ✅ Yes |
| Cost | 💰 Paid | ✅ Free (GitHub Actions) |
| External Service | ❌ Yes | ✅ No (pure GitHub) |

## Troubleshooting

### Error: "Repository not found" in dispatch

**Cause:** GitHub App not installed on centralized repo

**Fix:**
1. Go to GitHub App settings
2. Install on `centerlized-pipline-` repo

### Error: "Workflow not found"

**Cause:** `centralized-controller.yml` not in main branch

**Fix:**
```bash
cd centerlized-pipline-
git checkout main
# Ensure centralized-controller.yml exists in .github/workflows/
git push origin main
```

### Dispatch event not triggering

**Check:**
1. Is `repository_dispatch` event configured in controller?
2. Are secrets configured in dev repo?
3. Check Actions tab in both repos for errors

### OPA validation not working

**Check:**
1. OPA policies exist in `OPA-Poclies/terraform/s3/`
2. Terraform plan JSON is generated correctly
3. Check controller logs for OPA command output

## Next Steps

1. ✅ Add secrets to both repos
2. ✅ Test with a PR
3. ✅ Review centralized controller logs
4. ✅ Verify PR comments work
5. ✅ Test auto-merge/close functionality
6. 🎯 Add more dev repos (just copy dispatch workflow!)

---

**This is the REAL centralized approach - everything happens in centerlized-pipline-!** 🎉
