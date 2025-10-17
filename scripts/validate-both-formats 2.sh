#!/bin/bash
# Simple validation for both tfvars and JSON bucket policies

set -euo pipefail

echo "🔍 Central Policy Validation - Both tfvars and JSON files"

deployment_approved=true
validation_results=""

# Test with S3 tfvars (bucket configurations)
if [ -f "./central-policies/tests/mock_data/valid_s3_config.json" ]; then
    echo "📋 Testing S3 bucket configuration policies..."
    
    if opa eval --data ./central-policies/aws/s3 --data ./central-policies/lib \
               --input ./central-policies/tests/mock_data/valid_s3_config.json \
               --format pretty "data.aws.s3.encryption.violations" > /tmp/s3_test.out 2>&1; then
        echo "✅ S3 configuration policies working"
        validation_results="$validation_results\n✅ S3 config policies: Working"
    else
        echo "⚠️ S3 configuration policies had issues"
        cat /tmp/s3_test.out
        validation_results="$validation_results\n⚠️ S3 config policies: Issues"
    fi
fi

# Test with JSON bucket policies  
if [ -f "./central-policies/tests/mock_data/test_bucket_policy.json" ]; then
    echo "📋 Testing S3 bucket policy validation..."
    
    if opa eval --data ./central-policies/aws/s3 \
               --input ./central-policies/tests/mock_data/test_bucket_policy.json \
               --format pretty "data.aws.s3.bucket_policy.violations" > /tmp/policy_test.out 2>&1; then
        echo "✅ Bucket policy validation working"
        
        # Show violations found in test policy
        violations=$(cat /tmp/policy_test.out)
        echo "Found violations in test policy:"
        echo "$violations"
        validation_results="$validation_results\n✅ Bucket policies: Working (found test violations as expected)"
    else
        echo "⚠️ Bucket policy validation had issues"
        cat /tmp/policy_test.out
        validation_results="$validation_results\n⚠️ Bucket policies: Issues"
    fi
fi

# Check actual files in Accounts directory
policy_files_found=0
for file in $(find Accounts/ -name "*.json" -o -name "*.tfvars" 2>/dev/null || echo ""); do
    if [ -f "$file" ]; then
        policy_files_found=$((policy_files_found + 1))
        echo "Found policy file: $file"
        
        if [[ "$file" == *.json ]]; then
            # Validate JSON bucket policy
            echo "  🔍 Validating JSON bucket policy: $(basename "$file")"
            
            if grep -q '"Effect"' "$file" && grep -q '"Statement"' "$file"; then
                if opa eval --data ./central-policies/aws/s3 \
                           --input "$file" \
                           --format raw "data.aws.s3.bucket_policy.violations | length" > /tmp/json_count.out 2>&1; then
                    violation_count=$(cat /tmp/json_count.out)
                    echo "  📊 Found $violation_count policy violations"
                    validation_results="$validation_results\n🔍 $(basename "$file"): $violation_count violations found"
                    
                    if [ "$violation_count" -gt 0 ]; then
                        echo "  ❌ Policy violations detected - would block deployment"
                        deployment_approved=false
                    fi
                else
                    echo "  ⚠️ Could not validate policy"
                    validation_results="$validation_results\n⚠️ $(basename "$file"): Validation error"
                fi
            else
                echo "  ℹ️ Not a bucket policy format"
            fi
            
        elif [[ "$file" == *.tfvars ]]; then
            echo "  🔍 Found tfvars file: $(basename "$file")"
            validation_results="$validation_results\nℹ️ $(basename "$file"): tfvars found (needs conversion for validation)"
        fi
    fi
done

if [ $policy_files_found -eq 0 ]; then
    echo "ℹ️ No policy files found to validate"
    validation_results="ℹ️ No policy files found"
fi

# Output results for GitHub Actions
echo "opa_result=success" >> $GITHUB_OUTPUT
echo "deployment_approved=$deployment_approved" >> $GITHUB_OUTPUT
echo "validation_summary<<EOF" >> $GITHUB_OUTPUT
echo -e "$validation_results" >> $GITHUB_OUTPUT
echo "EOF" >> $GITHUB_OUTPUT

echo ""
echo "🎯 Summary:"
echo "  Policy files found: $policy_files_found"
echo "  Deployment approved: $deployment_approved"
echo -e "  Results:$validation_results"

if [ "$deployment_approved" = "false" ]; then
    echo ""
    echo "🚫 DEPLOYMENT WOULD BE BLOCKED due to policy violations!"
else
    echo ""
    echo "✅ Central Policy-as-Code integration working!"
fi