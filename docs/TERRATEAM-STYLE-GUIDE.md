# 🚀 Terrateam-Style Deployment Management

## Overview

This implementation provides **Terrateam-style features** for your centralized Terraform pipeline:

1. ✅ **Cost Estimation** - Show estimated AWS costs before deployment
2. ✅ **Approval Thresholds** - Auto-approve small changes, require approval for large ones
3. ✅ **Beautiful PR Comments** - Rich formatted comments like Terrateam
4. ✅ **Team-Based Access Control** - Only authorized teams can deploy
5. ✅ **Multi-Tier Approvals** - Different approval levels based on cost/impact

## How It Works

```
┌─────────────────┐
│   Developer     │
│  Creates PR     │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────────────────┐
│         Centralized Controller Workflow         │
├─────────────────────────────────────────────────┤
│  1. ✅ Terraform Plan                           │
│  2. 🛡️ OPA Security Validation                 │
│  3. 💰 Cost Estimation                          │
│  4. 🔐 Team Authorization Check                 │
│  5. 📊 Determine Approval Tier                  │
│  6. 💬 Post Beautiful PR Comment                │
└────────┬────────────────────────────────────────┘
         │
         ▼
    ┌────────────────┐
    │  Auto-Approve? │
    └────┬───────┬───┘
         │       │
    YES  │       │  NO
         │       │
         ▼       ▼
    ┌─────┐  ┌────────────────┐
    │Merge│  │ Wait for       │
    │ &   │  │ Approval(s)    │
    │Apply│  └────────────────┘
    └─────┘
```

## Approval Tiers

### 🟢 Auto-Approve (Tier 0)
- **Cost:** < $50/month
- **Resources:** ≤ 5 created, ≤ 3 destroyed
- **Approvals Needed:** 0 (automatic)
- **Example:** Adding a small S3 bucket, Lambda function

### 🟡 Tier 1 Approval
- **Cost:** $50 - $500/month
- **Resources:** ≤ 20 created, ≤ 10 destroyed
- **Approvals Needed:** 1
- **Approvers:** Dev Team Lead, Platform Team
- **Example:** Adding RDS instance, multiple Lambda functions

### 🟠 Tier 2 Approval
- **Cost:** $500 - $2,000/month
- **Resources:** ≤ 50 created, ≤ 25 destroyed
- **Approvals Needed:** 2
- **Approvers:** Senior Engineers, Platform Team
- **Example:** Multiple RDS clusters, NAT Gateway, large EC2 fleet

### 🔴 Tier 3 Approval (Executive)
- **Cost:** > $2,000/month
- **Resources:** > 50 created or > 25 destroyed
- **Approvals Needed:** 3
- **Approvers:** CTO, VP Engineering, Director of Infrastructure
- **Example:** Major infrastructure overhaul, production migration

## Team-Based Access Control

### Defined Teams

#### 1. **Platform Team** (Full Access)
- **Members:** `pragadeeswarpa`, `infra-admin`, `devops-lead`
- **Access:** All accounts, all environments, all services
- **Can Approve:** All tiers including Tier 3

#### 2. **Development Team** (Limited Access)
- **Members:** `dev-user1`, `dev-user2`, `dev-lead`
- **Access:**
  - Accounts: `arj-wkld-a-nonprd` only
  - Environments: `development`, `staging`
  - Services: S3, Lambda, DynamoDB
- **Can Approve:** Tier 1 only

#### 3. **QA Team** (Read/Test Access)
- **Members:** `qa-user1`, `qa-engineer`
- **Access:**
  - Accounts: `arj-wkld-a-nonprd` only
  - Environments: `staging`, `testing`
  - Services: S3, RDS
- **Can Approve:** None (can only create PRs)

#### 4. **Production Team** (Prod Access)
- **Members:** `prod-admin`, `senior-engineer1`, `senior-engineer2`
- **Access:**
  - Accounts: `arj-wkld-a-prd` only
  - Environments: `production`
  - Services: All
- **Can Approve:** Tier 1 and Tier 2

#### 5. **Executive Team** (Ultimate Authority)
- **Members:** `cto`, `vp-engineering`, `director-infra`
- **Access:** Everything
- **Can Approve:** All tiers

## Configuration Files

### 1. `deployment-rules.yaml`

Main configuration file defining:

```yaml
cost_thresholds:
  auto_approve:
    max_monthly_cost: 50.00
    max_hourly_cost: 0.07
    
  tier1_approval:
    max_monthly_cost: 500.00
    required_approvals: 1
    
  tier2_approval:
    max_monthly_cost: 2000.00
    required_approvals: 2
    
  tier3_approval:
    min_monthly_cost: 2000.01
    required_approvals: 3
    requires_executives: true

teams:
  platform-team:
    members: [pragadeeswarpa, infra-admin]
    permissions:
      - all_accounts
      - all_environments
      - all_services
    can_approve_tier1: true
    can_approve_tier2: true
    can_approve_tier3: true

environments:
  production:
    auto_approve_enabled: false
    min_required_approvals: 2
    require_opa_validation: true
```

### 2. `scripts/terrateam-manager.py`

Python script that:
- Estimates costs from Terraform plan
- Checks team authorization
- Determines approval tier
- Generates beautiful PR comments

## PR Comment Example

When a PR is created, you'll see a comment like this:

```markdown
## ⏳ **Approval Required**

**👤 Author:** @dev-user1
**👥 Team:** Development Team
**🎯 Approval Tier:** `tier1_approval`
**✋ Required Approvals:** 1

---

### 📦 Resource Changes

| Action | Count |
|--------|-------|
| 🟢 **To Create** | `3` |
| 🔄 **To Change** | `1` |
| 🗑️ **To Destroy** | `0` |
| **Total** | **`4`** |

### 💰 Cost Estimation

**Monthly Cost:** `$127.45 USD/month`

**Breakdown by Service:**

- **S3**: $23.00/month
- **LAMBDA**: $4.45/month
- **RDS**: $100.00/month

### 🛡️ Security Validation

✅ All security policies passed

### 🔐 Authorization

✅ dev-user1 is authorized for this deployment

---

### 🎯 Decision: ⏳ Approval required: 1 approver(s) needed ($127.45/mo)

⏳ **Waiting for 1 approval(s)**

**Approvers must:**
1. Review the plan and cost estimation
2. Approve this PR
3. System will auto-merge once approvals are met

---
*Powered by Centralized Terraform Controller | [View Rules](../deployment-rules.yaml)*
```

## Workflow Integration

### Step-by-Step Process

1. **Developer creates PR** in source repo
2. **Workflow triggers** via repository_dispatch
3. **Terraform Plan** is generated
4. **OPA Validation** checks security policies
5. **Cost Estimation** calculates monthly costs
6. **Team Authorization** verifies PR author permissions
7. **Approval Tier** is determined based on cost + impact
8. **PR Comment** is posted with all details
9. **Decision:**
   - **Auto-approve:** Merge and apply immediately
   - **Requires approval:** Wait for human reviewers
   - **Blocked:** Close PR if unauthorized or security failed

### Workflow YAML Additions

Add these steps to `centralized-controller.yml`:

```yaml
- name: 💰 Cost Estimation & Approval Decision
  id: deployment_decision
  working-directory: source-repo
  run: |
    python3 ../controller/scripts/terrateam-manager.py \
      "${{ github.event.client_payload.pr_author }}" \
      "$ACCOUNT" \
      "$ENVIRONMENT" \
      "$SERVICE" \
      "canonical-plan/plan.json" \
      "${{ steps.opa.outputs.validation_status == 'passed' }}" \
      "${{ steps.opa.outputs.critical_violations }}"
    
    # Parse decision
    DECISION=$(cat decision.json)
    echo "approved=$(echo $DECISION | jq -r '.approved')" >> $GITHUB_OUTPUT
    echo "approval_tier=$(echo $DECISION | jq -r '.approval_tier')" >> $GITHUB_OUTPUT
    echo "monthly_cost=$(echo $DECISION | jq -r '.monthly_cost')" >> $GITHUB_OUTPUT

- name: 💬 Post Terrateam-Style PR Comment
  uses: actions/github-script@v7
  with:
    github-token: ${{ steps.app-token.outputs.token }}
    script: |
      const fs = require('fs');
      const comment = fs.readFileSync('source-repo/pr-comment.md', 'utf8');
      
      await github.rest.issues.createComment({
        owner: '${{ github.event.client_payload.source_owner }}',
        repo: '${{ github.event.client_payload.source_repo }}',
        issue_number: ${{ github.event.client_payload.pr_number }},
        body: comment
      });
```

## Environment-Specific Rules

### Production
- **Auto-approve:** ❌ Disabled
- **Minimum Approvals:** 2
- **OPA Required:** ✅ Yes
- **Cost Estimation:** ✅ Required
- **Allowed Hours:** 09:00-17:00 weekdays only
- **Always requires:** Manual approval regardless of cost

### Staging
- **Auto-approve:** ✅ Enabled (up to $100/mo)
- **Minimum Approvals:** 1
- **OPA Required:** ✅ Yes
- **Cost Estimation:** ✅ Required

### Development
- **Auto-approve:** ✅ Enabled (up to $200/mo)
- **Minimum Approvals:** 0
- **OPA Required:** ✅ Yes
- **Cost Estimation:** ⚠️ Optional

## Security Policies

### Always Require Approval
These resources **always** require manual approval, regardless of cost:
- `aws_iam_role`
- `aws_iam_policy`
- `aws_kms_key`
- `aws_vpc`
- `aws_security_group`

### Forbidden Actions
These actions will **block** deployment:
- Delete production data resources (RDS, DynamoDB with data)
- Disable encryption on existing resources
- Remove backups
- Expose public access (unless explicitly allowed)

## Cost Anomaly Detection

The system alerts if:
- **Cost increases by 200%+** - Potential misconfiguration
- **Cost decreases by 50%+** - Potential accidental deletion
- **Unexpected service costs** - New services not in baseline

## Usage Examples

### Example 1: Small S3 Bucket (Auto-Approved)

**PR:** Add logging bucket
**Resources:** 1 S3 bucket
**Cost:** $23/month
**Result:** ✅ **Auto-approved** - Merged and applied automatically

### Example 2: RDS Database (Requires 1 Approval)

**PR:** Add staging database
**Resources:** 1 RDS instance (db.t3.small)
**Cost:** $127/month
**Result:** ⏳ **Tier 1** - Waits for dev lead approval

### Example 3: Production Migration (Requires 3 Approvals)

**PR:** Migrate to new VPC
**Resources:** 20+ resources (VPC, NAT, ELB, EC2, RDS)
**Cost:** $2,500/month
**Result:** 🔴 **Tier 3** - Requires CTO + VP + Director approval

### Example 4: Unauthorized User (Blocked)

**PR:** Deploy to production
**Author:** qa-user1 (QA team - no prod access)
**Result:** ❌ **Blocked** - PR closed with explanation

## Customization

### Adding New Teams

Edit `deployment-rules.yaml`:

```yaml
teams:
  your-new-team:
    name: "Your Team Name"
    members:
      - github-username1
      - github-username2
    permissions:
      allowed_accounts:
        - your-account
      allowed_environments:
        - development
      allowed_services:
        - s3
        - lambda
    can_approve_tier1: true
    can_approve_tier2: false
    can_approve_tier3: false
```

### Adjusting Cost Thresholds

```yaml
cost_thresholds:
  auto_approve:
    max_monthly_cost: 100.00  # Increase from $50
    
  tier1_approval:
    max_monthly_cost: 1000.00  # Increase from $500
    required_approvals: 1
```

### Adding Service-Specific Rules

```yaml
applications:
  your-service:
    allowed_teams:
      - platform-team
      - your-team
    cost_multiplier: 1.5  # More strict (67% of normal)
    require_encryption: true
```

## Benefits vs Terrateam

| Feature | Terrateam | This Implementation |
|---------|-----------|---------------------|
| Cost Estimation | ✅ Via Infracost | ✅ Built-in (can integrate Infracost) |
| Approval Workflows | ✅ Yes | ✅ Yes (4 tiers) |
| Team Access Control | ✅ Yes | ✅ Yes (detailed RBAC) |
| Beautiful PR Comments | ✅ Yes | ✅ Yes (similar style) |
| OPA Integration | ❌ No | ✅ Yes (comprehensive) |
| Multi-Service Support | ✅ Yes | ✅ Yes (S3, IAM, KMS, Lambda, etc.) |
| Centralized Control | ❌ No | ✅ Yes (centralized repo) |
| Cost | 💰 $20/user/month | 🆓 Free (open source) |

## Troubleshooting

### PR Comment Not Appearing
- Check GitHub App permissions (issues: write)
- Verify token has access to source repository

### Cost Estimation Shows $0
- Check if resource types are in cost_map
- Consider integrating Infracost API for accurate costs

### User Blocked Despite Being in Team
- Verify account/environment/service match in deployment-rules.yaml
- Check team membership is correct (case-sensitive)

### All PRs Require Approval
- Check environment configuration
- Production always requires approval by default
- Verify cost thresholds are not too low

## Next Steps

1. ✅ **Configure Teams** - Add your team members to deployment-rules.yaml
2. ✅ **Adjust Thresholds** - Set cost limits appropriate for your org
3. ✅ **Test with Dev PR** - Create a small PR to see it work
4. ✅ **Integrate Infracost** (Optional) - For accurate cost estimation
5. ✅ **Add Slack Notifications** (Optional) - Alert teams on approvals

## Support

For issues or questions:
- 📖 Check deployment-rules.yaml for configuration
- 🐛 Review workflow logs in GitHub Actions
- 💬 Check PR comments for detailed decision reasoning

---

**🎉 You now have Terrateam-style deployment management with cost control, approval workflows, and team-based access control!**
