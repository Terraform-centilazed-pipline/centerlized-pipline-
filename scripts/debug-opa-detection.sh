#!/bin/bash
# OPA Service Detection Debugger
# This script helps debug why OPA is not detecting services in terraform plans

echo "🔍 OPA Service Detection Debugger"
echo "=================================="

# Check if required files exist
if [ ! -f "canonical-plan/plan.json" ] && [ ! -f "plan.json" ]; then
    echo "❌ No plan.json found. Looking for any JSON files..."
    find . -name "*.json" -type f | head -5
    echo ""
    echo "Please ensure you have a terraform plan JSON file"
    exit 1
fi

# Use the plan file that exists
PLAN_FILE=""
if [ -f "canonical-plan/plan.json" ]; then
    PLAN_FILE="canonical-plan/plan.json"
elif [ -f "plan.json" ]; then
    PLAN_FILE="plan.json"
else
    PLAN_FILE=$(find . -name "*.json" -type f | head -1)
fi

echo "📋 Using plan file: $PLAN_FILE"
echo ""

# Check OPA policies directory
if [ ! -d "../opa-policies/terraform" ] && [ ! -d "opa-policies/terraform" ] && [ ! -d "../OPA-Poclies/terraform" ]; then
    echo "❌ OPA policies directory not found. Checking available directories..."
    find .. -name "terraform" -type d | grep -i opa | head -3
    echo ""
    echo "Please ensure OPA policies are available"
    exit 1
fi

# Find the OPA policies directory
OPA_DIR=""
if [ -d "../opa-policies/terraform" ]; then
    OPA_DIR="../opa-policies/terraform"
elif [ -d "opa-policies/terraform" ]; then
    OPA_DIR="opa-policies/terraform"
elif [ -d "../OPA-Poclies/terraform" ]; then
    OPA_DIR="../OPA-Poclies/terraform"
fi

echo "📁 Using OPA policies from: $OPA_DIR"
echo ""

# Basic plan analysis
echo "🧭 Basic Plan Analysis:"
echo "----------------------"
file_size=$(wc -c < "$PLAN_FILE")
echo "   File size: $file_size bytes"

if [ "$file_size" -lt 100 ]; then
    echo "⚠️  Plan file seems too small, might be empty or invalid"
fi

# Check if plan has required structure
has_resource_changes=$(jq -r 'has("resource_changes")' "$PLAN_FILE" 2>/dev/null)
resource_count=$(jq -r '.resource_changes | length' "$PLAN_FILE" 2>/dev/null || echo "0")
echo "   Has resource_changes: $has_resource_changes"
echo "   Resource changes count: $resource_count"

if [ "$resource_count" = "0" ]; then
    echo "⚠️  No resource changes found in plan"
    echo ""
    echo "📋 Plan structure:"
    jq -r 'keys[]' "$PLAN_FILE" 2>/dev/null || echo "Invalid JSON"
    echo ""
fi

# Show sample resources
echo ""
echo "🔍 Sample Resources in Plan:"
echo "----------------------------"
jq -r '.resource_changes[]? | "\(.type) - \(.change.actions[]?)"' "$PLAN_FILE" 2>/dev/null | head -10

echo ""
echo "📦 Resource Types Summary:"
echo "-------------------------"
jq -r '.resource_changes[]?.type' "$PLAN_FILE" 2>/dev/null | sort | uniq -c | sort -nr

echo ""
echo "🛡️  OPA Service Detection Test:"
echo "==============================="

# Test OPA evaluation step by step
echo "1. Testing OPA binary..."
if ! command -v opa &> /dev/null; then
    echo "❌ OPA binary not found. Please install OPA first."
    exit 1
else
    echo "✅ OPA binary found: $(which opa)"
    opa version
fi

echo ""
echo "2. Testing policy loading..."
if ! opa eval -d "$OPA_DIR" "data.terraform.main" > /dev/null 2>&1; then
    echo "❌ Failed to load OPA policies from $OPA_DIR"
    echo "   Available policy files:"
    find "$OPA_DIR" -name "*.rego" | head -5
    exit 1
else
    echo "✅ OPA policies loaded successfully"
fi

echo ""
echo "3. Testing resource detection..."

# Test each service detection
services=("S3" "IAM" "KMS" "Lambda" "VPC" "EC2" "RDS")
service_functions=("has_s3_resources" "has_iam_resources" "has_kms_resources" "has_lambda_resources" "has_vpc_resources" "has_ec2_resources" "has_rds_resources")

for i in "${!services[@]}"; do
    service="${services[$i]}"
    function="${service_functions[$i]}"
    
    result=$(opa eval -d "$OPA_DIR" -i "$PLAN_FILE" "data.terraform.main.$function" --format json 2>/dev/null | jq -r '.result[0].expressions[0].value // false')
    
    if [ "$result" = "true" ]; then
        echo "✅ $service resources detected"
    else
        echo "❌ $service resources NOT detected"
    fi
done

echo ""
echo "4. Testing deployment summary..."
services_detected=$(opa eval -d "$OPA_DIR" -i "$PLAN_FILE" "data.terraform.main.deployment_summary.services_detected" --format json 2>/dev/null | jq -r '.result[0].expressions[0].value[]?' 2>/dev/null | tr '\n' ',' | sed 's/,$//')

if [ -n "$services_detected" ]; then
    echo "✅ Services detected: $services_detected"
else
    echo "❌ No services detected in deployment summary"
    
    # Debug why no services detected
    echo ""
    echo "🔍 Debug Info:"
    echo "-------------"
    
    # Check if main.rego exists and has the right structure
    if [ -f "$OPA_DIR/main.rego" ]; then
        echo "✅ main.rego exists"
        
        # Check if service detection functions exist
        if grep -q "has_s3_resources" "$OPA_DIR/main.rego"; then
            echo "✅ Service detection functions found in main.rego"
        else
            echo "❌ Service detection functions missing in main.rego"
        fi
        
        # Check if services_detected is defined
        if grep -q "services_detected" "$OPA_DIR/main.rego"; then
            echo "✅ services_detected rule found in main.rego"
        else
            echo "❌ services_detected rule missing in main.rego"
        fi
    else
        echo "❌ main.rego not found in $OPA_DIR"
        echo "   Available files:"
        ls -la "$OPA_DIR/"
    fi
fi

echo ""
echo "5. Testing violation detection..."
violations=$(opa eval -d "$OPA_DIR" -i "$PLAN_FILE" "data.terraform.main.deny" --format json 2>/dev/null | jq -r '.result[0].expressions[0].value // {}' | jq 'keys | length' 2>/dev/null || echo "0")

echo "   Violations found: $violations"

echo ""
echo "📋 Complete Deployment Summary:"
echo "==============================="
opa eval -d "$OPA_DIR" -i "$PLAN_FILE" "data.terraform.main.deployment_summary" --format pretty 2>/dev/null || echo "Failed to get deployment summary"

echo ""
echo "🎯 Debugging Complete!"
echo "====================="

if [ -n "$services_detected" ]; then
    echo "✅ OPA service detection is working correctly"
else
    echo "❌ OPA service detection has issues. Check the debug info above."
    echo ""
    echo "Common issues:"
    echo "1. Plan file has no resource_changes"
    echo "2. Resource types don't match OPA detection patterns"
    echo "3. OPA policies not loaded correctly"
    echo "4. main.rego missing or has syntax errors"
fi