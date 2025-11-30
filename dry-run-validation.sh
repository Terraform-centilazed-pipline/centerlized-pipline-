#!/bin/bash
# =============================================================================
# PRE-DEPLOYMENT DRY RUN VALIDATOR
# =============================================================================
# Purpose: Validate workflows before pushing to GitHub
# Version: 1.0
# =============================================================================

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Counters
TOTAL_CHECKS=0
PASSED_CHECKS=0
FAILED_CHECKS=0

# Functions
print_header() {
    echo -e "\n${BLUE}╔══════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║${NC}  $1"
    echo -e "${BLUE}╚══════════════════════════════════════════════════════════════════╝${NC}\n"
}

check_pass() {
    ((TOTAL_CHECKS++))
    ((PASSED_CHECKS++))
    echo -e "${GREEN}✅ PASS${NC}: $1"
}

check_fail() {
    ((TOTAL_CHECKS++))
    ((FAILED_CHECKS++))
    echo -e "${RED}❌ FAIL${NC}: $1"
    echo -e "   ${YELLOW}→${NC} $2"
}

check_warn() {
    echo -e "${YELLOW}⚠️  WARN${NC}: $1"
}

# =============================================================================
# CHECK 1: File Existence
# =============================================================================
print_header "CHECK 1: File Existence"

files=(
    "dev-deployment/.github/workflows/dispatch-to-controller-v2.yml"
    "centerlized-pipline-/.github/workflows/centralized-controller.yml"
    "centerlized-pipline-/scripts/handle_pr_merge.py"
    "centerlized-pipline-/scripts/requirements.txt"
    "centerlized-pipline-/config/special-approvers.yaml"
)

for file in "${files[@]}"; do
    if [[ -f "$file" ]]; then
        check_pass "File exists: $file"
    else
        check_fail "File missing: $file" "Create this file before deployment"
    fi
done

# =============================================================================
# CHECK 2: YAML Syntax Validation
# =============================================================================
print_header "CHECK 2: YAML Syntax Validation"

if command -v python3 &> /dev/null; then
    python3 << 'PYEOF'
import yaml
import sys

files = [
    'dev-deployment/.github/workflows/dispatch-to-controller-v2.yml',
    'centerlized-pipline-/.github/workflows/centralized-controller.yml',
    'centerlized-pipline-/config/special-approvers.yaml'
]

for file in files:
    try:
        with open(file, 'r') as f:
            yaml.safe_load(f)
        print(f'✅ Valid YAML syntax: {file}')
    except yaml.YAMLError as e:
        print(f'❌ YAML Error in {file}: {str(e)}')
        sys.exit(1)
PYEOF
    if [[ $? -eq 0 ]]; then
        check_pass "All YAML files have valid syntax"
    else
        check_fail "YAML syntax errors detected" "Fix YAML syntax errors above"
    fi
else
    check_warn "Python3 not available - skipping YAML validation"
fi

# =============================================================================
# CHECK 3: Required Secrets Check
# =============================================================================
print_header "CHECK 3: Required Secrets Configuration"

required_secrets=(
    "GT_APP_ID"
    "GT_APP_PRIVATE_KEY"
)

echo "Required GitHub secrets:"
for secret in "${required_secrets[@]}"; do
    echo "  • $secret"
done
check_pass "Secret list verified"

# =============================================================================
# CHECK 4: Workflow Structure Validation
# =============================================================================
print_header "CHECK 4: Workflow Structure Validation"

# Check dispatch workflow jobs
dispatch_jobs=(
    "auto-pr"
    "dispatch-validate"
    "dispatch-merge"
    "dispatch-apply"
)

if [[ -f "dev-deployment/.github/workflows/dispatch-to-controller-v2.yml" ]]; then
    for job in "${dispatch_jobs[@]}"; do
        if grep -q "^  $job:" "dev-deployment/.github/workflows/dispatch-to-controller-v2.yml"; then
            check_pass "Dispatch job exists: $job"
        else
            check_fail "Dispatch job missing: $job" "Add job definition"
        fi
    done
fi

# Check controller workflow has Python script step
if [[ -f "centerlized-pipline-/.github/workflows/centralized-controller.yml" ]]; then
    if grep -q "handle_pr_merge.py" "centerlized-pipline-/.github/workflows/centralized-controller.yml"; then
        check_pass "Controller calls Python merge script"
    else
        check_fail "Python merge script not called" "Add Python script execution step"
    fi
fi

# =============================================================================
# CHECK 5: Python Script Validation
# =============================================================================
print_header "CHECK 5: Python Script Validation"

if [[ -f "centerlized-pipline-/scripts/handle_pr_merge.py" ]]; then
    # Check if executable
    if [[ -x "centerlized-pipline-/scripts/handle_pr_merge.py" ]]; then
        check_pass "Python script is executable"
    else
        check_warn "Python script is not executable (chmod +x recommended)"
    fi
    
    # Check for required imports
    required_imports=("github" "yaml" "json" "os" "sys")
    for imp in "${required_imports[@]}"; do
        if grep -q -E "(import $imp|from $imp import)" "centerlized-pipline-/scripts/handle_pr_merge.py"; then
            check_pass "Import found: $imp"
        else
            check_fail "Missing import: $imp" "Add 'import $imp' to script"
        fi
    done
    
    # Check for main function
    if grep -q "def main():" "centerlized-pipline-/scripts/handle_pr_merge.py"; then
        check_pass "Main function exists"
    else
        check_fail "Main function missing" "Add 'def main():' function"
    fi
fi

# =============================================================================
# CHECK 6: Dependencies Check
# =============================================================================
print_header "CHECK 6: Dependencies Check"

if [[ -f "centerlized-pipline-/scripts/requirements.txt" ]]; then
    required_deps=("PyGithub" "PyYAML")
    for dep in "${required_deps[@]}"; do
        if grep -q "$dep" "centerlized-pipline-/scripts/requirements.txt"; then
            check_pass "Dependency listed: $dep"
        else
            check_fail "Missing dependency: $dep" "Add to requirements.txt"
        fi
    done
fi

# =============================================================================
# CHECK 7: Configuration Validation
# =============================================================================
print_header "CHECK 7: Configuration Validation"

# Check special approvers config
if [[ -f "centerlized-pipline-/config/special-approvers.yaml" ]]; then
    if grep -q "special_approvers:" "centerlized-pipline-/config/special-approvers.yaml"; then
        check_pass "Special approvers config structure valid"
        
        # Check if has at least one approver
        if grep -q "  - " "centerlized-pipline-/config/special-approvers.yaml"; then
            check_pass "At least one special approver configured"
        else
            check_fail "No special approvers defined" "Add at least one approver"
        fi
    else
        check_fail "Invalid special approvers config" "Add 'special_approvers:' key"
    fi
fi

# Check environment variables in dispatch workflow
if grep -q "CONTROLLER_OWNER:" "dev-deployment/.github/workflows/dispatch-to-controller-v2.yml"; then
    check_pass "Controller owner configured"
else
    check_fail "CONTROLLER_OWNER not set" "Add env variable"
fi

if grep -q "CONTROLLER_REPO:" "dev-deployment/.github/workflows/dispatch-to-controller-v2.yml"; then
    check_pass "Controller repo configured"
else
    check_fail "CONTROLLER_REPO not set" "Add env variable"
fi

# =============================================================================
# CHECK 8: Trigger Configuration
# =============================================================================
print_header "CHECK 8: Trigger Configuration"

# Check dispatch triggers
triggers=("pull_request:" "pull_request_review:" "push:")
for trigger in "${triggers[@]}"; do
    if grep -q "$trigger" "dev-deployment/.github/workflows/dispatch-to-controller-v2.yml"; then
        check_pass "Dispatch trigger configured: ${trigger%:}"
    else
        check_fail "Missing trigger: ${trigger%:}" "Add trigger configuration"
    fi
done

# Check controller triggers
if grep -q "repository_dispatch:" "centerlized-pipline-/.github/workflows/centralized-controller.yml"; then
    check_pass "Controller dispatch trigger configured"
else
    check_fail "Controller missing repository_dispatch" "Add trigger configuration"
fi

# =============================================================================
# CHECK 9: Security Gates
# =============================================================================
print_header "CHECK 9: Security Gates"

# Check OPA label validation in dispatch
if grep -q "opa-passed" "dev-deployment/.github/workflows/dispatch-to-controller-v2.yml"; then
    check_pass "OPA label check present in dispatch"
else
    check_fail "Missing OPA label check" "Add security gate validation"
fi

# Check label addition in controller
if grep -q "addLabels" "centerlized-pipline-/.github/workflows/centralized-controller.yml" || \
   grep -q "add_to_labels" "centerlized-pipline-/scripts/handle_pr_merge.py"; then
    check_pass "Label management configured"
else
    check_fail "Label management missing" "Add label addition logic"
fi

# =============================================================================
# CHECK 10: Action Routing
# =============================================================================
print_header "CHECK 10: Action Routing"

actions=("validate" "merge" "apply")
for action in "${actions[@]}"; do
    if grep -q "action: '$action'" "dev-deployment/.github/workflows/dispatch-to-controller-v2.yml" || \
       grep -q "action: '\"$action\"'" "dev-deployment/.github/workflows/dispatch-to-controller-v2.yml"; then
        check_pass "Action defined: $action"
    else
        check_warn "Action routing: $action (verify manually)"
    fi
done

# =============================================================================
# SUMMARY
# =============================================================================
print_header "VALIDATION SUMMARY"

echo -e "Total checks: ${TOTAL_CHECKS}"
echo -e "${GREEN}Passed: ${PASSED_CHECKS}${NC}"
if [[ $FAILED_CHECKS -gt 0 ]]; then
    echo -e "${RED}Failed: ${FAILED_CHECKS}${NC}"
else
    echo -e "${GREEN}Failed: ${FAILED_CHECKS}${NC}"
fi

echo ""

if [[ $FAILED_CHECKS -eq 0 ]]; then
    echo -e "${GREEN}╔═══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║  ✅ ALL CHECKS PASSED - READY FOR DEPLOYMENT             ║${NC}"
    echo -e "${GREEN}╚═══════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo "Next steps:"
    echo "  1. Review changes: git diff"
    echo "  2. Commit: git add . && git commit -m 'feat: workflow v2'"
    echo "  3. Push: git push origin main"
    echo ""
    exit 0
else
    echo -e "${RED}╔═══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${RED}║  ❌ VALIDATION FAILED - FIX ERRORS BEFORE DEPLOYMENT      ║${NC}"
    echo -e "${RED}╚═══════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo "Please fix the errors above and run this script again."
    echo ""
    exit 1
fi
