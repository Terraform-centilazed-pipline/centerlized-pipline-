# GitHub Secrets Configuration Guide

## Overview

You need to configure secrets in **TWO repositories**:
1. **centerlized-pipline-** (Controller repository)
2. **dev-deployment** (Developer repositories - one or more)

## Required Secrets

### 🔐 Secrets Summary Table

| Secret Name | Required In | Purpose | How to Get |
|-------------|-------------|---------|------------|
| `GITHUB_APP_ID` | Controller only | GitHub App authentication | From GitHub App settings |
| `GITHUB_APP_PRIVATE_KEY` | Both repos | GitHub App authentication | Generated from GitHub App |
| `AWS_TERRAFORM_ROLE_ARN` | Both repos | AWS authentication for Terraform | From AWS IAM |

---

## Part 1: Create GitHub App (One-Time Setup)

### Step 1: Create the GitHub App

1. Go to your organization settings:
   ```
   https://github.com/organizations/Terraform-centilazed-pipline/settings/apps
   ```

2. Click **"New GitHub App"**

3. Fill in the details:

   **GitHub App name**: `terraform-centralized-controller`
   
   **Homepage URL**: `https://github.com/Terraform-centilazed-pipline/centerlized-pipline-`
   
   **Webhook**: ✅ **UNCHECK** "Active" (We don't need webhooks!)
   
   **Permissions**:
   ```
   Repository permissions:
   ├── Actions:        Read and write
   ├── Contents:       Read and write
   ├── Issues:         Read and write
   ├── Pull requests:  Read and write
   └── Workflows:      Read and write
   ```
   
   **Where can this GitHub App be installed?**
   - Select: "Only on this account"

4. Click **"Create GitHub App"**

### Step 2: Generate Private Key

1. After creating the app, scroll down to **"Private keys"**
2. Click **"Generate a private key"**
3. A `.pem` file will be downloaded
4. Keep this file safe! You'll use it for the secret

### Step 3: Note the App ID

1. At the top of the GitHub App settings page, you'll see:
   ```
   App ID: 123456
   ```
2. Copy this number - you'll need it for `GITHUB_APP_ID`

### Step 4: Install the App

1. In the left sidebar, click **"Install App"**
2. Click **"Install"** next to your organization
3. Select **"Only select repositories"**
4. Choose these 4 repositories:
   - ✅ `centerlized-pipline-`
   - ✅ `dev-deployment`
   - ✅ `tf-module`
   - ✅ `OPA-Poclies`
5. Click **"Install"**

---

## Part 2: AWS IAM Role ARN (For Terraform Execution)

### Option A: If you already have the role

Your AWS IAM role should look like:
```
arn:aws:iam::802860742843:role/TerraformExecutionRole
```

This is the role defined in your `providers.tf`:
```hcl
assume_role = {
  role_arn     = "arn:aws:iam::802860742843:role/TerraformExecutionRole"
  session_name = "terraform-s3-backend"
}
```

### Option B: If you need to create the role

See the AWS IAM setup guide in your OPA-Poclies repo:
```bash
cat OPA-Poclies/AWS-IAM-SETUP-GUIDE.md
```

---

## Part 3: Add Secrets to GitHub

### 🎯 Repository 1: centerlized-pipline- (Controller)

1. Go to repository settings:
   ```
   https://github.com/Terraform-centilazed-pipline/centerlized-pipline-/settings/secrets/actions
   ```

2. Click **"New repository secret"** for each:

   #### Secret 1: GITHUB_APP_ID
   ```
   Name:  GITHUB_APP_ID
   Value: 123456
   ```
   *(Replace with your actual App ID from Step 3)*

   #### Secret 2: GITHUB_APP_PRIVATE_KEY
   ```
   Name:  GITHUB_APP_PRIVATE_KEY
   Value: -----BEGIN RSA PRIVATE KEY-----
          MIIEpAIBAAKCAQEA...
          (entire contents of the .pem file)
          ...
          -----END RSA PRIVATE KEY-----
   ```
   ⚠️ **Important**: Copy the ENTIRE contents of the `.pem` file, including the BEGIN and END lines

   #### Secret 3: AWS_TERRAFORM_ROLE_ARN
   ```
   Name:  AWS_TERRAFORM_ROLE_ARN
   Value: arn:aws:iam::802860742843:role/TerraformExecutionRole
   ```
   *(Replace with your actual AWS IAM role ARN)*

### 🎯 Repository 2: dev-deployment (Developer Repo)

1. Go to repository settings:
   ```
   https://github.com/Terraform-centilazed-pipline/dev-deployment/settings/secrets/actions
   ```

2. Click **"New repository secret"** for each:

   #### Secret 1: GITHUB_APP_PRIVATE_KEY
   ```
   Name:  GITHUB_APP_PRIVATE_KEY
   Value: -----BEGIN RSA PRIVATE KEY-----
          MIIEpAIBAAKCAQEA...
          (entire contents of the .pem file)
          ...
          -----END RSA PRIVATE KEY-----
   ```
   ⚠️ **Same `.pem` file as used in controller repo**

   #### Secret 2: AWS_TERRAFORM_ROLE_ARN
   ```
   Name:  AWS_TERRAFORM_ROLE_ARN
   Value: arn:aws:iam::802860742843:role/TerraformExecutionRole
   ```
   *(Same value as controller repo)*

---

## Part 4: Verify Secrets Are Set

### Check Controller Repo (centerlized-pipline-)

```bash
# Should show 3 secrets
https://github.com/Terraform-centilazed-pipline/centerlized-pipline-/settings/secrets/actions
```

Expected:
- ✅ `GITHUB_APP_ID`
- ✅ `GITHUB_APP_PRIVATE_KEY`
- ✅ `AWS_TERRAFORM_ROLE_ARN`

### Check Developer Repo (dev-deployment)

```bash
# Should show 2 secrets
https://github.com/Terraform-centilazed-pipline/dev-deployment/settings/secrets/actions
```

Expected:
- ✅ `GITHUB_APP_PRIVATE_KEY`
- ✅ `AWS_TERRAFORM_ROLE_ARN`

---

## Part 5: How Secrets Are Used

### In Controller Workflow (controller-simple.yml)

```yaml
jobs:
  controller:
    steps:
      - name: Generate GitHub App Token
        id: app-token
        uses: actions/create-github-app-token@v1
        with:
          app-id: ${{ secrets.GITHUB_APP_ID }}              # ← Used here
          private-key: ${{ secrets.GITHUB_APP_PRIVATE_KEY }} # ← Used here

      - name: Checkout controller repo
        uses: actions/checkout@v4
        with:
          token: ${{ steps.app-token.outputs.token }}       # ← Uses generated token
          repository: Terraform-centilazed-pipline/centerlized-pipline-
          path: controller

      - name: Terraform Plan
        env:
          AWS_ROLE_ARN: ${{ secrets.AWS_TERRAFORM_ROLE_ARN }} # ← Used here
        run: |
          terraform plan
```

### In Developer Workflow (trigger-controller.yml)

```yaml
jobs:
  call-controller:
    uses: Terraform-centilazed-pipline/centerlized-pipline-/.github/workflows/controller-simple.yml@main
    with:
      changed_files: ${{ github.event.pull_request.changed_files }}
      pr_number: ${{ github.event.pull_request.number }}
      event_type: ${{ github.event_name }}
    secrets:
      APP_PRIVATE_KEY: ${{ secrets.GITHUB_APP_PRIVATE_KEY }}  # ← Passed to controller
      AWS_ROLE_ARN: ${{ secrets.AWS_TERRAFORM_ROLE_ARN }}     # ← Passed to controller
```

---

## Common Issues & Solutions

### ❌ Issue: "Resource not accessible by integration"

**Cause**: GitHub App doesn't have correct permissions

**Solution**:
1. Go to GitHub App settings
2. Check all 5 permissions are set to "Read and write"
3. Click "Save changes"
4. Re-install the app on your repositories

### ❌ Issue: "Bad credentials"

**Cause**: Private key not copied correctly

**Solution**:
1. Make sure you copied the ENTIRE `.pem` file contents
2. Include the `-----BEGIN RSA PRIVATE KEY-----` line
3. Include the `-----END RSA PRIVATE KEY-----` line
4. Don't add any extra spaces or newlines

### ❌ Issue: "Invalid App ID"

**Cause**: Wrong App ID value

**Solution**:
1. Go to your GitHub App settings
2. Copy the exact App ID number shown at the top
3. Don't include any letters or special characters

### ❌ Issue: AWS authentication fails

**Cause**: Wrong role ARN or role doesn't exist

**Solution**:
1. Verify the role exists in AWS IAM
2. Check the ARN format: `arn:aws:iam::ACCOUNT_ID:role/ROLE_NAME`
3. Ensure the role has trust policy for GitHub OIDC

---

## AWS IAM Role Trust Policy

Your `TerraformExecutionRole` should have this trust policy:

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

This allows GitHub Actions from your organization to assume the role.

---

## Testing the Setup

### Test 1: Verify GitHub App Token Generation

1. Go to Actions tab in controller repo
2. Manually trigger a workflow (or create a test PR)
3. Check if "Generate GitHub App Token" step succeeds

### Test 2: Verify Cross-Repo Access

1. Check if "Checkout all repos" step succeeds
2. Should see all 4 repos checked out:
   - ✅ dev-deployment
   - ✅ centerlized-pipline-
   - ✅ tf-module
   - ✅ OPA-Poclies

### Test 3: Verify AWS Authentication

1. Check if "Terraform init" step succeeds
2. Should see: "Successfully configured backend"
3. No AWS authentication errors

---

## Security Best Practices

### ✅ Do:
- ✅ Use repository secrets (not environment secrets)
- ✅ Generate a unique private key for each GitHub App
- ✅ Rotate GitHub App keys periodically (every 90 days)
- ✅ Use AWS IAM roles (OIDC) instead of access keys
- ✅ Limit GitHub App permissions to minimum required
- ✅ Use separate AWS roles for different environments

### ❌ Don't:
- ❌ Store private keys in code
- ❌ Share private keys across multiple apps
- ❌ Use long-lived AWS access keys
- ❌ Grant more permissions than needed
- ❌ Store secrets in environment variables locally

---

## Quick Setup Checklist

```
□ Create GitHub App
  □ Set 5 permissions (Actions, Contents, Issues, PRs, Workflows)
  □ Disable webhooks
  □ Generate private key (.pem file)
  □ Note the App ID
  □ Install on 4 repositories

□ Configure Controller Repo (centerlized-pipline-)
  □ Add GITHUB_APP_ID
  □ Add GITHUB_APP_PRIVATE_KEY
  □ Add AWS_TERRAFORM_ROLE_ARN

□ Configure Developer Repo (dev-deployment)
  □ Add GITHUB_APP_PRIVATE_KEY
  □ Add AWS_TERRAFORM_ROLE_ARN

□ Verify AWS IAM Role
  □ Role exists in AWS account 802860742843
  □ Trust policy allows GitHub OIDC
  □ Permissions for S3, KMS, IAM, etc.

□ Test the Setup
  □ Create test PR in dev-deployment
  □ Check workflow runs successfully
  □ Verify cross-repo access works
  □ Verify AWS authentication works
```

---

## Summary

### Secrets Required by Repository

| Repository | GITHUB_APP_ID | GITHUB_APP_PRIVATE_KEY | AWS_TERRAFORM_ROLE_ARN |
|------------|---------------|------------------------|------------------------|
| **centerlized-pipline-** | ✅ Required | ✅ Required | ✅ Required |
| **dev-deployment** | ❌ Not needed | ✅ Required | ✅ Required |
| **tf-module** | ❌ Not needed | ❌ Not needed | ❌ Not needed |
| **OPA-Poclies** | ❌ Not needed | ❌ Not needed | ❌ Not needed |

### Total Secrets Needed

- **1 GitHub App** (with ID and private key)
- **1 AWS IAM Role ARN**
- **5 secret values** total (3 in controller, 2 in dev-deployment)

Once configured, your centralized pipeline will work automatically! 🚀
