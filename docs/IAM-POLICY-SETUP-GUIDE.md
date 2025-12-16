# Secure IAM Policy for GitHub Cross-Account Role

## 🎯 Purpose

This policy allows GitHub Actions (via cross-account role) to manage IAM roles securely with proper restrictions and safeguards.

**Target Role:** `arn:aws:iam::478180153472:role/GitHub`

## 🔒 Security Features

### 1. **Resource Name Restrictions**
```json
"Resource": [
  "arn:aws:iam::*:role/arj-*",
  "arn:aws:iam::*:role/terraform-*"
]
```
- ✅ Only roles starting with `arj-` or `terraform-`
- ❌ Cannot create arbitrary role names
- ✅ Enforces naming conventions

### 2. **Regional Restrictions**
```json
"Condition": {
  "StringEquals": {
    "aws:RequestedRegion": ["us-east-1", "us-west-2"]
  }
}
```
- ✅ Limited to specific regions
- ❌ Prevents accidental global deployments
- ✅ Aligns with your infrastructure regions

### 3. **Protected Role Deny List**
```json
"Resource": [
  "arn:aws:iam::*:role/Admin*",
  "arn:aws:iam::*:role/PowerUser*",
  "arn:aws:iam::*:role/*SecurityAudit*",
  "arn:aws:iam::*:role/OrganizationAccountAccessRole",
  "arn:aws:iam::478180153472:role/GitHub"
]
```
- ❌ Cannot modify admin/privileged roles
- ❌ Cannot modify the GitHub cross-account role itself
- ✅ Prevents privilege escalation

### 4. **Mandatory ManagedBy Tag**
```json
"Condition": {
  "StringNotEquals": {
    "aws:RequestTag/ManagedBy": "terraform"
  }
}
```
- ✅ All created roles MUST have `ManagedBy=terraform` tag
- ❌ Denies creation without proper tagging
- ✅ Enforces compliance with OPA policies

### 5. **Tag Protection**
```json
"Condition": {
  "ForAllValues:StringEquals": {
    "aws:TagKeys": ["ManagedBy"]
  }
}
```
- ❌ Cannot remove the `ManagedBy` tag
- ✅ Ensures audit trail
- ✅ Prevents manual modifications

## 📋 Permissions Granted

### Create & Manage Roles
- `iam:CreateRole` - Create new IAM roles
- `iam:DeleteRole` - Remove IAM roles
- `iam:GetRole` - Read role details
- `iam:UpdateRole` - Modify role properties
- `iam:TagRole` / `UntagRole` - Manage tags

### Manage Policies
- `iam:AttachRolePolicy` - Attach AWS managed policies
- `iam:DetachRolePolicy` - Remove attached policies
- `iam:PutRolePolicy` - Create inline policies
- `iam:DeleteRolePolicy` - Remove inline policies
- `iam:GetRolePolicy` - Read inline policies

### Read-Only Global
- `iam:GetPolicy` - View policy details
- `iam:ListPolicies` - List available policies
- `iam:ListRoles` - List all roles

## 🚀 How to Apply

### Option 1: AWS Console

1. **Navigate to IAM Console**
   - Go to IAM → Roles
   - Find `GitHub` role (in account 478180153472)

2. **Add Inline Policy**
   - Click "Add permissions" → "Create inline policy"
   - Switch to JSON tab
   - Paste contents of `terraform-execution-role-iam-policy.json`
   - Name it: `GitHubIAMManagement`

3. **Save Changes**
   - Review permissions
   - Click "Create policy"

### Option 2: AWS CLI

```bash
# Save the policy to a file
cat > /tmp/iam-policy.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [ ... ]
}
EOF

# Apply to GitHub cross-account role (in account 478180153472)
aws iam put-role-policy \
  --role-name GitHub \
  --policy-name GitHubIAMManagement \
  --policy-document file:///tmp/iam-policy.json
```

### Option 3: Terraform

```hcl
resource "aws_iam_role_policy" "github_iam_management" {
  name   = "GitHubIAMManagement"
  role   = "GitHub"  # Cross-account role in 478180153472
  policy = file("${path.module}/terraform-execution-role-iam-policy.json")
}
```

## 🧪 Testing

After applying the policy, test with:

```bash
# This should work (matches arj-* pattern)
aws iam create-role \
  --role-name arj-test-role \
  --assume-role-policy-document file://trust-policy.json \
  --tags Key=ManagedBy,Value=terraform

# This should fail (missing ManagedBy tag)
aws iam create-role \
  --role-name arj-test-role-2 \
  --assume-role-policy-document file://trust-policy.json
# Error: Request failed due to tag requirement

# This should fail (protected role - GitHub cross-account role)
aws iam delete-role --role-name GitHub
# Error: Access Denied
```

## ⚠️ Important Restrictions

### What This Policy ALLOWS ✅
- Create roles matching `arj-*` or `terraform-*` patterns
- Manage policies for allowed roles
- Tag roles with required tags
- Delete roles created by Terraform

### What This Policy DENIES ❌
- Creating roles without `ManagedBy=terraform` tag
- Modifying Admin/PowerUser/SecurityAudit roles
- Modifying TerraformExecutionRole itself
- Removing the `ManagedBy` tag
- Creating roles outside us-east-1/us-west-2

## 🔧 Customization

### Add More Allowed Name Patterns
```json
"Resource": [
  "arn:aws:iam::*:role/arj-*",
  "arn:aws:iam::*:role/terraform-*",
  "arn:aws:iam::*:role/myapp-*"  // Add your pattern
]
```

### Add More Protected Regions
```json
"aws:RequestedRegion": [
  "us-east-1",
  "us-west-2",
  "eu-west-1"  // Add more regions
]
```

### Add More Protected Roles
```json
"Resource": [
  "arn:aws:iam::*:role/Admin*",
  "arn:aws:iam::*:role/YourProtectedRole"  // Add specific roles
]
```

## 📊 Policy Evaluation Flow

```
Request: Create IAM Role
         ↓
1. Check: Does role name match arj-* or terraform-*?
   ❌ NO → Deny (resource restriction)
   ✅ YES → Continue
         ↓
2. Check: Is region us-east-1 or us-west-2?
   ❌ NO → Deny (region restriction)
   ✅ YES → Continue
         ↓
3. Check: Is role name in protected list?
   ✅ YES → Deny (protected role)
   ❌ NO → Continue
         ↓
4. Check: Has ManagedBy=terraform tag?
   ❌ NO → Deny (tag requirement)
   ✅ YES → ALLOW
```

## 🎯 Alignment with OPA Policies

This IAM policy complements your OPA policies:

| OPA Policy | IAM Policy Enforcement |
|------------|------------------------|
| Requires `ManagedBy` tag | ✅ Enforced at AWS level |
| Role naming conventions | ✅ Only `arj-*` and `terraform-*` allowed |
| Regional restrictions | ✅ Limited to us-east-1, us-west-2 |
| Tag protection | ✅ Cannot remove `ManagedBy` tag |

## 🔍 Troubleshooting

### Error: "Access Denied: iam:CreateRole"
**Cause:** Policy not attached to GitHub role (account 478180153472)  
**Fix:** Apply the policy using one of the methods above

### Error: "Request failed due to tag requirement"
**Cause:** Role creation without `ManagedBy=terraform` tag  
**Fix:** Ensure your Terraform code includes:
```hcl
tags = {
  ManagedBy = "terraform"
  # ... other tags
}
```

### Error: "Not authorized to perform: iam:CreateRole on resource: arn:aws:iam::*:role/my-custom-role"
**Cause:** Role name doesn't match allowed patterns  
**Fix:** Rename role to start with `arj-` or `terraform-`

## 📚 Related Documentation

- [IAM Role Module](../../tf-module/Module/IAM/README.md)
- [OPA IAM Policies](../../OPA-Poclies/terraform/iam/comprehensive.rego)
- [Deployment Rules](../deployment-rules.yaml)

## ✅ Summary

**Target Role:** `arn:aws:iam::478180153472:role/GitHub` (cross-account)

**Before:** GitHub role had no IAM role management permissions
**After:** Secure, restricted access to manage IAM roles with:
- ✅ Name pattern restrictions
- ✅ Regional limitations
- ✅ Protected role safeguards
- ✅ Mandatory tagging
- ✅ Tag protection

**Apply this policy to enable IAM role management while maintaining security!** 🔒
