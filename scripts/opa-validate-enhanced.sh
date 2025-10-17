#!/bin/bash
set -euo pipefail

# Strategic OPA Validation Script
# Enhanced with IAM Role Security Validation
# Supports flexible policy levels: strict, standard, flexible

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Configuration
POLICY_DIR="${POLICY_DIR:-./policies}"
OPA_DATA_DIR="${OPA_DATA_DIR:-./policies/levels}"
TERRAFORM_PLAN_FILE="${TERRAFORM_PLAN_FILE:-tfplan.json}"
POLICY_LEVEL="${POLICY_LEVEL:-standard}"
ENVIRONMENT="${ENVIRONMENT:-staging}"
ACCOUNT_ID="${ACCOUNT_ID:-123456789012}"
VALIDATION_OUTPUT="${VALIDATION_OUTPUT:-opa-validation-results.json}"

# Function to print colored output
print_color() {
    local color=$1
    shift
    echo -e "${color}$*${NC}"
}

print_header() {
    print_color $BLUE "╔══════════════════════════════════════════════════════════════╗"
    print_color $BLUE "║               🔒 Strategic OPA Validation                     ║"
    print_color $BLUE "║           S3 Management + IAM Role Security                  ║"
    print_color $BLUE "╚══════════════════════════════════════════════════════════════╝"
}

print_section() {
    print_color $CYAN "\n📋 $1"
    print_color $CYAN "$(printf '%.60s' "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")"
}

# Auto-detect policy level based on environment if not explicitly set
auto_detect_policy_level() {
    case "${ENVIRONMENT,,}" in
        production|prod|prd)
            echo "strict"
            ;;
        staging|stage|stg)
            echo "standard"
            ;;
        development|dev|test|sandbox)
            echo "flexible"
            ;;
        *)
            echo "standard"
            ;;
    esac
}

# Validate prerequisites
validate_prerequisites() {
    print_section "Prerequisites Validation"
    
    # Check if OPA is installed
    if ! command -v opa &> /dev/null; then
        print_color $RED "❌ OPA is not installed. Please install OPA first."
        exit 1
    fi
    print_color $GREEN "✅ OPA found: $(opa version | head -n1)"
    
    # Check if jq is installed
    if ! command -v jq &> /dev/null; then
        print_color $RED "❌ jq is not installed. Please install jq first."
        exit 1
    fi
    print_color $GREEN "✅ jq found: $(jq --version)"
    
    # Check if terraform plan file exists
    if [[ ! -f "$TERRAFORM_PLAN_FILE" ]]; then
        print_color $RED "❌ Terraform plan file not found: $TERRAFORM_PLAN_FILE"
        exit 1
    fi
    print_color $GREEN "✅ Terraform plan file found: $TERRAFORM_PLAN_FILE"
    
    # Check if policy directory exists
    if [[ ! -d "$POLICY_DIR" ]]; then
        print_color $RED "❌ Policy directory not found: $POLICY_DIR"
        exit 1
    fi
    print_color $GREEN "✅ Policy directory found: $POLICY_DIR"
    
    # Check strategic configuration
    local strategic_config="$OPA_DATA_DIR/strategic-config.json"
    if [[ ! -f "$strategic_config" ]]; then
        print_color $RED "❌ Strategic configuration not found: $strategic_config"
        exit 1
    fi
    print_color $GREEN "✅ Strategic configuration found: $strategic_config"
}

# Prepare validation data
prepare_validation_data() {
    print_section "Validation Data Preparation"
    
    # Auto-detect policy level if not explicitly set or set to 'auto'
    if [[ "$POLICY_LEVEL" == "auto" ]]; then
        POLICY_LEVEL=$(auto_detect_policy_level)
        print_color $YELLOW "🔍 Auto-detected policy level: $POLICY_LEVEL (based on environment: $ENVIRONMENT)"
    else
        print_color $BLUE "📊 Using explicit policy level: $POLICY_LEVEL"
    fi
    
    # Create input for OPA with enhanced context
    cat > opa-input.json << EOF
{
    "resource_changes": $(jq '.resource_changes' "$TERRAFORM_PLAN_FILE"),
    "configuration": $(jq '.configuration' "$TERRAFORM_PLAN_FILE" 2>/dev/null || echo 'null'),
    "planned_values": $(jq '.planned_values' "$TERRAFORM_PLAN_FILE" 2>/dev/null || echo 'null'),
    "environment": "$ENVIRONMENT",
    "policy_level": "$POLICY_LEVEL", 
    "terraform_account_id": "$ACCOUNT_ID",
    "validation_timestamp": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
    "validation_context": {
        "terraform_plan_file": "$TERRAFORM_PLAN_FILE",
        "policy_directory": "$POLICY_DIR",
        "strategic_config_dir": "$OPA_DATA_DIR"
    }
}
EOF
    
    print_color $GREEN "✅ Created OPA input file: opa-input.json"
    
    # Display validation context
    print_color $BLUE "🎯 Validation Context:"
    print_color $BLUE "   Environment: $ENVIRONMENT"
    print_color $BLUE "   Policy Level: $POLICY_LEVEL" 
    print_color $BLUE "   Account ID: $ACCOUNT_ID"
    print_color $BLUE "   Resource Changes: $(jq '.resource_changes | length' opa-input.json)"
}

# Run S3 security validation
run_s3_validation() {
    print_section "S3 Security Policy Validation"
    
    if [[ -f "$POLICY_DIR/s3_security.rego" ]]; then
        print_color $BLUE "🪣 Validating S3 security policies..."
        
        opa eval \
            --data "$POLICY_DIR/s3_security.rego" \
            --data "$OPA_DATA_DIR/strategic-config.json" \
            --input opa-input.json \
            --format json \
            "data.terraform.s3_security" > s3-validation-results.json
        
        # Parse results
        local violations=$(jq -r '.result[0].expressions[0].value.violations // []' s3-validation-results.json)
        local violation_count=$(echo "$violations" | jq 'length')
        local enforcement_result=$(jq -r '.result[0].expressions[0].value.enforcement_result // {}' s3-validation-results.json)
        
        print_color $BLUE "📊 S3 Validation Results:"
        print_color $BLUE "   Violations Found: $violation_count"
        echo "$enforcement_result" | jq -r 'to_entries[] | "   \(.key | ascii_upcase): \(.value)"'
        
        if [[ "$violation_count" -gt 0 ]]; then
            print_color $YELLOW "⚠️  S3 Policy Violations:"
            echo "$violations" | jq -r '.[] | "   • \(.)"'
        else
            print_color $GREEN "✅ No S3 policy violations found"
        fi
        
        echo "$violations" | jq '.' > s3-violations.json
    else
        print_color $YELLOW "⚠️  S3 security policy file not found: $POLICY_DIR/s3_security.rego"
        echo "[]" > s3-violations.json
    fi
}

# Run access control validation
run_access_control_validation() {
    print_section "Access Control Policy Validation"
    
    if [[ -f "$POLICY_DIR/access_control.rego" ]]; then
        print_color $BLUE "🔐 Validating access control policies..."
        
        opa eval \
            --data "$POLICY_DIR/access_control.rego" \
            --data "$OPA_DATA_DIR/strategic-config.json" \
            --input opa-input.json \
            --format json \
            "data.terraform.access_control" > access-validation-results.json
        
        # Parse results
        local violations=$(jq -r '.result[0].expressions[0].value.violations // []' access-validation-results.json)
        local violation_count=$(echo "$violations" | jq 'length')
        local enforcement_result=$(jq -r '.result[0].expressions[0].value.enforcement_result // {}' access-validation-results.json)
        
        print_color $BLUE "📊 Access Control Validation Results:"
        print_color $BLUE "   Violations Found: $violation_count"
        echo "$enforcement_result" | jq -r 'to_entries[] | "   \(.key | ascii_upcase): \(.value)"'
        
        if [[ "$violation_count" -gt 0 ]]; then
            print_color $YELLOW "⚠️  Access Control Policy Violations by Category:"
            local categories=$(echo "$enforcement_result" | jq -r '.violations_by_category | to_entries[] | select(.value > 0) | "   🔸 \(.key | ascii_upcase): \(.value) violations"')
            echo "$categories"
            
            print_color $YELLOW "\n📝 Detailed Access Control Violations:"
            echo "$violations" | jq -r '.[] | "   • \(.)"'
        else
            print_color $GREEN "✅ No access control policy violations found"
        fi
        
        echo "$violations" | jq '.' > access-violations.json
    else
        print_color $YELLOW "⚠️  Access control policy file not found: $POLICY_DIR/access_control.rego"
        echo "[]" > access-violations.json
    fi
}

# Run IAM security validation
run_iam_validation() {
    print_section "IAM Role Security Policy Validation"
    
    if [[ -f "$POLICY_DIR/iam_security.rego" ]]; then
        print_color $BLUE "🔑 Validating IAM role security policies..."
        
        opa eval \
            --data "$POLICY_DIR/iam_security.rego" \
            --data "$OPA_DATA_DIR/strategic-config.json" \
            --input opa-input.json \
            --format json \
            "data.terraform.iam_security" > iam-validation-results.json
        
        # Parse results
        local violations=$(jq -r '.result[0].expressions[0].value.violations // []' iam-validation-results.json)
        local violation_count=$(echo "$violations" | jq 'length')
        local enforcement_result=$(jq -r '.result[0].expressions[0].value.enforcement_result // {}' iam-validation-results.json)
        
        print_color $BLUE "📊 IAM Validation Results:"
        print_color $BLUE "   Violations Found: $violation_count"
        echo "$enforcement_result" | jq -r 'to_entries[] | "   \(.key | ascii_upcase): \(.value)"'
        
        if [[ "$violation_count" -gt 0 ]]; then
            print_color $YELLOW "⚠️  IAM Policy Violations by Category:"
            local categories=$(echo "$enforcement_result" | jq -r '.violations_by_category | to_entries[] | select(.value > 0) | "   🔸 \(.key | ascii_upcase): \(.value) violations"')
            echo "$categories"
            
            print_color $YELLOW "\n📝 Detailed IAM Violations:"
            echo "$violations" | jq -r '.[] | "   • \(.)"'
        else
            print_color $GREEN "✅ No IAM policy violations found"
        fi
        
        echo "$violations" | jq '.' > iam-violations.json
    else
        print_color $YELLOW "⚠️  IAM security policy file not found: $POLICY_DIR/iam_security.rego"
        echo "[]" > iam-violations.json
    fi
}

# Aggregate results and make enforcement decision
aggregate_results() {
    print_section "Strategic Enforcement Decision"
    
    local s3_violations=0
    local iam_violations=0
    local access_violations=0
    local total_violations=0
    
    # Count S3 violations
    if [[ -f "s3-violations.json" ]]; then
        s3_violations=$(jq 'length' s3-violations.json)
    fi
    
    # Count IAM violations
    if [[ -f "iam-violations.json" ]]; then
        iam_violations=$(jq 'length' iam-violations.json)
    fi
    
    # Count Access Control violations  
    if [[ -f "access-violations.json" ]]; then
        access_violations=$(jq 'length' access-violations.json)
    fi
    
    total_violations=$((s3_violations + iam_violations + access_violations))
    
    # Get strategic configuration for current policy level
    local strategic_config=$(jq --arg level "$POLICY_LEVEL" '.policy_levels[$level]' "$OPA_DATA_DIR/strategic-config.json")
    local enforcement_mode=$(echo "$strategic_config" | jq -r '.enforcement')
    local allowed_violations=$(echo "$strategic_config" | jq -r '.allowed_violations')
    local policy_description=$(echo "$strategic_config" | jq -r '.description')
    
    # Create aggregated results
    cat > "$VALIDATION_OUTPUT" << EOF
{
    "validation_summary": {
        "environment": "$ENVIRONMENT",
        "policy_level": "$POLICY_LEVEL",
        "policy_description": "$policy_description",
        "enforcement_mode": "$enforcement_mode",
        "allowed_violations": $allowed_violations,
        "total_violations": $total_violations,
        "violations_by_category": {
            "s3_security": $s3_violations,
            "iam_security": $iam_violations,
            "access_control": $access_violations
        }
    },
    "enforcement_decision": {
        "should_block_deployment": $([ "$enforcement_mode" = "hard_fail" ] && [ "$total_violations" -gt 0 ] && echo true || echo false),
        "has_warnings": $([ "$total_violations" -gt 0 ] && echo true || echo false),
        "exceeds_violation_threshold": $([ "$total_violations" -gt "$allowed_violations" ] && echo true || echo false)
    },
    "validation_timestamp": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
}
EOF
    
    # Display results
    print_color $BLUE "🎯 Strategic Enforcement Summary:"
    print_color $BLUE "   Policy Level: $POLICY_LEVEL ($policy_description)"
    print_color $BLUE "   Enforcement Mode: $enforcement_mode"
    print_color $BLUE "   Total Violations: $total_violations"
    print_color $BLUE "   Allowed Violations: $allowed_violations"
    print_color $BLUE "   S3 Violations: $s3_violations"
    print_color $BLUE "   IAM Violations: $iam_violations"
    print_color $BLUE "   Access Control Violations: $access_violations"
    
    # Enforcement decision logic
    case "$enforcement_mode" in
        "hard_fail")
            if [[ "$total_violations" -gt 0 ]]; then
                print_color $RED "❌ DEPLOYMENT BLOCKED: Hard fail mode with violations detected"
                return 1
            else
                print_color $GREEN "✅ DEPLOYMENT APPROVED: No violations in hard fail mode"
                return 0
            fi
            ;;
        "soft_fail_with_warnings")
            if [[ "$total_violations" -gt "$allowed_violations" ]]; then
                print_color $RED "❌ DEPLOYMENT BLOCKED: Violations ($total_violations) exceed threshold ($allowed_violations)"
                return 1
            else
                if [[ "$total_violations" -gt 0 ]]; then
                    print_color $YELLOW "⚠️  DEPLOYMENT APPROVED WITH WARNINGS: $total_violations violations within threshold"
                else
                    print_color $GREEN "✅ DEPLOYMENT APPROVED: No violations detected"
                fi
                return 0
            fi
            ;;
        "warn_only")
            if [[ "$total_violations" -gt 0 ]]; then
                print_color $YELLOW "⚠️  DEPLOYMENT APPROVED: $total_violations warnings in warn-only mode"
            else
                print_color $GREEN "✅ DEPLOYMENT APPROVED: No warnings"
            fi
            return 0
            ;;
    esac
}

# Cleanup temporary files
cleanup() {
    print_section "Cleanup"
    
    local temp_files=("opa-input.json" "s3-validation-results.json" "iam-validation-results.json" "access-validation-results.json" "s3-violations.json" "iam-violations.json" "access-violations.json")
    
    for file in "${temp_files[@]}"; do
        if [[ -f "$file" ]]; then
            rm "$file"
            print_color $GREEN "🗑️  Removed temporary file: $file"
        fi
    done
}

# Display help
show_help() {
    cat << EOF
Strategic OPA Validation Script - Enhanced with IAM Role Security

Usage: $0 [OPTIONS]

Environment Variables:
    POLICY_DIR              Directory containing OPA policies (default: ./policies)
    OPA_DATA_DIR           Directory containing strategic configuration (default: ./policies/levels)
    TERRAFORM_PLAN_FILE    Path to terraform plan JSON file (default: tfplan.json)
    POLICY_LEVEL           Policy enforcement level: strict|standard|flexible|auto (default: standard)
    ENVIRONMENT            Target environment for deployment (default: staging)
    ACCOUNT_ID             AWS Account ID for validation (default: 123456789012)
    VALIDATION_OUTPUT      Output file for validation results (default: opa-validation-results.json)

Policy Levels:
    strict      Maximum security - Production environments (hard_fail)
    standard    Balanced approach - Staging environments (soft_fail_with_warnings)
    flexible    Development friendly - Dev/Test environments (warn_only)
    auto        Auto-detect based on ENVIRONMENT variable

Options:
    -h, --help             Show this help message
    --cleanup-only         Only perform cleanup of temporary files
    --check-setup          Only validate prerequisites without running validation
    
Examples:
    # Basic validation with auto-detected policy level
    ENVIRONMENT=production POLICY_LEVEL=auto $0
    
    # Staging validation with specific policy level
    ENVIRONMENT=staging POLICY_LEVEL=standard $0
    
    # Development validation with custom account
    ENVIRONMENT=development ACCOUNT_ID=999999999999 $0

Supported Validations:
    🪣 S3 Security: Bucket encryption, public access, lifecycle policies, naming conventions
    🔑 IAM Security: Role policies, assume role validation, naming conventions, session duration
    � Access Control: Cross-account access, least privilege, service integration patterns
    �📊 Strategic Levels: Environment-based enforcement with violation thresholds
    🔒 Cross-Account: Validation of cross-account access and trust relationships
    🏷️  Tagging: Required tags enforcement for compliance
EOF
}

# Main execution
main() {
    # Handle command line arguments
    case "${1:-}" in
        -h|--help)
            show_help
            exit 0
            ;;
        --cleanup-only)
            cleanup
            exit 0
            ;;
        --check-setup)
            print_header
            validate_prerequisites
            exit 0
            ;;
    esac
    
    # Main validation flow
    print_header
    
    validate_prerequisites
    prepare_validation_data
    run_s3_validation
    run_access_control_validation
    run_iam_validation
    
    # Aggregate and enforce
    if aggregate_results; then
        print_color $GREEN "\n🎉 Strategic OPA validation completed successfully!"
        cleanup
        exit 0
    else
        print_color $RED "\n🚫 Strategic OPA validation failed - deployment blocked"
        cleanup
        exit 1
    fi
}

# Execute main function with all arguments
main "$@"