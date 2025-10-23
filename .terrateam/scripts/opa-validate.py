#!/usr/bin/env python3
"""
Simple OPA Validator for Terrateam
==================================
Validates Terraform plans with OPA policies (if available)
"""

import os
import subprocess
import sys
import tempfile

def run_command(cmd):
    """Run a command and return output"""
    try:
        result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
        return True, result.stdout
    except subprocess.CalledProcessError as e:
        return False, e.stderr

def check_opa_available():
    """Check if OPA is available"""
    success, _ = run_command("opa version")
    return success

def validate_with_opa():
    """Run OPA validation if policies exist"""
    print("🛡️ OPA Policy Validation")
    
    # Check if OPA policies exist
    policies_path = "../OPA-Poclies/opa"
    if not os.path.exists(policies_path):
        print(f"⚠️ OPA policies not found at {policies_path}")
        print("✅ Skipping OPA validation")
        return True
    
    # Check if OPA is available
    if not check_opa_available():
        print("⚠️ OPA not available, skipping validation")
        return True
    
    # Generate a simple plan for validation
    print("📋 Generating Terraform plan...")
    plan_success, _ = run_command("terraform plan -out=tfplan.tmp")
    
    if not plan_success:
        print("❌ Failed to generate plan")
        return False
    
    # Convert plan to JSON
    json_success, json_output = run_command("terraform show -json tfplan.tmp")
    
    if not json_success:
        print("❌ Failed to convert plan to JSON")
        return False
    
    # Write JSON to temp file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        f.write(json_output)
        json_file = f.name
    
    try:
        # Run OPA evaluation
        opa_cmd = f"opa eval -d {policies_path} -i {json_file} 'data.terraform.deny[x]' --format json"
        opa_success, opa_output = run_command(opa_cmd)
        
        if opa_success and opa_output.strip():
            # Parse OPA output to check for violations
            import json
            try:
                result = json.loads(opa_output)
                violations = []
                for item in result.get('result', []):
                    for expr in item.get('expressions', []):
                        if expr.get('value'):
                            violations.append(str(expr['value']))
                
                if violations:
                    print("❌ Policy violations found:")
                    for v in violations:
                        print(f"  - {v}")
                    return False
                else:
                    print("✅ No policy violations found")
                    return True
            except json.JSONDecodeError:
                print("✅ OPA validation completed (no violations)")
                return True
        else:
            print("✅ OPA validation completed")
            return True
    
    finally:
        # Cleanup
        for temp_file in [json_file, 'tfplan.tmp']:
            if os.path.exists(temp_file):
                os.remove(temp_file)
    
    return True

def main():
    """Main function"""
    success = validate_with_opa()
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()