#!/usr/bin/env python3
"""
Terraform tfvars Generator for S3 Deployment with KMS Integration
This script generates terraform.tfvars based on user inputs and templates
"""

import json
import os
import sys
from datetime import datetime
from typing import Dict, Any, List
import argparse

class TerraformTfvarsGenerator:
    def __init__(self):
        self.mandatory_inputs = {}
        self.optional_inputs = {}
        self.bucket_configs = []
        
    def collect_mandatory_inputs(self) -> Dict[str, Any]:
        """Collect mandatory inputs from user"""
        print("🚀 S3 Deployment Configuration Generator")
        print("=" * 50)
        
        mandatory = {}
        
        # AWS Region
        mandatory['aws_region'] = input("Enter AWS Region [us-east-1]: ") or "us-east-1"
        
        # Environment
        environment = input("Enter Environment (dev/staging/prod) [dev]: ") or "dev"
        mandatory['environment'] = environment
        
        # Project Name
        mandatory['project_name'] = input("Enter Project Name: ").strip()
        if not mandatory['project_name']:
            print("❌ Project name is required!")
            sys.exit(1)
            
        # KMS Key ID (existing custom key)
        mandatory['kms_key_id'] = input("Enter existing KMS Key ID (leave empty for no encryption): ").strip()
        
        # AWS Account ID for dynamic backend key
        mandatory['account_id'] = input("Enter AWS Account ID (for backend key mapping): ").strip()
        if not mandatory['account_id']:
            print("❌ AWS Account ID is required for dynamic backend configuration!")
            sys.exit(1)
            
        # IAM Role Name
        mandatory['iam_role_name'] = input("Enter IAM Role Name for S3/KMS access: ").strip()
        if not mandatory['iam_role_name']:
            print("❌ IAM Role name is required!")
            sys.exit(1)
            
        # Update KMS Policy
        update_kms = input("Update KMS key policy for S3 access? (y/n) [y]: ") or "y"
        mandatory['update_kms_policy'] = update_kms.lower() == 'y'
        
        return mandatory
    
    def collect_bucket_configurations(self) -> List[Dict[str, Any]]:
        """Collect S3 bucket configurations"""
        buckets = []
        
        print("\n📦 S3 Bucket Configuration")
        print("=" * 30)
        
        while True:
            bucket = {}
            
            # Bucket name
            bucket_name = input(f"\nEnter bucket name (without random suffix): ").strip()
            if not bucket_name:
                break
                
            # Add environment and random suffix
            bucket['bucket_name'] = f"{bucket_name}-{self.mandatory_inputs['environment']}-{datetime.now().strftime('%Y%m%d%H%M')}"
            
            # Bucket type
            print("\nSelect bucket type:")
            print("1. Application Data (secure)")
            print("2. Logging Bucket")
            print("3. Static Website")
            print("4. Backup Storage")
            
            bucket_type = input("Enter choice (1-4) [1]: ") or "1"
            
            # Configure based on type
            if bucket_type == "1":
                bucket.update(self._configure_application_bucket())
            elif bucket_type == "2":
                bucket.update(self._configure_logging_bucket())
            elif bucket_type == "3":
                bucket.update(self._configure_website_bucket())
            elif bucket_type == "4":
                bucket.update(self._configure_backup_bucket())
            
            # Force destroy (for non-prod)
            if self.mandatory_inputs['environment'] != 'prod':
                bucket['force_destroy'] = True
            else:
                force_destroy = input("Allow force destroy for production? (y/n) [n]: ") or "n"
                bucket['force_destroy'] = force_destroy.lower() == 'y'
            
            buckets.append(bucket)
            
            # Ask for more buckets
            more = input("\nAdd another bucket? (y/n) [n]: ") or "n"
            if more.lower() != 'y':
                break
                
        return buckets
    
    def _configure_application_bucket(self) -> Dict[str, Any]:
        """Configure application data bucket"""
        config = {
            'versioning_enabled': True,
            'public_access_block': {
                'block_public_acls': True,
                'block_public_policy': True,
                'ignore_public_acls': True,
                'restrict_public_buckets': True
            },
            'bucket_policy_file': './policies/application-data-policy.json',
            'tags': {
                'Purpose': 'Application Data Storage',
                'Backup': 'true'
            }
        }
        
        # Add KMS encryption if key provided
        if self.mandatory_inputs.get('kms_key_id'):
            config['encryption'] = {
                'sse_algorithm': 'aws:kms',
                'kms_master_key_id': self.mandatory_inputs['kms_key_id'],
                'bucket_key_enabled': True
            }
        
        return config
    
    def _configure_logging_bucket(self) -> Dict[str, Any]:
        """Configure logging bucket"""
        source_bucket = input("Enter source bucket ARN for logging: ").strip()
        
        config = {
            'versioning_enabled': True,
            'public_access_block': {
                'block_public_acls': True,
                'block_public_policy': True,
                'ignore_public_acls': True,
                'restrict_public_buckets': True
            },
            'bucket_policy_file': './policies/logging-bucket-policy.json',
            'source_bucket_arn': source_bucket,
            'lifecycle_rules': [{
                'id': 'logs-lifecycle',
                'status': 'Enabled',
                'filter': {'prefix': 'logs/'},
                'transitions': [
                    {'days': 30, 'storage_class': 'STANDARD_IA'},
                    {'days': 90, 'storage_class': 'GLACIER'}
                ],
                'expiration': {'days': 365}
            }],
            'tags': {
                'Purpose': 'Access Logging',
                'Retention': '1-year'
            }
        }
        
        return config
    
    def _configure_website_bucket(self) -> Dict[str, Any]:
        """Configure static website bucket"""
        config = {
            'public_access_block': {
                'block_public_acls': False,
                'block_public_policy': False,
                'ignore_public_acls': False,
                'restrict_public_buckets': False
            },
            'website': {
                'index_document': 'index.html',
                'error_document': 'error.html'
            },
            'cors_rules': [{
                'allowed_headers': ['*'],
                'allowed_methods': ['GET', 'HEAD'],
                'allowed_origins': ['*'],
                'max_age_seconds': 3600
            }],
            'tags': {
                'Purpose': 'Static Website',
                'Public': 'true'
            }
        }
        
        return config
    
    def _configure_backup_bucket(self) -> Dict[str, Any]:
        """Configure backup bucket"""
        config = {
            'versioning_enabled': True,
            'force_destroy': False,  # Protect backups
            'public_access_block': {
                'block_public_acls': True,
                'block_public_policy': True,
                'ignore_public_acls': True,
                'restrict_public_buckets': True
            },
            'bucket_policy_file': './policies/secure-kms-policy.json',
            'lifecycle_rules': [{
                'id': 'backup-retention',
                'status': 'Enabled',
                'transitions': [
                    {'days': 30, 'storage_class': 'STANDARD_IA'},
                    {'days': 90, 'storage_class': 'GLACIER'},
                    {'days': 365, 'storage_class': 'DEEP_ARCHIVE'}
                ]
            }],
            'tags': {
                'Purpose': 'Backup Storage',
                'Critical': 'true',
                'Retention': '7-years'
            }
        }
        
        # Force KMS encryption for backups
        if self.mandatory_inputs.get('kms_key_id'):
            config['encryption'] = {
                'sse_algorithm': 'aws:kms',
                'kms_master_key_id': self.mandatory_inputs['kms_key_id'],
                'bucket_key_enabled': True
            }
        
        return config
    
    def generate_tfvars(self) -> str:
        """Generate terraform.tfvars content"""
        
        # Collect all inputs
        self.mandatory_inputs = self.collect_mandatory_inputs()
        self.bucket_configs = self.collect_bucket_configurations()
        
        if not self.bucket_configs:
            print("❌ At least one bucket configuration is required!")
            sys.exit(1)
        
        # Generate tfvars content
        tfvars_content = f'''# Generated S3 Deployment Configuration
# Generated on: {datetime.now().isoformat()}
# Project: {self.mandatory_inputs['project_name']}
# Environment: {self.mandatory_inputs['environment']}

# Account Configuration for Dynamic Backend
account_name = "{self.mandatory_inputs['environment']}"  # Use environment as account name
account_id = "{self.mandatory_inputs.get('account_id', '')}"   # AWS Account ID
environment = "{self.mandatory_inputs['environment']}"           # Environment

# AWS Configuration
aws_region = "{self.mandatory_inputs['aws_region']}"

# KMS Configuration
kms_key_id = "{self.mandatory_inputs['kms_key_id']}"
update_kms_policy = {str(self.mandatory_inputs['update_kms_policy']).lower()}

# IAM Configuration
iam_role_name = "{self.mandatory_inputs['iam_role_name']}"

# Common Tags
common_tags = {{
  Project     = "{self.mandatory_inputs['project_name']}"
  Environment = "{self.mandatory_inputs['environment']}"
  Owner       = "DevOps-Team"
  Terraform   = "true"
  Generated   = "{datetime.now().strftime('%Y-%m-%d')}"
  KMSEnabled  = "{bool(self.mandatory_inputs['kms_key_id'])}"
}}

# S3 Buckets Configuration
s3_buckets = {{'''

        # Add bucket configurations
        for i, bucket in enumerate(self.bucket_configs):
            bucket_name = bucket.pop('bucket_name')
            bucket_key = f"bucket-{i+1}"
            
            tfvars_content += f'\n  "{bucket_key}" = {{\n'
            tfvars_content += f'    bucket_name = "{bucket_name}"\n'
            
            for key, value in bucket.items():
                if isinstance(value, str):
                    tfvars_content += f'    {key} = "{value}"\n'
                elif isinstance(value, bool):
                    tfvars_content += f'    {key} = {str(value).lower()}\n'
                elif isinstance(value, dict):
                    tfvars_content += f'    {key} = {self._format_dict(value, 2)}\n'
                elif isinstance(value, list):
                    tfvars_content += f'    {key} = {self._format_list(value, 2)}\n'
            
            tfvars_content += '  }'
            if i < len(self.bucket_configs) - 1:
                tfvars_content += ','
            tfvars_content += '\n'
        
        tfvars_content += '}\n'
        
        return tfvars_content
    
    def _format_dict(self, d: Dict, indent_level: int) -> str:
        """Format dictionary for HCL"""
        indent = '  ' * indent_level
        lines = ['{']
        for k, v in d.items():
            if isinstance(v, str):
                lines.append(f'{indent}  {k} = "{v}"')
            elif isinstance(v, bool):
                lines.append(f'{indent}  {k} = {str(v).lower()}')
            elif isinstance(v, dict):
                lines.append(f'{indent}  {k} = {self._format_dict(v, indent_level + 1)}')
            elif isinstance(v, list):
                lines.append(f'{indent}  {k} = {self._format_list(v, indent_level + 1)}')
        lines.append(f'{indent}}}')
        return '\n'.join(lines)
    
    def _format_list(self, lst: List, indent_level: int) -> str:
        """Format list for HCL"""
        if not lst:
            return '[]'
        
        indent = '  ' * indent_level
        if all(isinstance(item, (str, int, bool)) for item in lst):
            # Simple list
            formatted_items = []
            for item in lst:
                if isinstance(item, str):
                    formatted_items.append(f'"{item}"')
                else:
                    formatted_items.append(str(item).lower() if isinstance(item, bool) else str(item))
            return f'[{", ".join(formatted_items)}]'
        else:
            # Complex list with objects
            lines = ['[']
            for i, item in enumerate(lst):
                if isinstance(item, dict):
                    lines.append(f'{indent}  {self._format_dict(item, indent_level + 1)}')
                    if i < len(lst) - 1:
                        lines.append(f'{indent}  ,')
            lines.append(f'{indent}]')
            return '\n'.join(lines)

def main():
    parser = argparse.ArgumentParser(description='Generate terraform.tfvars for S3 deployment')
    parser.add_argument('--output', '-o', default='terraform.tfvars', 
                       help='Output file path (default: terraform.tfvars)')
    parser.add_argument('--interactive', '-i', action='store_true', default=True,
                       help='Interactive mode (default)')
    
    args = parser.parse_args()
    
    generator = TerraformTfvarsGenerator()
    
    try:
        # Generate tfvars content
        tfvars_content = generator.generate_tfvars()
        
        # Write to file
        with open(args.output, 'w') as f:
            f.write(tfvars_content)
        
        print(f"\n✅ Generated {args.output} successfully!")
        print(f"📁 File location: {os.path.abspath(args.output)}")
        print("\n🚀 Next steps:")
        print("1. Review the generated terraform.tfvars file")
        print("2. Ensure JSON policy files exist in ./policies/ directory")
        print("3. Run: terraform init")
        print("4. Run: terraform plan")
        print("5. Run: terraform apply")
        
    except KeyboardInterrupt:
        print("\n❌ Generation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error generating tfvars: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()