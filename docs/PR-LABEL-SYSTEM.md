# GitHub PR Label System

## 🎨 Label Colors & Meanings

The centralized Terraform controller automatically applies colored labels to PRs based on validation results.

---

## ✅ Green Labels (Success - #0E8A16)

### `opa-passed`
- **Color**: 🟢 Green (#0E8A16)
- **Meaning**: OPA validation passed
- **Action**: Deployment approved
- **Auto-applied**: When all OPA policies pass

### `ready-for-review`
- **Color**: 🟢 Green (#0E8A16)
- **Meaning**: PR is ready for team review
- **Action**: Team can review and approve
- **Auto-applied**: When validation passes

### `validated`
- **Color**: 🟢 Green (#0E8A16)
- **Meaning**: Pre-deployment validation completed successfully
- **Action**: All validation checks passed
- **Auto-applied**: When comprehensive validation passes

---

## 🔴 Red Labels (Critical - #B60205)

### `opa-failed`
- **Color**: 🔴 Red (#B60205)
- **Meaning**: OPA validation failed
- **Action**: Must fix policy violations before merge
- **Auto-applied**: When OPA finds violations

### `blocked`
- **Color**: 🔴 Red (#B60205)
- **Meaning**: Deployment is blocked by validation errors
- **Action**: Critical issues must be resolved
- **Auto-applied**: When validation errors are found

---

## 🟠 Orange Labels (Warning - #D93F0B)

### `needs-fixes`
- **Color**: 🟠 Orange (#D93F0B)
- **Meaning**: Issues need to be addressed
- **Action**: Review and fix issues
- **Auto-applied**: When validation fails

### `drift-detected`
- **Color**: 🟠 Orange (#D93F0B)
- **Meaning**: Infrastructure drift detected
- **Action**: Review manual changes outside Terraform
- **Auto-applied**: When drift detection finds changes

---

## 🟡 Yellow Labels (Caution - #FBCA04)

### `production`
- **Color**: 🟡 Yellow (#FBCA04)
- **Meaning**: Production environment deployment
- **Action**: Extra caution required - production changes
- **Auto-applied**: When deploying to production environment

---

## 🔄 Label Workflow

### PR Creation (Validation Phase)
```
1. PR opened → Validation runs
2. ↓
3. All checks passed?
   YES → 🟢 opa-passed, ready-for-review, validated
   NO  → 🔴 opa-failed, needs-fixes, blocked
4. ↓
5. Production deployment?
   YES → 🟡 production (additional label)
```

### Label Examples

#### ✅ Successful Validation
```
Labels:
🟢 opa-passed
🟢 ready-for-review
🟢 validated
```

#### ❌ Failed Validation
```
Labels:
🔴 opa-failed
🔴 blocked
🟠 needs-fixes
```

#### ⚠️ Production Deployment
```
Labels:
🟢 opa-passed
🟢 ready-for-review
🟡 production
```

---

## 📋 Label Definitions (Technical)

| Label | Color Code | Description |
|-------|-----------|-------------|
| `opa-passed` | `#0E8A16` | ✅ OPA validation passed - deployment approved |
| `opa-failed` | `#B60205` | ❌ OPA validation failed - needs fixes |
| `ready-for-review` | `#0E8A16` | ✅ Ready for team review |
| `needs-fixes` | `#D93F0B` | ⚠️ Issues need to be addressed |
| `validated` | `#0E8A16` | ✅ Pre-deployment validation passed |
| `blocked` | `#B60205` | 🚫 Deployment blocked by validation |
| `production` | `#FBCA04` | ⚠️ Production environment deployment |
| `drift-detected` | `#D93F0B` | ⚠️ Infrastructure drift detected |

---

## 🛠️ How Labels Are Applied

Labels are automatically created and applied by the GitHub workflow:

```yaml
# In centralized-controller.yml
- Labels are created with colors if they don't exist
- Labels are updated if colors need to change
- Labels are applied based on validation results
- Production label added for prod environment
```

### Label Creation Code
```javascript
const labelDefinitions = [
  { name: 'opa-passed', color: '0E8A16', description: '✅ OPA validation passed' },
  { name: 'opa-failed', color: 'B60205', description: '❌ OPA validation failed' },
  // ... etc
];
```

---

## 🎯 Quick Reference

**Need to know label status?**

- 🟢 **Green** = Good to go
- 🔴 **Red** = Must fix
- 🟠 **Orange** = Needs attention
- 🟡 **Yellow** = Proceed with caution

**Common label combinations:**

1. **Happy path**: `opa-passed` + `ready-for-review` + `validated`
2. **Needs work**: `opa-failed` + `blocked` + `needs-fixes`
3. **Production**: Any + `production` label

---

## 📚 Related Documentation

- [Workflow Architecture](../WORKFLOW_ARCHITECTURE.md)
- [OPA Validation](../COMPLETE-WORKFLOW-GUIDE.md)
- [Security Features](./SECURITY-FEATURES.md)

---

*🤖 Automated Label Management by Centralized Terraform Controller*
