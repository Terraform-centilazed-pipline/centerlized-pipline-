# GitHub App Setup Guide - Exact Permissions & Settings

## Step 1: Create GitHub App

Go to: **https://github.com/organizations/YOUR_ORG/settings/apps/new**

Or: **Organization Settings** → **Developer settings** → **GitHub Apps** → **New GitHub App**

---

## Step 2: Basic Information

```yaml
GitHub App name: Terraform-Controller
Description: Centralized Terraform automation and OPA policy enforcement
Homepage URL: https://github.com/Terraform-centilazed-pipline/centerlized-pipline-

Callback URL: [Leave empty]
Setup URL: [Leave empty]

✅ Webhook: Uncheck "Active" (we don't need webhooks!)
Webhook URL: [Leave empty]
```

---

## Step 3: Permissions - EXACT Settings

### Repository Permissions (what the app can do in repos)

```yaml
✅ Actions: Read and write
   - Needed to: Trigger workflows, read workflow runs
   
✅ Contents: Read and write
   - Needed to: Clone repos, read files, commit changes
   
✅ Issues: Read and write
   - Needed to: Create issues for policy violations
   
✅ Metadata: Read-only (automatically selected)
   - Needed to: Access basic repo info
   
✅ Pull requests: Read and write
   - Needed to: Create comments, merge/close PRs
   
✅ Workflows: Read and write
   - Needed to: Trigger controller workflow

❌ Administration: NO
❌ Checks: NO
❌ Commit statuses: NO (optional but not required)
❌ Deployments: NO
❌ Environments: NO
❌ Pages: NO
❌ Secrets: NO
❌ Variables: NO
❌ Webhooks: NO
```

### Organization Permissions

```yaml
❌ Members: NO
❌ Administration: NO
❌ Projects: NO

All others: NO
```

### Account Permissions

```yaml
❌ Email addresses: NO
❌ Followers: NO
❌ GPG keys: NO
❌ Plan: NO

All: NO
```

---

## Step 4: Subscribe to Events

```yaml
✅ Check NONE - we don't use webhooks!

Webhook status: ⚪ Inactive (this is correct!)
```

**Why no webhook events?**
- We use `workflow_call` instead
- No external server needed
- Simpler and more reliable

---

## Step 5: Where can this app be installed?

```yaml
◉ Only on this account
   (Select if org-only)
   
OR

◉ Any account  
   (Select if you want to share with other orgs)
```

**Recommended**: Only on this account (more secure)

---

## Step 6: After Creation

### 6.1 Generate Private Key

1. Scroll down to **Private keys**
2. Click **Generate a private key**
3. Save the `.pem` file securely
4. **Note the App ID** at the top of the page

### 6.2 Install the App

1. Click **Install App** in left sidebar
2. Select **All repositories** OR **Only select repositories**
3. If "Only select", choose:
   ```
   ✅ centerlized-pipline-  (controller repo)
   ✅ dev-deployment        (dev repo)
   ✅ OPA-Poclies           (policies repo)
   ✅ tf-module             (modules repo)
   ```
4. Click **Install**

---

## Step 7: Configure Repository Secrets

### In Controller Repo (`centerlized-pipline-`)

Go to: **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

```bash
# Secret 1
Name: GTHUB_APP_ID
Value: 123456  # Your App ID from GitHub App page

# Secret 2  
Name: GTHUB_APP_PRIVATE_KEY
Value: 
-----BEGIN RSA PRIVATE KEY-----
<paste entire contents of .pem file here>
-----END RSA PRIVATE KEY-----

# Secret 3
Name: AWS_TERRAFORM_ROLE_ARN
Value: arn:aws:iam::ACCOUNT_ID:role/TerraformExecutionRole
```

### In Each Dev Repo (`dev-deployment`, etc.)

Go to: **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

```bash
# Secret 1 (same as controller)
Name: GTHUB_APP_PRIVATE_KEY
Value: 
-----BEGIN RSA PRIVATE KEY-----
<paste entire contents of .pem file here>
-----END RSA PRIVATE KEY-----

# Secret 2 (same as controller)
Name: AWS_TERRAFORM_ROLE_ARN
Value: arn:aws:iam::ACCOUNT_ID:role/TerraformExecutionRole

# Secret 3 (if needed for modules)
Name: GTHUB_APP_ID
Value: 123456
```

---

## Step 8: Verify Installation

### Check App is Installed

1. Go to **Organization Settings** → **GitHub Apps**
2. Click on **Terraform-Controller**
3. Click **Install App** → should show "Installed" on repos

### Check Permissions

In the app page, verify:
- ✅ Actions: Read and write
- ✅ Contents: Read and write
- ✅ Issues: Read and write
- ✅ Pull requests: Read and write
- ✅ Workflows: Read and write

### Test Token Generation

In any workflow, add this step to test:

```yaml
- name: Test GitHub App Token
  uses: tibdex/github-app-token@v2
  with:
    app_id: ${{ secrets.GTHUB_APP_ID }}
    private_key: ${{ secrets.GTHUB_APP_PRIVATE_KEY }}
```

---

## Step 9: Final Checklist

```yaml
✅ GitHub App created
✅ Private key generated and saved
✅ App ID noted
✅ Permissions set correctly:
   - Actions: Read and write
   - Contents: Read and write
   - Issues: Read and write
   - Pull requests: Read and write
   - Workflows: Read and write
✅ Webhook DISABLED (Inactive)
✅ App installed on all required repos
✅ Secrets configured in controller repo:
   - GTHUB_APP_ID
   - GTHUB_APP_PRIVATE_KEY
   - AWS_TERRAFORM_ROLE_ARN
✅ Secrets configured in dev repos:
   - GTHUB_APP_PRIVATE_KEY
   - AWS_TERRAFORM_ROLE_ARN
```

---

## Permissions Summary Table

| Permission | Access Level | Why Needed | Used By |
|------------|--------------|------------|---------|
| **Actions** | Read & Write | Trigger workflows, read runs | Controller workflow |
| **Contents** | Read & Write | Clone repos, read configs | All workflows |
| **Issues** | Read & Write | Create violation issues | Controller (on OPA fail) |
| **Pull Requests** | Read & Write | Comment, merge, close PRs | Controller (auto-merge/close) |
| **Workflows** | Read & Write | Trigger controller workflow | Dev repo trigger |
| **Metadata** | Read-only | Basic repo info | Auto-selected |

---

## Security Best Practices

### ✅ DO:
- Store private key in GitHub Secrets (encrypted)
- Use "Only on this account" for app installation
- Limit app to specific repos if possible
- Rotate private key periodically (every 6-12 months)
- Use minimum required permissions

### ❌ DON'T:
- Commit `.pem` file to git
- Share private key via Slack/email
- Give admin permissions
- Enable unnecessary permissions
- Use personal access tokens instead

---

## Troubleshooting

### "Bad credentials" error
- Check GTHUB_APP_ID matches the app
- Verify GTHUB_APP_PRIVATE_KEY has complete .pem content
- Ensure app is installed on the repository

### "Resource not accessible by integration"
- Check app permissions (needs Read & Write)
- Verify app is installed on target repo
- Check repository visibility (app must have access)

### "Workflow not found"
- Ensure controller workflow is pushed to `main` branch
- Verify workflow path is correct
- Check workflow file has `workflow_call` trigger

### Token expires quickly
- This is normal - tokens last 1 hour
- Generate new token for each workflow run
- Use `tibdex/github-app-token@v2` action

---

## App vs PAT (Personal Access Token)

| Feature | GitHub App | PAT |
|---------|------------|-----|
| **Scope** | Repository-specific | User-wide |
| **Permissions** | Fine-grained | Broad |
| **Expiration** | 1 hour (auto-refresh) | Manual rotation |
| **Audit** | Per-app logs | Per-user logs |
| **Security** | Better | Good |
| **Rate Limits** | 5,000/hour | 5,000/hour |
| **Best For** | Automation | Personal use |

**Recommendation**: Use GitHub App for this workflow (better security)

---

## Quick Reference

```bash
# GitHub App Dashboard
https://github.com/organizations/YOUR_ORG/settings/apps/YOUR_APP_NAME

# App ID Location
Top of GitHub App settings page

# Private Key Location  
GitHub App settings → Private keys section → Generate

# Installation URL
https://github.com/organizations/YOUR_ORG/settings/installations/YOUR_INSTALLATION_ID

# Permissions Check
GitHub App settings → Permissions & events tab
```

---

## What Happens After Setup

1. **Dev creates PR** with terraform changes
2. **Dev repo workflow** triggers (uses `GTHUB_APP_PRIVATE_KEY`)
3. **Workflow generates token** from GitHub App
4. **Token used to call** controller workflow
5. **Controller runs** with full permissions
6. **Controller posts comment** to PR (using app token)
7. **Controller merges/closes** PR (using app token)

All authenticated via GitHub App - secure and auditable! 🔒
