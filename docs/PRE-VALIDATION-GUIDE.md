# 🚀 Pre-Deployment Validation Quick Guide

## What Gets Validated BEFORE Terraform Plan?

Your **tfvars file** is checked for 3 required fields:

### 1. ✅ Application/Project Name
```hcl
# In your .tfvars file:
application_name = "s3-management"     # or
project_name = "test-poc-3"            # or
project = "lambda-functions"
```

**Checks:**
- ✅ Is the application in the **allowed list**?
- ✅ Is it allowed in this **environment**?
- ✅ Is it **active**?

**Allowed applications:**
- `s3-management` - S3 bucket management (dev/staging/prod)
- `database-management` - RDS/DynamoDB (staging/prod)
- `lambda-functions` - Lambda deployments (dev/staging/prod)
- `network-infra` - VPC/networking (prod only)
- `test-poc-3` - Test projects (dev/staging)

### 2. ✅ Team Name
```hcl
# In your .tfvars file:
team_name = "platform-team"   # or
team = "dev-team"             # or
owner_team = "qa-team"
```

**Checks:**
- ✅ Does the team **exist**?
- ✅ Is the **PR author** a member of this team?
- ✅ Is this team **authorized** for the application?

**Available teams:**
- `platform-team` - Full access to everything
- `dev-team` - Dev/staging, S3/Lambda/DynamoDB only
- `qa-team` - Staging/testing, S3/RDS only
- `prod-team` - Production access, all services
- `executive-team` - Ultimate authority

### 3. ✅ Cost Center
```hcl
# In your .tfvars file:
cost_center = "CC-1001"      # or
costcenter = "CC-2001"       # or
billing_code = "CC-9999"
```

**Checks:**
- ✅ Is the cost center **valid**?
- ✅ Is your team **authorized** to use it?
- ✅ Is it **active**?

**Available cost centers:**
- `CC-1001` - Platform Engineering ($10K/month budget)
- `CC-2001` - Product Development ($5K/month budget)
- `CC-2002` - QA and Testing ($2K/month budget)
- `CC-3001` - Production Systems ($15K/month budget)
- `CC-9999` - Sandbox/Experimental ($500/month budget)

## Example .tfvars File

```hcl
# Required for pre-validation
application_name = "s3-management"
team_name = "platform-team"
cost_center = "CC-1001"
environment = "development"
account_name = "arj-wkld-a-nonprd"

# Your actual infrastructure variables
region = "us-east-1"
bucket_name = "my-test-bucket"
enable_versioning = true
# ... more variables ...
```

## What Happens During Validation?

```
┌─────────────────────────┐
│   PR Created            │
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│ 1. Extract tfvars       │
│    - application_name   │
│    - team_name          │
│    - cost_center        │
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│ 2. Check Application    │
│    ✓ In allowed list?   │
│    ✓ Allowed env?       │
│    ✓ Active?            │
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│ 3. Check Team           │
│    ✓ Team exists?       │
│    ✓ PR author member?  │
│    ✓ Team authorized?   │
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│ 4. Check Cost Center    │
│    ✓ Valid?             │
│    ✓ Team authorized?   │
│    ✓ Active?            │
└────────┬────────────────┘
         │
         ▼
    ┌────────┐
    │ PASSED?│
    └───┬─┬──┘
        │ │
    YES │ │ NO
        │ │
        ▼ ▼
    ┌────┐ ┌──────────────┐
    │Run │ │ Close PR     │
    │Plan│ │ Post Comment │
    └────┘ └──────────────┘
```

## PR Comment Examples

### ✅ Success (All Checks Pass)

```markdown
## ✅ Pre-Deployment Validation Passed

**👤 PR Author:** @pragadeeswarpa
**📄 Validated File:** `Accounts/arj-wkld-a-nonprd/development/test-poc-3/terraform.tfvars`

---

### 📋 Validation Checklist

| Check | Status | Details |
|-------|--------|----------|
| **Application/Project** | ✅ | `s3-management` |
| **Team Authorization** | ✅ | `platform-team` |
| **Cost Center** | ✅ | `CC-1001` |

### 📊 Deployment Metadata

```yaml
Application: s3-management
Team: platform-team
Cost Center: CC-1001
Environment: development
Account: arj-wkld-a-nonprd
```

---

### ✅ Next Steps

All pre-deployment validations passed!

**The workflow will now:**
1. ✅ Run terraform plan
2. 🛡️ Validate with OPA security policies
3. 💰 Estimate deployment costs
4. 🎯 Determine approval requirements
```

### ❌ Failure (Invalid Application)

```markdown
## ❌ Pre-Deployment Validation Failed

**👤 PR Author:** @dev-user1
**📄 Validated File:** `Accounts/arj-wkld-a-nonprd/development/my-app/terraform.tfvars`

---

### 📋 Validation Checklist

| Check | Status | Details |
|-------|--------|----------|
| **Application/Project** | ❌ | `my-app` |
| **Team Authorization** | ✅ | `dev-team` |
| **Cost Center** | ✅ | `CC-2001` |

### 🚫 Validation Errors

- ❌ Application 'my-app' not in allowed list. Available: s3-management, database-management, lambda-functions, network-infra, test-poc-3

---

### ❌ Required Actions

**Deployment is blocked.** Please fix the errors above:

1. Update your `tfvars` file with correct values
2. Ensure you're using an approved:
   - Application/Project name
   - Team name (that you're a member of)
   - Cost center (authorized for your team)
3. Push changes to re-trigger validation

**Need help?**
- Check allowed values in [`deployment-rules.yaml`](../deployment-rules.yaml)
- Contact your team lead or platform engineering
```

### ❌ Failure (Unauthorized Team)

```markdown
## ❌ Pre-Deployment Validation Failed

### 🚫 Validation Errors

- ❌ User 'qa-user1' is not a member of team 'platform-team'
- ❌ Team 'qa-team' not authorized for application 'network-infra'
```

## Common Errors & Solutions

### Error: "Application not in allowed list"
**Solution:** Use one of the approved application names from the list above, or request to add your application to `deployment-rules.yaml`

### Error: "User not a member of team"
**Solution:** Either:
- Use your actual team name in tfvars
- Request to be added to the team
- Contact team lead

### Error: "Team not authorized for application"
**Solution:** Your team doesn't have access to deploy this application. Contact platform engineering.

### Error: "Cost center not in approved list"
**Solution:** Use a valid cost center code, or request your cost center be added to the system.

### Error: "Team not authorized to use cost center"
**Solution:** Use a cost center your team is authorized for, or request authorization.

### Error: "Cost center is inactive"
**Solution:** This cost center is disabled. Use a different active cost center.

## How to Add New Items

### Add New Application
Edit `deployment-rules.yaml`:
```yaml
allowed_applications:
  your-new-app:
    name: "Your Application Name"
    description: "What it does"
    allowed_teams:
      - platform-team
      - your-team
    allowed_environments:
      - development
      - staging
    services:
      - s3
      - lambda
    active: true
```

### Add New Cost Center
Edit `deployment-rules.yaml`:
```yaml
cost_centers:
  CC-XXXX:
    name: "Your Department"
    description: "Purpose"
    authorized_teams:
      - your-team
    budget_monthly: 5000.00
    budget_annual: 60000.00
    active: true
    owner: "your-username"
```

### Add Team Member
Edit `deployment-rules.yaml`:
```yaml
teams:
  your-team:
    members:
      - existing-user
      - new-user  # Add here
```

## Benefits

1. **🚀 Fast Feedback** - Know immediately if your deployment will be blocked
2. **💰 Cost Tracking** - All deployments tied to cost centers
3. **🔒 Security** - Only authorized teams can deploy to each environment
4. **📊 Auditability** - Track who deploys what, with which budget
5. **⚡ No Wasted Terraform Plans** - Don't run plan if it will be rejected anyway

## Need Help?

1. Check `deployment-rules.yaml` for:
   - Allowed applications
   - Team memberships
   - Cost center authorizations

2. Contact:
   - **Team Lead** - For team access
   - **Platform Engineering** - For application approvals
   - **Finance** - For cost center issues

---

**Remember:** These checks run BEFORE terraform plan to save time and prevent unauthorized deployments! 🎯
