## 🔍 Pre-Deployment Validation Report

**Deployment**: `test-syntax-error`  
**Account**: `test-account`  
**Region**: `invalid-region`  
**Status**: ❌ 4 validation error(s) found across 5 checks  
**Duration**: 0.0s  
**Timestamp**: 2025-11-14T00:17:02.569042

### 📋 Validation Details

| Check | Status | Details |
|-------|--------|----------|
| File Structure | ✅ Passed | No issues found |
| Syntax | ❌ Failed | Mismatched braces: 3 opening, 1 closing; Line 10: Possible unterminated string |
| Aws Region | ❌ Failed | Invalid AWS region: invalid-region. Valid regions: af-south-1, ap-east-1, ap-northeast-1, ap-nort... |
| Account Config | ❌ Failed | Invalid region 'invalid-region' in regions list |
| Required Variables | ✅ Passed | Services: s3 |

### ❌ Issues Found

1. Mismatched braces: 3 opening, 1 closing
2. Line 10: Possible unterminated string
3. Invalid AWS region: invalid-region. Valid regions: af-south-1, ap-east-1, ap-northeast-1, ap-northeast-2, ap-south-1, ap-southeast-1, ap-southeast-2, ca-central-1, eu-central-1, eu-north-1, eu-west-1, eu-west-2, eu-west-3, sa-east-1, us-east-1, us-east-2, us-west-1, us-west-2
4. Invalid region 'invalid-region' in regions list

### 💡 Suggested Fixes

- **Region Issues**: Use valid AWS region names (e.g., us-east-1, eu-west-1)

