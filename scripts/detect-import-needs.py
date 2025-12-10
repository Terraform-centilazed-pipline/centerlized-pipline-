#!/usr/bin/env python3
"""
Smart Import Gap Detection
Checks if tfvars references resources that exist in AWS but not in Terraform state

Exit Codes:
  0 = No gap (all resources managed or don't exist)
  1 = Gap detected (resources need import)
  2 = Error
"""

import sys
import re
import subprocess
import json
from pathlib import Path
from typing import List, Dict, Optional

class GapDetector:
    """Detects resources that need importing"""
    
    def __init__(self, tfvars_file: str):
        self.tfvars_file = Path(tfvars_file)
        self.gaps = []
        self.checked = []
        
    def extract_resources(self) -> List[Dict]:
        """Parse tfvars for all resource references"""
        content = self.tfvars_file.read_text()
        resources = []
        
        # S3 Buckets
        s3_pattern = r's3_buckets\s*=\s*\{([^}]+)\}'
        s3_match = re.search(s3_pattern, content, re.DOTALL)
        if s3_match:
            block = s3_match.group(1)
            for match in re.finditer(r'"([^"]+)"\s*=\s*\{([^}]+)\}', block, re.DOTALL):
                key = match.group(1)
                resource_block = match.group(2)
                
                # Extract bucket_name
                name_match = re.search(r'bucket_name\s*=\s*"([^"]+)"', resource_block)
                if name_match:
                    resources.append({
                        'type': 's3',
                        'key': key,
                        'id': name_match.group(1),
                        'target': f'module.s3["{key}"].aws_s3_bucket.this[0]',
                        'aws_check_cmd': ['aws', 's3api', 'head-bucket', '--bucket', name_match.group(1)]
                    })
        
        # IAM Roles
        iam_pattern = r'iam_roles\s*=\s*\{([^}]+)\}'
        iam_match = re.search(iam_pattern, content, re.DOTALL)
        if iam_match:
            block = iam_match.group(1)
            for match in re.finditer(r'"([^"]+)"\s*=\s*\{([^}]+)\}', block, re.DOTALL):
                key = match.group(1)
                resource_block = match.group(2)
                
                # Extract role_name
                name_match = re.search(r'role_name\s*=\s*"([^"]+)"', resource_block)
                if name_match:
                    role_name = name_match.group(1)
                    resources.append({
                        'type': 'iam_role',
                        'key': key,
                        'id': role_name,
                        'target': f'module.iam["{key}"].aws_iam_role.this[0]',
                        'aws_check_cmd': ['aws', 'iam', 'get-role', '--role-name', role_name]
                    })
        
        # Lambda Functions
        lambda_pattern = r'lambda_functions\s*=\s*\{([^}]+)\}'
        lambda_match = re.search(lambda_pattern, content, re.DOTALL)
        if lambda_match:
            block = lambda_match.group(1)
            for match in re.finditer(r'"([^"]+)"\s*=\s*\{([^}]+)\}', block, re.DOTALL):
                key = match.group(1)
                resource_block = match.group(2)
                
                # Extract function_name
                name_match = re.search(r'function_name\s*=\s*"([^"]+)"', resource_block)
                if name_match:
                    func_name = name_match.group(1)
                    resources.append({
                        'type': 'lambda',
                        'key': key,
                        'id': func_name,
                        'target': f'module.lambda["{key}"].aws_lambda_function.this[0]',
                        'aws_check_cmd': ['aws', 'lambda', 'get-function', '--function-name', func_name]
                    })
        
        # KMS Keys
        kms_pattern = r'kms_keys\s*=\s*\{([^}]+)\}'
        kms_match = re.search(kms_pattern, content, re.DOTALL)
        if kms_match:
            block = kms_match.group(1)
            for match in re.finditer(r'"([^"]+)"\s*=\s*\{([^}]+)\}', block, re.DOTALL):
                key = match.group(1)
                resource_block = match.group(2)
                
                # Extract key_id or alias
                key_match = re.search(r'(?:key_id|alias)\s*=\s*"([^"]+)"', resource_block)
                if key_match:
                    key_id = key_match.group(1)
                    resources.append({
                        'type': 'kms',
                        'key': key,
                        'id': key_id,
                        'target': f'module.kms["{key}"].aws_kms_key.this[0]',
                        'aws_check_cmd': ['aws', 'kms', 'describe-key', '--key-id', key_id]
                    })
        
        return resources
    
    def check_terraform_state(self, target: str) -> bool:
        """Check if resource exists in Terraform state"""
        try:
            result = subprocess.run(
                ['terraform', 'state', 'list'],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                return target in result.stdout
            
            return False
        except Exception as e:
            print(f"⚠️  Warning: Could not check state: {e}", file=sys.stderr)
            return False
    
    def check_aws_exists(self, cmd: List[str]) -> bool:
        """Check if resource exists in AWS"""
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            # Exit 0 = resource exists
            return result.returncode == 0
            
        except subprocess.TimeoutExpired:
            print(f"⚠️  Warning: AWS check timed out for {cmd}", file=sys.stderr)
            return False
        except Exception as e:
            print(f"⚠️  Warning: AWS check failed: {e}", file=sys.stderr)
            return False
    
    def detect_gaps(self) -> List[Dict]:
        """Find resources that exist in AWS but not in Terraform state"""
        resources = self.extract_resources()
        
        if not resources:
            print("ℹ️  No resources found in tfvars")
            return []
        
        print(f"🔍 Checking {len(resources)} resources...")
        
        for resource in resources:
            self.checked.append(resource)
            
            # Step 1: Check Terraform state
            in_state = self.check_terraform_state(resource['target'])
            
            if in_state:
                print(f"   ✅ {resource['type']}: {resource['id']} (already managed)")
                continue
            
            # Step 2: Check if exists in AWS
            in_aws = self.check_aws_exists(resource['aws_check_cmd'])
            
            if in_aws:
                # GAP DETECTED: In AWS but not in Terraform state
                print(f"   🔍 {resource['type']}: {resource['id']} (NEEDS IMPORT)")
                self.gaps.append(resource)
            else:
                # Not in AWS and not in state - will be created on apply
                print(f"   ➕ {resource['type']}: {resource['id']} (will be created)")
        
        return self.gaps
    
    def generate_import_report(self) -> Dict:
        """Generate JSON report of gaps"""
        return {
            'needs_import': len(self.gaps) > 0,
            'total_checked': len(self.checked),
            'gap_count': len(self.gaps),
            'gaps': [
                {
                    'type': g['type'],
                    'key': g['key'],
                    'id': g['id'],
                    'target': g['target']
                }
                for g in self.gaps
            ]
        }

def main():
    if len(sys.argv) < 2:
        print("Usage: detect-import-needs.py <tfvars-file>")
        sys.exit(2)
    
    tfvars_file = sys.argv[1]
    
    if not Path(tfvars_file).exists():
        print(f"❌ Error: File not found: {tfvars_file}")
        sys.exit(2)
    
    print(f"\n{'='*70}")
    print(f"🔍 IMPORT GAP DETECTION")
    print(f"{'='*70}")
    print(f"📂 File: {tfvars_file}")
    print(f"{'='*70}\n")
    
    detector = GapDetector(tfvars_file)
    
    try:
        gaps = detector.detect_gaps()
        report = detector.generate_import_report()
        
        # Write report for workflow to read
        report_file = Path(tfvars_file).parent / '.import-gap-report.json'
        report_file.write_text(json.dumps(report, indent=2))
        
        print(f"\n{'='*70}")
        print(f"📊 GAP DETECTION SUMMARY")
        print(f"{'='*70}")
        print(f"📋 Checked: {report['total_checked']} resources")
        print(f"🔍 Gaps Found: {report['gap_count']} resources need import")
        print(f"💾 Report: {report_file.name}")
        print(f"{'='*70}\n")
        
        if gaps:
            print("🚨 IMPORT REQUIRED")
            print("\nResources needing import:")
            for gap in gaps:
                print(f"   - {gap['type']}: {gap['id']}")
            print(f"\nRun: python3 resource-discovery.py {tfvars_file}")
            sys.exit(1)  # Gap detected
        else:
            print("✅ NO IMPORT NEEDED")
            print("All resources are either:")
            print("   - Already managed by Terraform")
            print("   - Will be created on next apply")
            sys.exit(0)  # No gap
    
    except KeyboardInterrupt:
        print("\n\n⚠️  Detection interrupted")
        sys.exit(2)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(2)

if __name__ == '__main__':
    main()
