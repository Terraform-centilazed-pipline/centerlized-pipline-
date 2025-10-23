#!/bin/bash
# scripts/opa-validate.sh
# Basic OPA validation for Terrateam

set -e

echo "🔍 Running OPA Policy Validation..."

# Check if terraform plan file exists
if [ ! -f "tfplan.binary" ]; then
    echo "📋 Generating Terraform plan..."
    terraform plan -out=tfplan.binary
fi

# Convert plan to JSON for OPA
echo "📄 Converting plan to JSON..."
terraform show -json tfplan.binary > tfplan.json

# Set OPA policies path
OPA_POLICIES_PATH="${OPA_POLICIES_PATH:-../OPA-Poclies/opa}"

# Run OPA validation if policies exist
if [ -d "$OPA_POLICIES_PATH" ]; then
    echo "🛡️ Running OPA security policies..."
    
    # Install OPA if not available
    if ! command -v opa &> /dev/null; then
        echo "📥 Installing OPA..."
        curl -L -o opa https://openpolicyagent.org/downloads/v0.57.0/opa_linux_amd64_static
        chmod +x opa
        sudo mv opa /usr/local/bin/
    fi
    
    # Run OPA evaluation
    violations=$(opa eval -d "$OPA_POLICIES_PATH" -i tfplan.json "data.terraform.deny[x]" --format json | jq '. | length')
    
    if [ "$violations" -gt 0 ]; then
        echo "❌ OPA Policy violations found!"
        opa eval -d "$OPA_POLICIES_PATH" -i tfplan.json "data.terraform.deny[x]" --format pretty
        exit 1
    else
        echo "✅ All OPA policies passed!"
    fi
else
    echo "⚠️ OPA policies directory not found: $OPA_POLICIES_PATH"
    echo "Skipping OPA validation"
fi

# Cleanup
rm -f tfplan.binary tfplan.json

echo "✅ OPA validation completed!"