#!/usr/bin/env python3
"""
Generate detailed policy violation reports from OPA validation results.
"""

import json
import os
import sys
import glob
from pathlib import Path

def generate_detailed_report(validation_results_dir, output_file):
    """Generate a detailed violation report from OPA validation results."""
    
    # Initialize report
    report_lines = []
    
    # Find all validation result files
    result_files = glob.glob(os.path.join(validation_results_dir, "result-*.json"))
    
    if not result_files:
        report_lines.append("⚠️ No detailed validation results found")
        with open(output_file, 'w') as f:
            f.write('\n'.join(report_lines))
        return 0
    
    report_lines.append("## 🚫 Detailed Policy Violations")
    report_lines.append("")
    
    total_violations = 0
    
    for result_file in sorted(result_files):
        try:
            # Extract plan name from filename
            plan_name = os.path.basename(result_file).replace("result-", "").replace(".json", "")
            
            with open(result_file, 'r') as f:
                result_data = json.load(f)
            
            # Extract violations from OPA result
            violations_obj = result_data.get('result', [{}])[0].get('expressions', [{}])[0].get('value', {})
            
            if not violations_obj or violations_obj == {}:
                continue
                
            report_lines.append(f"### 📋 Terraform Plan: {plan_name}")
            report_lines.append("")
            
            # Parse violations (OPA returns violations as object keys)
            violation_count = 0
            for violation_key in violations_obj.keys():
                try:
                    # Each key is a JSON string representing a violation
                    violation = json.loads(violation_key)
                    violation_count += 1
                    total_violations += 1
                    
                    severity = violation.get('severity', 'unknown').upper()
                    policy = violation.get('policy', 'unknown')
                    resource = violation.get('resource', 'unknown')
                    message = violation.get('message', 'No message provided')
                    remediation = violation.get('remediation', 'No remediation guidance provided')
                    security_risk = violation.get('security_risk', 'Risk not specified')
                    
                    # Format violation details
                    report_lines.append(f"#### 🚨 {severity} Violation #{violation_count}")
                    report_lines.append(f"- **Policy**: `{policy}`")
                    report_lines.append(f"- **Resource**: `{resource}`")
                    report_lines.append(f"- **Issue**: {message}")
                    report_lines.append(f"- **Security Risk**: {security_risk}")
                    report_lines.append(f"- **Remediation**: {remediation}")
                    report_lines.append("")
                    
                except json.JSONDecodeError:
                    # If violation key is not valid JSON, skip it
                    continue
            
            if violation_count == 0:
                report_lines.append("✅ No violations found in this terraform plan")
                report_lines.append("")
                
        except Exception as e:
            print(f"⚠️ Error processing {result_file}: {e}", file=sys.stderr)
            continue
    
    if total_violations == 0:
        report_lines = ["## ✅ No Policy Violations Found", "", "All terraform configurations passed security validation."]
    else:
        report_lines.insert(2, f"**Total Violations Found**: {total_violations}")
        report_lines.insert(3, "")
    
    # Write report to file
    with open(output_file, 'w') as f:
        f.write('\n'.join(report_lines))
    
    print(f"✅ Generated detailed report with {total_violations} violations")
    return total_violations

def main():
    if len(sys.argv) != 3:
        print("Usage: python3 generate-detailed-report.py <validation-results-dir> <output-file>")
        sys.exit(1)
    
    validation_results_dir = sys.argv[1]
    output_file = sys.argv[2]
    
    if not os.path.exists(validation_results_dir):
        print(f"❌ Validation results directory not found: {validation_results_dir}")
        sys.exit(1)
    
    violations = generate_detailed_report(validation_results_dir, output_file)
    print(f"📊 Report generated: {output_file} ({violations} violations)")

if __name__ == "__main__":
    main()