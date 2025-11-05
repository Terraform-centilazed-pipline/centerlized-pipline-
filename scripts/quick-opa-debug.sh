# Quick OPA Debug Commands
# Run these in your centralized controller workflow directory

# 1. Check if plan has resources
echo "=== Plan Resource Check ==="
jq '.resource_changes | length' canonical-plan/plan.json
jq '.resource_changes[]?.type' canonical-plan/plan.json | sort | uniq -c

# 2. Test OPA policy loading
echo "=== OPA Policy Test ==="
opa eval -d ../opa-policies/terraform/ "data.terraform.main.has_s3_resources" -i canonical-plan/plan.json

# 3. Test service detection directly
echo "=== Service Detection Test ==="
opa eval -d ../opa-policies/terraform/ "data.terraform.main.services_detected" -i canonical-plan/plan.json --format json

# 4. Check for specific resource types
echo "=== Resource Types ==="
jq '.resource_changes[]? | select(.type | startswith("aws_s3")) | .type' canonical-plan/plan.json

# 5. Full deployment summary
echo "=== Deployment Summary ==="
opa eval -d ../opa-policies/terraform/ "data.terraform.main.deployment_summary" -i canonical-plan/plan.json --format pretty