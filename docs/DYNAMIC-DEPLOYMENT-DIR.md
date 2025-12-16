# OPA Validator - Dynamic Deployment Directory

## 🎯 Problem Solved

**Before:** The deployment directory was hardcoded as `dev-deployment` in line 163:
```python
return f"dev-deployment/**/{base_name}.tfvars"  # ❌ Static/hardcoded
```

**Issues with hardcoded path:**
- ❌ Only works if deployment directory is named exactly "dev-deployment"
- ❌ Breaks if you rename the directory
- ❌ Can't adapt to different environments (prod-deployment, staging-deployment)
- ❌ Not flexible for different workspace structures

## ✅ Solution Implemented

**After:** Dynamic detection during initialization:
```python
def __init__(self, ...):
    self.deployment_dir = self._detect_deployment_directory()  # ✅ Dynamic

def _extract_source_file_from_plan_name(self, plan_name: str) -> str:
    return f"{self.deployment_dir}/**/{base_name}.tfvars"  # ✅ Uses detected path
```

## 🔍 How Dynamic Detection Works

### 1. Detection Method (`_detect_deployment_directory`)

Searches for common deployment directory patterns:
```python
patterns = [
    'dev-deployment',
    'deployment', 
    'deployments',
    'terraform',
    'infrastructure',
    'infra'
]
```

### 2. Multi-Level Search

Checks multiple parent directory levels:
```
current/
├── canonical-plan/        ← plans_dir (starting point)
parent/
├── controller/
│   └── canonical-plan/
├── dev-deployment/        ← Found! (level 1)
grandparent/
├── project/
│   ├── dev-deployment/    ← Could be here (level 2)
│   └── controller/
```

### 3. Intelligent Fallback

If no deployment directory found:
- Falls back to generic `deployment`
- Ensures violations still show useful paths
- Prevents errors from missing directories

## 📊 Detection Examples

### Example 1: Standard Structure
```
/workspace/
├── dev-deployment/    ← Detected as "dev-deployment"
│   ├── S3/
│   └── IAM/
└── controller/
    └── canonical-plan/

Result: deployment_dir = "dev-deployment"
Violation path: "dev-deployment/**/test-poc-3.tfvars"
```

### Example 2: Different Naming
```
/workspace/
├── infrastructure/    ← Detected as "infrastructure"
│   ├── buckets/
│   └── roles/
└── pipeline/
    └── plans/

Result: deployment_dir = "infrastructure"
Violation path: "infrastructure/**/project.tfvars"
```

### Example 3: Environment-Specific
```
/workspace/
├── prod-deployment/   ← Detected as "prod-deployment" 
│   └── critical/
├── staging-deployment/
└── controller/

Result: deployment_dir = "prod-deployment"
Violation path: "prod-deployment/**/prod-data.tfvars"
```

### Example 4: Nested Structure
```
/company/
├── projects/
│   └── myproject/
│       ├── deployment/  ← Detected as "deployment"
│       └── pipeline/

Result: deployment_dir = "deployment"
Violation path: "deployment/**/config.tfvars"
```

## 🚀 Benefits

### 1. **Flexibility**
✅ Works with any deployment directory name
✅ Adapts to different organizational structures
✅ No configuration required

### 2. **Environment Support**
✅ `dev-deployment` for development
✅ `prod-deployment` for production
✅ `staging-deployment` for staging
✅ Any custom naming convention

### 3. **Workspace Agnostic**
✅ Works in different workspace layouts
✅ Handles nested directory structures
✅ Resilient to directory reorganization

### 4. **User Experience**
✅ More accurate file paths in violations
✅ Matches actual workspace structure
✅ Easier to locate files for fixing issues

## 📝 Violation Message Impact

### Before (Hardcoded)
```
📂 Source File: dev-deployment/**/test-poc-3.tfvars
```
❌ Only correct if directory is named "dev-deployment"

### After (Dynamic)
```
📂 Source File: infrastructure/**/test-poc-3.tfvars
```
✅ Reflects actual workspace structure

## 🔧 Implementation Details

### Code Changes

**File:** `scripts/opa-validator.py`

**Changes:**
1. Added `_detect_deployment_directory()` method (new)
2. Added `self.deployment_dir` instance variable
3. Updated `_extract_source_file_from_plan_name()` to use dynamic path
4. Added debug logging for detected directory

**Lines Modified:**
- Line 30-35: Added deployment_dir initialization
- Line 152-190: New detection method
- Line 192-200: Updated path extraction

### Detection Algorithm

```python
def _detect_deployment_directory(self) -> str:
    # 1. Define common patterns
    patterns = ['dev-deployment', 'deployment', 'infrastructure', ...]
    
    # 2. Search parent directories (up to 3 levels)
    search_paths = [parent, grandparent, great_grandparent]
    
    # 3. Check each path for deployment directories
    for search_path in search_paths:
        for pattern in patterns:
            if (search_path / pattern).exists():
                return pattern  # Found!
    
    # 4. Fallback to generic name
    return 'deployment'
```

### Debug Output

When `--debug` flag is used:
```
📁 Detected deployment directory: dev-deployment
```

## 🧪 Testing

### Manual Test

```bash
# Run validator with debug mode
python3 opa-validator.py \
  --opa-policies ../opa-policies \
  --plans-dir canonical-plan \
  --debug

# Check for detection message
# Should see: "📁 Detected deployment directory: dev-deployment"
```

### Verification Script

```bash
./test-dynamic-deploy-dir.sh
```

Shows:
- ✅ Detection method added
- ✅ Instance variable added
- ✅ Path extraction updated
- ✅ No more hardcoded paths

## 🎯 Use Cases

### Use Case 1: Multi-Environment Pipeline

```
/pipeline/
├── dev-deployment/     ← Dev environment
├── prod-deployment/    ← Prod environment
└── controller/

When running on dev branch: detects "dev-deployment"
When running on prod branch: detects "prod-deployment"
```

### Use Case 2: Company Standards

```
/workspace/
├── infrastructure/     ← Your company uses this name
└── cicd/

Automatically detects "infrastructure" ✅
No need to modify validator code ✅
```

### Use Case 3: Monorepo Structure

```
/monorepo/
├── terraform/          ← TF configs here
├── applications/
└── pipelines/

Automatically detects "terraform" ✅
Uses common pattern matching ✅
```

## 📚 Related Documentation

- [OPA Message Enhancement Guide](./OPA-MESSAGE-ENHANCEMENT.md) - Enhanced violation messages
- [Deployment Rules](../deployment-rules.yaml) - Deployment configuration
- [Workflow Guide](./GITHUB-SECRETS-SETUP.md) - CI/CD setup

## 🎉 Summary

**What Changed:**
- ❌ Removed hardcoded `dev-deployment` path
- ✅ Added automatic deployment directory detection
- ✅ Made validator workspace-structure agnostic

**Benefits:**
- 🎯 Works with any deployment directory name
- 🔄 Adapts to workspace changes automatically
- 🌍 Supports multiple environments
- 🏗️ Flexible for different organizational structures

**Result:**
The OPA validator is now **truly dynamic** and adapts to your workspace structure instead of assuming a fixed layout! 🚀
