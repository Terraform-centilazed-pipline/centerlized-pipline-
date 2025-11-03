#!/usr/bin/env python3
"""
Cross-Account STS Token Generator
=================================

Purpose: Generate cross-account STS tokens for terraform deployments
Usage: Extract account IDs from terraform plans and generate appropriate STS tokens
Author: DevOps Team
Version: 1.0.0

Features:
- Fast STS token generation for multiple AWS accounts
- Account discovery from terraform plan files
- Role assumption with cross-account access
- JSON output for workflow integration
- Error handling and retry logic
"""

import json
import boto3
import sys
import os
import time
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import argparse
from pathlib import Path

class CrossAccountSTSGenerator:
    def __init__(self, base_role_arn_template: str, session_duration: int = 3600):
        """
        Initialize the STS generator
        
        Args:
            base_role_arn_template: Template for role ARN (e.g., "arn:aws:iam::{account_id}:role/TerraformDeploymentRole")
            session_duration: STS token duration in seconds (default: 1 hour)
        """
        self.base_role_arn_template = base_role_arn_template
        self.session_duration = session_duration
        self.sts_client = boto3.client('sts')
        self.generated_tokens = {}
        
    def extract_accounts_from_terraform_plans(self, plans_directory: str) -> List[str]:
        """
        Extract unique AWS account IDs from terraform plan files
        
        Args:
            plans_directory: Directory containing terraform plan JSON files
            
        Returns:
            List of unique AWS account IDs found in plans
        """
        accounts = set()
        plans_dir = Path(plans_directory)
        
        print(f"🔍 Scanning terraform plans in: {plans_dir}")
        
        # Find all JSON plan files
        plan_files = list(plans_dir.glob("**/*.json"))
        
        if not plan_files:
            print(f"⚠️ No JSON plan files found in {plans_dir}")
            return []
            
        print(f"📋 Found {len(plan_files)} plan files")
        
        for plan_file in plan_files:
            try:
                print(f"📖 Processing: {plan_file.name}")
                
                with open(plan_file, 'r') as f:
                    plan_data = json.load(f)
                
                # Extract account IDs from various sources in the plan
                extracted_accounts = self._extract_accounts_from_plan_data(plan_data)
                accounts.update(extracted_accounts)
                
                if extracted_accounts:
                    print(f"  📍 Found accounts: {', '.join(extracted_accounts)}")
                    
            except Exception as e:
                print(f"⚠️ Error processing {plan_file}: {e}")
                continue
                
        unique_accounts = list(accounts)
        print(f"✅ Total unique accounts discovered: {len(unique_accounts)}")
        print(f"🏦 Account IDs: {', '.join(unique_accounts)}")
        
        return unique_accounts
    
    def _extract_accounts_from_plan_data(self, plan_data: Dict) -> List[str]:
        """
        Extract account IDs from terraform plan JSON data
        
        Args:
            plan_data: Parsed terraform plan JSON
            
        Returns:
            List of account IDs found in this plan
        """
        accounts = set()
        
        # Method 1: Check planned_values resources
        if 'planned_values' in plan_data and 'root_module' in plan_data['planned_values']:
            resources = plan_data['planned_values']['root_module'].get('resources', [])
            
            for resource in resources:
                # Look for AWS provider configurations
                if resource.get('provider_name') == 'registry.terraform.io/hashicorp/aws':
                    # Check resource values for account references
                    values = resource.get('values', {})
                    
                    # Common fields that might contain account IDs
                    account_fields = ['account_id', 'owner_id', 'account']
                    for field in account_fields:
                        if field in values and values[field]:
                            account_id = str(values[field]).strip()
                            if self._is_valid_account_id(account_id):
                                accounts.add(account_id)
                    
                    # Check ARNs for account IDs
                    arn_fields = ['arn', 'role_arn', 'bucket_arn', 'key_arn']
                    for field in arn_fields:
                        if field in values and values[field]:
                            account_from_arn = self._extract_account_from_arn(values[field])
                            if account_from_arn:
                                accounts.add(account_from_arn)
        
        # Method 2: Check configuration for account variables
        if 'configuration' in plan_data:
            config = plan_data['configuration']
            if 'root_module' in config:
                # Look for account variables in locals or variables
                if 'locals' in config['root_module']:
                    accounts.update(self._extract_accounts_from_locals(config['root_module']['locals']))
                
                if 'variables' in config['root_module']:
                    accounts.update(self._extract_accounts_from_variables(config['root_module']['variables']))
        
        # Method 3: Check resource changes
        if 'resource_changes' in plan_data:
            for change in plan_data['resource_changes']:
                if 'change' in change and 'after' in change['change']:
                    after_values = change['change']['after'] or {}
                    
                    # Look for account references in resource changes
                    for key, value in after_values.items():
                        if 'account' in key.lower() and value:
                            account_id = str(value).strip()
                            if self._is_valid_account_id(account_id):
                                accounts.add(account_id)
        
        return list(accounts)
    
    def _extract_accounts_from_locals(self, locals_config: Dict) -> List[str]:
        """Extract account IDs from terraform locals"""
        accounts = set()
        
        def recursive_search(obj, path=""):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    if 'account' in key.lower() and isinstance(value, (str, int)):
                        account_id = str(value).strip()
                        if self._is_valid_account_id(account_id):
                            accounts.add(account_id)
                    else:
                        recursive_search(value, f"{path}.{key}")
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    recursive_search(item, f"{path}[{i}]")
        
        recursive_search(locals_config)
        return list(accounts)
    
    def _extract_accounts_from_variables(self, variables_config: Dict) -> List[str]:
        """Extract account IDs from terraform variables"""
        accounts = set()
        
        for var_name, var_config in variables_config.items():
            if 'account' in var_name.lower():
                # Check default value
                if 'default' in var_config:
                    default_val = var_config['default']
                    if isinstance(default_val, (str, int)):
                        account_id = str(default_val).strip()
                        if self._is_valid_account_id(account_id):
                            accounts.add(account_id)
        
        return list(accounts)
    
    def _extract_account_from_arn(self, arn: str) -> Optional[str]:
        """
        Extract account ID from AWS ARN
        
        Args:
            arn: AWS ARN string
            
        Returns:
            Account ID if found, None otherwise
        """
        try:
            # ARN format: arn:partition:service:region:account-id:resource
            parts = arn.split(':')
            if len(parts) >= 5 and self._is_valid_account_id(parts[4]):
                return parts[4]
        except:
            pass
        return None
    
    def _is_valid_account_id(self, account_id: str) -> bool:
        """
        Validate AWS account ID format
        
        Args:
            account_id: Potential account ID string
            
        Returns:
            True if valid AWS account ID format
        """
        try:
            # AWS account IDs are 12-digit numbers
            return len(account_id) == 12 and account_id.isdigit()
        except:
            return False
    
    def generate_cross_account_sts_tokens(self, account_ids: List[str]) -> Dict[str, Dict]:
        """
        Generate STS tokens for multiple AWS accounts
        
        Args:
            account_ids: List of AWS account IDs to generate tokens for
            
        Returns:
            Dictionary mapping account IDs to their STS credentials
        """
        results = {}
        
        print(f"🔑 Generating STS tokens for {len(account_ids)} accounts...")
        
        for account_id in account_ids:
            try:
                print(f"🎭 Assuming role for account: {account_id}")
                
                # Generate role ARN for this account
                role_arn = self.base_role_arn_template.format(account_id=account_id)
                
                # Generate session name
                session_name = f"CrossAccount-Deploy-{account_id}-{int(time.time())}"
                
                # Assume role for this account
                response = self.sts_client.assume_role(
                    RoleArn=role_arn,
                    RoleSessionName=session_name,
                    DurationSeconds=self.session_duration
                )
                
                credentials = response['Credentials']
                
                # Store credentials for this account
                results[account_id] = {
                    'aws_access_key_id': credentials['AccessKeyId'],
                    'aws_secret_access_key': credentials['SecretAccessKey'],
                    'aws_session_token': credentials['SessionToken'],
                    'expiration': credentials['Expiration'].isoformat(),
                    'role_arn': role_arn,
                    'session_name': session_name,
                    'generated_at': datetime.utcnow().isoformat()
                }
                
                print(f"  ✅ Token generated (expires: {credentials['Expiration']})")
                
            except Exception as e:
                print(f"  ❌ Failed to generate token for {account_id}: {e}")
                results[account_id] = {
                    'error': str(e),
                    'role_arn': self.base_role_arn_template.format(account_id=account_id),
                    'generated_at': datetime.utcnow().isoformat()
                }
        
        return results
    
    def save_tokens_to_file(self, tokens: Dict[str, Dict], output_file: str):
        """
        Save STS tokens to JSON file
        
        Args:
            tokens: Dictionary of account tokens
            output_file: Path to output JSON file
        """
        output_path = Path(output_file)
        
        # Prepare output data
        output_data = {
            'generated_at': datetime.utcnow().isoformat(),
            'token_count': len(tokens),
            'accounts': list(tokens.keys()),
            'session_duration_seconds': self.session_duration,
            'tokens': tokens
        }
        
        # Write to file
        with open(output_path, 'w') as f:
            json.dump(output_data, f, indent=2, default=str)
        
        print(f"💾 STS tokens saved to: {output_path}")
        
        # Also create a summary file
        summary_file = output_path.parent / f"{output_path.stem}_summary.json"
        summary_data = {
            'generated_at': output_data['generated_at'],
            'total_accounts': len(tokens),
            'successful_tokens': len([t for t in tokens.values() if 'error' not in t]),
            'failed_tokens': len([t for t in tokens.values() if 'error' in t]),
            'accounts': {
                'successful': [acc for acc, token in tokens.items() if 'error' not in token],
                'failed': [acc for acc, token in tokens.items() if 'error' in token]
            }
        }
        
        with open(summary_file, 'w') as f:
            json.dump(summary_data, f, indent=2)
        
        print(f"📊 Summary saved to: {summary_file}")


def main():
    parser = argparse.ArgumentParser(description='Generate cross-account STS tokens for terraform deployments')
    parser.add_argument('--plans-dir', required=True, help='Directory containing terraform plan JSON files')
    parser.add_argument('--role-template', required=True, help='Role ARN template with {account_id} placeholder')
    parser.add_argument('--output', required=True, help='Output JSON file for STS tokens')
    parser.add_argument('--duration', type=int, default=3600, help='STS token duration in seconds (default: 3600)')
    parser.add_argument('--accounts', help='Comma-separated list of account IDs (if not auto-discovering)')
    
    args = parser.parse_args()
    
    print("🚀 Cross-Account STS Token Generator")
    print("=" * 50)
    print(f"📂 Plans directory: {args.plans_dir}")
    print(f"🎭 Role template: {args.role_template}")
    print(f"💾 Output file: {args.output}")
    print(f"⏰ Token duration: {args.duration} seconds")
    print("")
    
    # Initialize generator
    generator = CrossAccountSTSGenerator(
        base_role_arn_template=args.role_template,
        session_duration=args.duration
    )
    
    # Get account IDs
    if args.accounts:
        # Use provided account IDs
        account_ids = [acc.strip() for acc in args.accounts.split(',')]
        print(f"📋 Using provided account IDs: {', '.join(account_ids)}")
    else:
        # Auto-discover from terraform plans
        account_ids = generator.extract_accounts_from_terraform_plans(args.plans_dir)
        
        if not account_ids:
            print("❌ No account IDs found in terraform plans!")
            sys.exit(1)
    
    # Generate STS tokens
    tokens = generator.generate_cross_account_sts_tokens(account_ids)
    
    # Save to file
    generator.save_tokens_to_file(tokens, args.output)
    
    # Print summary
    successful = len([t for t in tokens.values() if 'error' not in t])
    failed = len([t for t in tokens.values() if 'error' in t])
    
    print("")
    print("📊 Generation Summary:")
    print(f"  ✅ Successful: {successful}")
    print(f"  ❌ Failed: {failed}")
    print(f"  📊 Total: {len(tokens)}")
    
    if failed > 0:
        print("\n❌ Failed accounts:")
        for acc, token in tokens.items():
            if 'error' in token:
                print(f"  • {acc}: {token['error']}")
    
    print(f"\n🎉 Cross-account STS token generation complete!")
    
    # Exit with appropriate code
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()