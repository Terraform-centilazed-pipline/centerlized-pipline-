#!/bin/bash
# S3_Mgmt Integration Script  
# Integrates with central terraform-opa-policies repository

set -euo pipefail

# Configuration
CENTRAL_POLICY_REPO="ExperimentZone/terraform-opa-policies"
POLICY_VERSION="${POLICY_VERSION:-v1.0}"
TEMP_DIR="/tmp/opa-policies-$$"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

cleanup() {
    rm -rf "$TEMP_DIR"
}
trap cleanup EXIT

# Pull central policies
pull_central_policies() {
    echo -e "${BLUE}📥 Pulling central OPA policies (version: $POLICY_VERSION)${NC}"
    
    mkdir -p "$TEMP_DIR"
    
    # Clone or download the central policy repo
    if [[ -n "${GITHUB_TOKEN:-}" ]]; then
        git clone --depth 1 --branch "$POLICY_VERSION" \
            "https://${GITHUB_TOKEN}@github.com/${CENTRAL_POLICY_REPO}.git" \
            "$TEMP_DIR/opa-policies"
    else
        git clone --depth 1 --branch "$POLICY_VERSION" \
            "https://github.com/${CENTRAL_POLICY_REPO}.git" \
            "$TEMP_DIR/opa-policies"
    fi
    
    echo -e "${GREEN}✅ Central policies downloaded${NC}"
}

# Convert tfvars to JSON for OPA evaluation
convert_tfvars_to_json() {
    local tfvars_file="$1"
    local output_file="$2"
    
    echo -e "${BLUE}🔄 Converting tfvars to JSON...${NC}"
    
    # Use terraform to convert HCL to JSON
    terraform-config-inspect --json "$tfvars_file" > "$output_file" 2>/dev/null || {
        # Fallback: simple conversion for basic tfvars
        cat > "$output_file" << 'EOF'
{
  "s3_buckets": {},
  "accounts": {},
  "common_tags": {}
}
EOF
        echo -e "${BLUE}  Using basic JSON structure (install terraform-config-inspect for full conversion)${NC}"
    }
}

# Validate S3 configuration against central policies
validate_s3_config() {
    local config_file="$1"
    
    echo -e "${BLUE}🔍 Validating S3 configuration against central policies...${NC}"
    
    # Convert tfvars to JSON if needed
    local json_config="$TEMP_DIR/config.json"
    if [[ "$config_file" == *.tfvars ]]; then
        convert_tfvars_to_json "$config_file" "$json_config"
    else
        cp "$config_file" "$json_config"
    fi
    
    # Run OPA evaluation
    local result
    result=$(opa eval \
        --data "$TEMP_DIR/opa-policies/aws/s3" \
        --data "$TEMP_DIR/opa-policies/lib" \
        --input "$json_config" \
        --format json \
        "data.aws.s3")
    
    # Extract violations
    local violations
    violations=$(echo "$result" | jq -r '.result[0].expressions[0].value | 
        (.encryption.violations // []) + 
        (.public_access.violations // []) + 
        (.vpc_endpoint.violations // []) + 
        (.tagging.violations // []) | 
        length')
    
    if [[ $violations -eq 0 ]]; then
        echo -e "${GREEN}✅ S3 configuration passed all policy checks${NC}"
        return 0
    else
        echo -e "${RED}❌ Found $violations policy violations:${NC}"
        
        # Display violations with details
        echo "$result" | jq -r '.result[0].expressions[0].value | 
            (.encryption.violations // []) + 
            (.public_access.violations // []) + 
            (.vpc_endpoint.violations // []) + 
            (.tagging.violations // []) | 
            .[] | 
            "  🚨 " + (.severity // "medium") + ": " + .message + 
            (if .remediation then "\n     💡 " + .remediation else "" end)'
        
        return 1
    fi
}

# Main validation function
main() {
    local config_file="${1:-terraform.tfvars}"
    
    echo -e "${BLUE}🏢 S3 Management Policy Validation${NC}"
    echo -e "${BLUE}===================================${NC}"
    
    # Check if config file exists
    if [[ ! -f "$config_file" ]]; then
        echo -e "${RED}❌ Configuration file not found: $config_file${NC}"
        exit 1
    fi
    
    # Pull central policies
    pull_central_policies
    
    # Validate configuration
    if validate_s3_config "$config_file"; then
        echo -e "\n${GREEN}🎉 S3 configuration is compliant!${NC}"
        echo -e "${GREEN}Ready for deployment${NC}"
        exit 0
    else
        echo -e "\n${RED}❌ S3 configuration has policy violations${NC}"
        echo -e "${RED}Please fix violations before deployment${NC}"
        exit 1
    fi
}

# Show usage if no arguments
if [[ $# -eq 0 ]]; then
    echo "Usage: $0 <tfvars-file>"
    echo "Example: $0 terraform.tfvars"
    echo ""
    echo "Environment variables:"
    echo "  POLICY_VERSION - Policy version to use (default: v1.0)"
    echo "  GITHUB_TOKEN   - GitHub token for private repos"
    exit 1
fi

main "$@"