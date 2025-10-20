# 🎯 SIMPLIFIED GitHub Secrets Setup

## 🎉 GREAT NEWS: Dev Repos Need ZERO Secrets!

After optimization, we've eliminated ALL secret requirements from developer repositories!

---

## 📊 Secret Requirements Summary

### **Controller Repo** (`centerlized-pipline-`) - **3 Secrets**

| Secret Name | Purpose | Where to Get |
|------------|---------|--------------|
| `GTHUB_APP_ID` | Identifies the GitHub App | GitHub App settings page |
| `GTHUB_APP_PRIVATE_KEY` | Authenticates as the GitHub App | Generate from GitHub App |
| `AWS_TERRAFORM_ROLE_ARN` | AWS role for Terraform execution | Your AWS IAM console |

### **Developer Repos** (`dev-deployment`, etc.) - **0 Secrets** ✅

**NO SECRETS NEEDED!** The controller handles all authentication centrally.

---

## 🔧 Setup Instructions

### Step 1: Create GitHub App (One Time)

1. **Navigate to GitHub App settings:**
   ```
   https://github.com/organizations/Terraform-centilazed-pipline/settings/apps
   ```

2. **Click "New GitHub App"**

3. **Configure the App:**
   - **Name:** `terraform-centralized-controller`
   - **Homepage URL:** `https://github.com/Terraform-centilazed-pipline/centerlized-pipline-`
   - **Webhook:** ❌ **UNCHECK "Active"** (we don't use webhooks!)

4. **Set Permissions** (All "Read and write"):
   - ✅ **Actions**
   - ✅ **Contents**
   - ✅ **Issues**
   - ✅ **Pull requests**
   - ✅ **Workflows**

5. **Create the App**

6. **After Creation:**
   - **Note the App ID** (shown at top of page, e.g., `123456`)
   - **Generate Private Key:**
     - Scroll down to "Private keys"
     - Click "Generate a private key"
     - Downloads a `.pem` file - **SAVE THIS SAFELY!**

7. **Install the App:**
   - Click "Install App" in left sidebar
   - Select your organization
   - Choose "All repositories" OR select these 4:
     - `centerlized-pipline-`
     - `dev-deployment`
     - `tf-module`
     - `OPA-Poclies`

---

### Step 2: Add Secrets to Controller Repo ONLY

**Repository:** `centerlized-pipline-`

**URL:** 
```
https://github.com/Terraform-centilazed-pipline/centerlized-pipline-/settings/secrets/actions
```

#### Secret 1: GTHUB_APP_ID

1. Click "New repository secret"
2. **Name:** `GTHUB_APP_ID`
3. **Value:** Your App ID number (e.g., `123456`)
4. Click "Add secret"

#### Secret 2: GTHUB_APP_PRIVATE_KEY

1. Click "New repository secret"
2. **Name:** `GTHUB_APP_PRIVATE_KEY`
3. **Value:** Open your `.pem` file and copy **ENTIRE contents** including:
   ```
   -----BEGIN RSA PRIVATE KEY-----
   MIIEpAIBAAKCAQEA...
   (all the encoded lines)
   ...
   -----END RSA PRIVATE KEY-----
   ```
4. Click "Add secret"

#### Secret 3: AWS_TERRAFORM_ROLE_ARN

1. Click "New repository secret"
2. **Name:** `AWS_TERRAFORM_ROLE_ARN`
3. **Value:** Your AWS IAM role ARN:
   ```
   arn:aws:iam::802860742843:role/TerraformExecutionRole
   ```
4. Click "Add secret"

---

### Step 3: Verify Setup

#### Controller Repo Verification

Navigate to:
```
https://github.com/Terraform-centilazed-pipline/centerlized-pipline-/settings/secrets/actions
```

You should see **3 secrets**:
- ✅ GTHUB_APP_ID
- ✅ GTHUB_APP_PRIVATE_KEY
- ✅ AWS_TERRAFORM_ROLE_ARN

#### Dev Repo Verification

Navigate to:
```
https://github.com/Terraform-centilazed-pipline/dev-deployment/settings/secrets/actions
```

You should see: **ZERO secrets!** ✅

---

## 🔄 How It Works (Updated Flow)

```
┌───────────────────────────────────────────────────────────────┐
│ 1. Dev Repo (dev-deployment)                                  │
│    ├─ PR created on Accounts/**/*.tfvars                      │
│    ├─ trigger-controller.yml runs                             │
│    └─ Calls controller workflow (NO secrets needed!)          │
└───────────────────────────────────────────────────────────────┘
                            │
                            │ workflow_call
                            │ (GitHub Actions built-in feature)
                            ▼
┌───────────────────────────────────────────────────────────────┐
│ 2. Controller Repo (centerlized-pipline-)                     │
│    ├─ Uses its OWN secrets:                                   │
│    │  ├─ GTHUB_APP_ID                                        │
│    │  ├─ GTHUB_APP_PRIVATE_KEY                               │
│    │  └─ AWS_TERRAFORM_ROLE_ARN                               │
│    ├─ Generates GitHub App token                              │
│    ├─ Checks out all 4 repos                                  │
│    ├─ Runs terraform plan/apply                               │
│    ├─ Validates with OPA policies                             │
│    └─ Posts results to PR                                     │
└───────────────────────────────────────────────────────────────┘
```

**Key Benefits:**
- ✅ Dev repos are completely "dumb" - just trigger the controller
- ✅ Controller is "smart" - handles ALL authentication
- ✅ One place to manage secrets (controller only)
- ✅ Adding new dev repos = just add trigger workflow, no secrets!

---

## 🧪 Testing

### Test 1: Create a Test PR

1. In `dev-deployment` repo, edit a file:
   ```bash
   vi Accounts/dev/test-bucket.tfvars
   ```

2. Make a small change (e.g., add a tag)

3. Create a Pull Request

4. Check the "Actions" tab - you should see:
   - ✅ `trigger-controller.yml` runs in dev-deployment
   - ✅ `controller-simple.yml` runs in centerlized-pipline-
   - ✅ All 4 repos checked out
   - ✅ Terraform plan executes
   - ✅ OPA validation runs
   - ✅ PR comment posted with results

### Test 2: Verify No Secret Errors

Check the workflow logs for:
- ✅ "Generate GitHub App Token" - should succeed
- ✅ No "missing secret" errors
- ✅ All checkout steps succeed

---

## 🐛 Troubleshooting

### ❌ Error: "Resource not accessible by integration"

**Cause:** GitHub App permissions not set correctly

**Fix:**
1. Go to your GitHub App settings
2. Verify ALL 5 permissions are "Read and write":
   - Actions
   - Contents
   - Issues
   - Pull requests
   - Workflows
3. Save changes
4. Re-run the workflow

### ❌ Error: "Bad credentials" or "Invalid token"

**Cause:** Private key not copied correctly

**Fix:**
1. Re-download the `.pem` file from GitHub App settings
2. Copy the ENTIRE contents including BEGIN/END lines
3. Update `GTHUB_APP_PRIVATE_KEY` secret
4. Make sure no extra spaces or newlines

### ❌ Error: "Invalid App ID"

**Cause:** App ID has wrong format

**Fix:**
1. App ID should be ONLY numbers (e.g., `123456`)
2. No letters, no quotes, no spaces
3. Find it at the top of your GitHub App settings page

### ❌ Error: "AssumeRole failed" or AWS permission denied

**Cause:** AWS IAM role issue

**Fix:**
1. Verify `AWS_TERRAFORM_ROLE_ARN` is correct:
   ```
   arn:aws:iam::802860742843:role/TerraformExecutionRole
   ```
2. Check the trust policy allows GitHub OIDC:
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Principal": {
           "Federated": "arn:aws:iam::802860742843:oidc-provider/token.actions.githubusercontent.com"
         },
         "Action": "sts:AssumeRoleWithWebIdentity",
         "Condition": {
           "StringEquals": {
             "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
           },
           "StringLike": {
             "token.actions.githubusercontent.com:sub": "repo:Terraform-centilazed-pipline/*:*"
           }
         }
       }
     ]
   }
   ```

---

## 📋 Quick Setup Checklist

- [ ] Create GitHub App
  - [ ] Set 5 permissions to "Read and write"
  - [ ] Disable webhook
  - [ ] Generate private key
  - [ ] Note App ID
  - [ ] Install on 4 repos

- [ ] Add secrets to **controller repo only**:
  - [ ] GTHUB_APP_ID
  - [ ] GTHUB_APP_PRIVATE_KEY
  - [ ] AWS_TERRAFORM_ROLE_ARN

- [ ] Verify **dev repos have ZERO secrets**

- [ ] Test with a PR

---

## 🎯 What Changed from Original Design?

### Before (Overcomplicated):
```yaml
# Dev repos needed 2 secrets:
- GTHUB_APP_PRIVATE_KEY
- AWS_TERRAFORM_ROLE_ARN

# Dev repo passed them to controller:
secrets:
  APP_PRIVATE_KEY: ${{ secrets.GTHUB_APP_PRIVATE_KEY }}
  AWS_ROLE_ARN: ${{ secrets.AWS_TERRAFORM_ROLE_ARN }}
```

### After (Simplified):
```yaml
# Dev repos need 0 secrets!

# Dev repo just calls controller:
uses: Terraform-centilazed-pipline/centerlized-pipline-/.github/workflows/controller-simple.yml@main
with:
  changed_files: ...
  pr_number: ...
  event_type: ...
# NO secrets section!
```

**Why This Works:**
- `workflow_call` is a built-in GitHub Actions feature
- No authentication needed to CALL a workflow in same org
- Controller uses its OWN secrets for everything
- Much simpler and more maintainable!

---

## 🔐 Security Best Practices

1. **Private Key Protection:**
   - Never commit `.pem` file to git
   - Store it securely (password manager, vault)
   - Rotate keys periodically

2. **AWS Role Permissions:**
   - Follow principle of least privilege
   - Only grant permissions needed for Terraform
   - Use separate roles for dev/staging/prod

3. **GitHub App Installation:**
   - Only install on repos that need it
   - Regularly audit installed apps
   - Review permissions periodically

4. **Secret Rotation:**
   - Set calendar reminder to rotate keys quarterly
   - Have process to update without downtime
   - Test with non-production repos first

---

## 📚 Related Documentation

- **Complete Setup Guide:** `GITHUB-SECRETS-SETUP.md`
- **Architecture Overview:** `ARCHITECTURE-SUMMARY.md`
- **Best Practices:** `TERRAFORM-BEST-PRACTICES.md`
- **Multi-Module Guide:** `MULTI-MODULE-GUIDE.md`

---

## ❓ FAQ

**Q: Why don't dev repos need secrets anymore?**
A: The controller repo handles all authentication. Dev repos just trigger it using GitHub's built-in `workflow_call` feature.

**Q: Can different dev repos use different AWS roles?**
A: Not with this simplified design. All use the same controller secrets. If you need per-repo AWS roles, you'd need to pass them as secrets (original design).

**Q: What if I want to add a new dev repo?**
A: Just add the `trigger-controller.yml` file. No secrets needed!

**Q: Is the private key safe when passed between workflows?**
A: We're NOT passing it anymore! Controller uses its own private key secret directly.

**Q: What if the GitHub App is deleted?**
A: Workflows will fail. Just recreate the app, generate new key, update secrets.

---

## 🎉 Summary

**Before:** Complex setup, secrets in multiple places, hard to maintain

**After:** Simple setup, all secrets in one place, easy to scale

**Dev Repo Setup Time:** 
- Before: ~5 minutes (add workflow + configure 2 secrets)
- After: ~1 minute (just add workflow file!)

**Maintenance:**
- Before: Update secrets in N repos when rotating keys
- After: Update secrets in 1 repo only!

This is the **Balanced MVP** done right! 🚀
