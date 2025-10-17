#!/usr/bin/env python3
"""
Enhanced S3 Terraform tfvars Generator
Template-based S3 deployment generator using accounts.yaml configuration
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List
import argparse

try:
    import yaml
except ImportError:
    yaml = None

class S3TfvarsGenerator:
    """Enhanced S3 tfvars generator using template system"""
    
    def __init__(self):
        self.script_dir = Path(__file__).parent
        self.project_root = self.script_dir.parent  # Go up one level from scripts/ to repo root
        self.templates_dir = self.project_root / "templates"
        self.accounts_config = self._load_accounts_config()
        self.region_codes = self.accounts_config.get('regions', {
            'us-east-1': 'use1',
            'us-west-2': 'usw2',
            'eu-west-1': 'ew1',
            'eu-central-1': 'ec1',
            'ap-southeast-1': 'ase1',
            'ap-southeast-2': 'ase2'
        })
    
    def _load_accounts_config(self) -> Dict:
        """Load accounts configuration from accounts.yaml"""
        accounts_file = self.project_root / "accounts.yaml"
        if not accounts_file.exists():
            print(f"❌ accounts.yaml not found at {accounts_file}")
            sys.exit(1)
        
        if yaml is None:
            return self._parse_simple_yaml(accounts_file)
        else:
            with open(accounts_file, 'r') as f:
                return yaml.safe_load(f)
    
    def _parse_simple_yaml(self, file_path: Path) -> Dict:
        """Simple YAML parser fallback"""
        config = {'accounts': {}, 's3_templates': {}, 'regions': {}, 'default_tags': {}}
        current_section = None
        current_account = None
        
        with open(file_path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                if line.endswith(':'):
                    key = line[:-1].strip("'\"")
                    if key in ['accounts', 's3_templates', 'regions', 'default_tags']:
                        current_section = key
                        current_account = None
                    elif current_section == 'accounts' and (key.isdigit() or key.startswith("'")):
                        current_account = key.strip("'\"")
                        config['accounts'][current_account] = {}
                elif ':' in line and current_section and current_account:
                    key, value = line.split(':', 1)
                    key = key.strip()
                    value = value.strip().strip("'\"")
                    config['accounts'][current_account][key] = value
        
        return config
    
    def _load_json_config(self, config_file: str) -> Dict:
        """Load and validate JSON configuration file"""
        try:
            with open(config_file, 'r') as f:
                config = json.load(f)

            # Validate required fields
            required_fields = ['account', 'region', 'project_name', 'bucket_name_base', 'owner', 'cost_center', 'kms_key_id']
            missing_fields = [field for field in required_fields if field not in config or not str(config[field]).strip()]

            if missing_fields:
                raise ValueError(f"Missing required fields in JSON config: {missing_fields}")

            # Set defaults for optional fields
            defaults = {
                'description': 'Secure S3 bucket with KMS encryption',
                'versioning_enabled': True,
                'force_destroy': False,
                'template_type': 's3-bucket',
                'iam_role_name': None
            }

            for key, default_value in defaults.items():
                if key not in config or config[key] is None:
                    config[key] = default_value

            # Normalize required string fields
            for key in ['owner', 'cost_center', 'kms_key_id']:
                config[key] = str(config[key]).strip()

            print(f"✅ Loaded configuration from: {config_file}")
            return config
            
        except FileNotFoundError:
            raise ValueError(f"Configuration file not found: {config_file}")
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON format in {config_file}: {e}")
        except Exception as e:
            raise ValueError(f"Error loading configuration: {e}")
    
    def json_based_generation(self, config_file: str):
        """JSON-based S3 deployment generation"""
        print("🚀 Enhanced S3 Deployment Configuration Generator (JSON Mode)")
        print("=" * 60)
        
        # Load JSON configuration
        try:
            json_config = self._load_json_config(config_file)
        except ValueError as e:
            print(f"❌ Configuration Error: {e}")
            return
        
        # Find account info
        account_key = json_config['account']
        accounts = self.accounts_config.get('accounts', {})
        
        # Try to find account by name or ID
        account_info = None
        for acc_id, acc_data in accounts.items():
            if (acc_id == account_key or 
                acc_data.get('account_name') == account_key or 
                acc_data.get('account_id') == account_key):
                account_info = {
                    'account_id': acc_data.get('account_id', acc_id),
                    'account_name': acc_data.get('account_name', account_key),
                    'environment': acc_data.get('environment', 'development'),
                    'regions': acc_data.get('regions', [])
                }
                break
        
        if not account_info:
            print(f"❌ Account '{account_key}' not found in accounts.yaml")
            return
        
        # Validate region
        region = json_config['region']
        available_regions = account_info.get('regions', [])
        if available_regions and region not in available_regions:
            print(f"⚠️  Region '{region}' not in account's available regions: {available_regions}")
            print("Proceeding anyway...")
        
        print(f"📋 Account: {account_info['account_name']} ({account_info['account_id']})")
        print(f"🌍 Region: {region}")
        print(f"📦 Project: {json_config['project_name']}")
        print(f"🪣 Bucket Base: {json_config['bucket_name_base']}")
        
        # Prepare project details
        project_details = {
            'project_name': json_config['project_name'],
            'bucket_name_base': json_config['bucket_name_base'],
            'owner': json_config['owner'],
            'cost_center': json_config['cost_center']
        }
        
        # Prepare bucket configuration
        bucket_config = {
            'description': json_config['description'],
            'versioning_enabled': json_config['versioning_enabled'],
            'force_destroy': json_config['force_destroy'],
            'encryption_type': 'kms',
            'iam_role_name': json_config.get('iam_role_name', 'REPLACE-WITH-YOUR-ROLE')
        }
        
        # Collect VPC endpoint configuration (use existing method)
        print(f"\n🔒 VPC Endpoint Configuration:")
        vpc_config = self._collect_vpc_endpoint_configuration_json(account_info, region, json_config)
        
        # Collect KMS configuration (use existing method)
        print(f"\n🔐 KMS Configuration:")
        kms_config = self._collect_kms_configuration_json(region, json_config)
        
        # Merge all configurations
        full_config = {**bucket_config, **vpc_config, **kms_config}
        
        # Generate deployment
        template_type = json_config.get('template_type', 's3-bucket')
        self._generate_deployment(account_info, region, template_type, project_details, full_config)
    
    def interactive_generation(self):
        """Interactive S3 deployment generation"""
        print("🚀 Enhanced S3 Deployment Configuration Generator")
        print("=" * 55)
        
        # Select account
        account_info = self._select_account()
        if not account_info:
            return
        
        # Select region
        region = self._select_region(account_info)
        
        # Select S3 template
        template_type = self._select_s3_template()
        
        # Collect project details
        project_details = self._collect_project_details()
        
        # Collect bucket-specific configuration
        bucket_config = self._collect_bucket_configuration(template_type)
        
        # Collect VPC endpoint configuration
        vpc_config = self._collect_vpc_endpoint_configuration(account_info, region)
        
        # Collect KMS configuration
        kms_config = self._collect_kms_configuration(region)
        
        # Merge all configurations
        full_config = {**bucket_config, **vpc_config, **kms_config}
        
        # Generate deployment
        self._generate_deployment(account_info, region, template_type, project_details, full_config)
    
    def _select_account(self) -> Dict:
        """Select target account for deployment"""
        accounts = self.accounts_config.get('accounts', {})
        if not accounts:
            print("❌ No accounts configured in accounts.yaml")
            return None
        
        print("\n📋 Available Accounts:")
        account_list = list(accounts.items())
        for i, (account_id, account_info) in enumerate(account_list, 1):
            env = account_info.get('environment', 'unknown')
            name = account_info.get('account_name', account_id)
            print(f"{i}. {name} ({account_id}) - {env}")
        
        while True:
            try:
                choice = int(input(f"\nSelect account (1-{len(account_list)}): "))
                if 1 <= choice <= len(account_list):
                    account_id, account_info = account_list[choice - 1]
                    account_info['account_id'] = account_id
                    return account_info
                else:
                    print("❌ Invalid choice. Please try again.")
            except ValueError:
                print("❌ Please enter a valid number.")
    
    def _select_region(self, account_info: Dict) -> str:
        """Select deployment region"""
        available_regions = list(self.region_codes.keys())
        
        if len(available_regions) == 1:
            return available_regions[0]
        
        print(f"\n🌍 Available Regions:")
        for i, region in enumerate(available_regions, 1):
            region_code = self.region_codes.get(region, region.replace('-', ''))
            print(f"{i}. {region} ({region_code})")
        
        while True:
            try:
                choice = int(input(f"\nSelect region (1-{len(available_regions)}): "))
                if 1 <= choice <= len(available_regions):
                    return available_regions[choice - 1]
                else:
                    print("❌ Invalid choice. Please try again.")
            except ValueError:
                print("❌ Please enter a valid number.")
    
    def _select_s3_template(self) -> str:
        """Select S3 bucket template type - simplified to single template"""
        print("\n📦 S3 Bucket Template:")
        print("1. S3 Bucket with KMS Encryption")
        print("   Secure S3 bucket with KMS encryption and customizable options")
        
        input("\nPress Enter to continue with S3 Bucket template...")
        return "s3-bucket"
    
    def _collect_project_details(self) -> Dict:
        """Collect project-specific details"""
        print("\n📋 Project Configuration:")
        
        project_name = input("Project Name: ").strip()
        if not project_name:
            print("❌ Project name is required!")
            sys.exit(1)
        
        bucket_name_base = input(f"Bucket Name Base [{project_name}]: ").strip() or project_name

        while True:
            owner = input("Owner/Team (required): ").strip()
            if owner:
                break
            print("❌ Owner/Team is required. Please provide a value.")

        while True:
            cost_center = input("Cost Center (required): ").strip()
            if cost_center:
                break
            print("❌ Cost Center is required. Please provide a value.")
        
        return {
            'project_name': project_name,
            'bucket_name_base': bucket_name_base,
            'owner': owner,
            'cost_center': cost_center
        }
    
    def _collect_bucket_configuration(self, template_type: str) -> Dict:
        """Collect bucket-specific configuration - simplified"""
        print(f"\n⚙️  S3 Bucket Configuration:")
        
        config = {}
        
        # Common configurations
        config['description'] = input("Bucket Description [Secure S3 bucket with KMS encryption]: ").strip() or "Secure S3 bucket with KMS encryption"
        
        # Versioning
        versioning = input("Enable versioning? (y/n) [y]: ").strip().lower()
        config['versioning_enabled'] = versioning != 'n'
        
        # Force destroy - default to false (no user input needed)
        config['force_destroy'] = False
        
        # Encryption - always use KMS (no AES256 option)
        config['encryption_type'] = 'kms'
        
        # IAM Role Name for S3 access
        print(f"\n🔐 IAM Role Configuration:")
        role_name = input("IAM Role Name for S3 access (e.g., MyAppS3AccessRole): ").strip()
        if not role_name:
            print("⚠️  No IAM Role name provided. You'll need to update the policy file manually.")
            role_name = "REPLACE-WITH-YOUR-ROLE"
        config['iam_role_name'] = role_name
        
        return config
    
    def _collect_vpc_endpoint_configuration(self, account_info: Dict, region: str) -> Dict:
        """Collect VPC endpoint configuration"""
        print(f"\n🔒 VPC Endpoint Security Configuration:")
        
        config = {}
        
        # Get shared interface endpoint from regional configuration
        interface_endpoints = self.accounts_config.get('vpc_interface_endpoints', {})
        interface_endpoint = interface_endpoints.get(region, '')
        
        if interface_endpoint:
            print(f"📋 Interface VPC Endpoint (shared for {region}): {interface_endpoint}")
            config['interface_endpoint'] = interface_endpoint
        else:
            print(f"⚠️  No shared Interface VPC Endpoint found for region {region}")
            interface_endpoint = input(f"Interface VPC Endpoint ID for {region} (e.g., vpce-12345678): ").strip()
            config['interface_endpoint'] = interface_endpoint or f"vpce-{region.replace('-', '')}-interface-XXXXXXXX"
        
        # Always ask for Gateway VPC Endpoint (account-specific)
        print(f"\n� Gateway VPC Endpoint Configuration:")
        print(f"Gateway endpoints are account-specific for {account_info['account_name']}")
        gateway_endpoint = input("Gateway VPC Endpoint ID (e.g., vpce-12345678): ").strip()
        if not gateway_endpoint:
            print("⚠️  No Gateway VPC Endpoint provided. Using placeholder.")
            gateway_endpoint = f"vpce-{region.replace('-', '')}-gateway-XXXXXXXX"
        config['gateway_endpoint'] = gateway_endpoint
        
        # Use Interface endpoint for policy (no selection needed)
        config['policy_endpoint'] = config['interface_endpoint']
        config['endpoint_type'] = 'interface'
        
        print(f"✅ Using Interface VPC Endpoint for S3 access policy")
        
        return config
    
    def _collect_kms_configuration(self, region: str) -> Dict:
        """Collect KMS key configuration based on region"""
        print(f"\n🔐 KMS Key Configuration:")
        
        while True:
            kms_key_id = input(
                f"KMS Key ID for region {region} (e.g., arn:aws:kms:{region}:123456789012:key/12345678-1234-1234-1234-123456789012): "
            ).strip()
            if kms_key_id:
                break
            print("❌ KMS Key ID is required for every region. Please enter a value.")

        return {
            'kms_key_id': kms_key_id
        }
    
    def _collect_vpc_endpoint_configuration_json(self, account_info: Dict, region: str, json_config: Dict) -> Dict:
        """Collect VPC endpoint configuration from JSON config"""
        config = {}
        
        # Get shared interface endpoint from regional configuration
        interface_endpoints = self.accounts_config.get('vpc_interface_endpoints', {})
        interface_endpoint = interface_endpoints.get(region, '')
        
        if interface_endpoint:
            print(f"📋 Using Interface VPC Endpoint (shared for {region}): {interface_endpoint}")
            config['interface_endpoint'] = interface_endpoint
        else:
            # Try to get from JSON config, otherwise use placeholder
            interface_endpoint = json_config.get('vpc_interface_endpoint', f"vpce-{region.replace('-', '')}-interface-XXXXXXXX")
            print(f"📋 Using Interface VPC Endpoint: {interface_endpoint}")
            config['interface_endpoint'] = interface_endpoint
        
        # Use Interface endpoint for policy
        config['policy_endpoint'] = config['interface_endpoint']
        config['endpoint_type'] = 'interface'
        
        print(f"✅ Using Interface VPC Endpoint for S3 access policy")
        
        return config
    
    def _collect_kms_configuration_json(self, region: str, json_config: Dict) -> Dict:
        """Collect KMS key configuration from JSON config"""
        kms_key_id = json_config.get('kms_key_id')
        if not kms_key_id or not str(kms_key_id).strip():
            raise ValueError(f"JSON configuration must include a non-empty 'kms_key_id' for region {region}.")

        print(f"✅ Using KMS Key: {kms_key_id}")
        return {
            'kms_key_id': kms_key_id.strip()
        }
    
    def _generate_aws_compliant_bucket_name(self, base_name: str, region_code: str, environment: str) -> str:
        """Generate AWS-compliant S3 bucket name following best practices"""
        # Clean and normalize inputs
        base_name = base_name.lower().replace('_', '-').replace(' ', '-')
        region_code = region_code.lower()
        environment = environment.lower()
        
        # Remove any invalid characters (only lowercase letters, numbers, hyphens, dots allowed)
        import re
        base_name = re.sub(r'[^a-z0-9\-.]', '', base_name)
        region_code = re.sub(r'[^a-z0-9\-.]', '', region_code)
        environment = re.sub(r'[^a-z0-9\-.]', '', environment)
        
        # Construct bucket name: base-region-environment
        bucket_name = f"{base_name}-{region_code}-{environment}"
        
        # Ensure it doesn't start or end with hyphen/dot
        bucket_name = bucket_name.strip('.-')
        
        # Ensure max 63 characters (AWS limit)
        if len(bucket_name) > 63:
            # Truncate base name to fit within limit
            max_base_length = 63 - len(region_code) - len(environment) - 2  # 2 hyphens
            if max_base_length > 0:
                base_name_truncated = base_name[:max_base_length].rstrip('-.')
                bucket_name = f"{base_name_truncated}-{region_code}-{environment}"
            else:
                # If still too long, use minimal form
                bucket_name = f"{base_name[:20]}-{region_code[:10]}-{environment[:10]}"
        
        return bucket_name
    
    def bulk_generate_multiple_accounts_regions(self, accounts: List[str], regions: List[str], project_configs: List[Dict]):
        """Bulk generate S3 deployments for multiple accounts and regions"""
        print("🚀 Bulk S3 Deployment Generator")
        print("=" * 50)
        
        total_deployments = len(accounts) * len(regions) * len(project_configs)
        print(f"📊 Total deployments to generate: {total_deployments}")
        print(f"   📋 Accounts: {len(accounts)}")
        print(f"   🌍 Regions: {len(regions)}")
        print(f"   📦 Projects: {len(project_configs)}")
        print()
        
        generated_count = 0
        failed_count = 0
        
        for account_key in accounts:
            # Find account info
            account_info = self._find_account_by_key(account_key)
            if not account_info:
                print(f"❌ Account '{account_key}' not found, skipping...")
                failed_count += len(regions) * len(project_configs)
                continue
            
            for region in regions:
                # Validate region for account
                if not self._validate_region_for_account(account_info, region):
                    print(f"⚠️  Region '{region}' not available for account '{account_info['account_name']}', skipping...")
                    failed_count += len(project_configs)
                    continue
                
                for project_config in project_configs:
                    try:
                        project_name = project_config.get('project_name', project_config.get('name'))
                        if not project_name:
                            raise ValueError("Project configuration requires a 'name' or 'project_name' field.")

                        print(f"🔄 Generating: {account_info['account_name']}/{region}/{project_name}")

                        owner = str(project_config.get('owner', '')).strip()
                        cost_center = str(project_config.get('cost_center', '')).strip()
                        kms_overrides = project_config.get('kms_key_ids', {}) or {}
                        kms_key_id = kms_overrides.get(region) or str(project_config.get('kms_key_id', '')).strip()

                        if not owner or not cost_center or not kms_key_id:
                            raise ValueError("Project configuration requires owner, cost_center, and KMS key details.")
                        
                        # Use default bucket config if not provided
                        bucket_config = project_config.get('bucket_config', {
                            'description': f"S3 bucket for {project_name}",
                            'versioning_enabled': True,
                            'force_destroy': False,
                            'encryption_type': 'kms',
                            'endpoint_type': 'interface'
                        })

                        bucket_config['kms_key_id'] = bucket_config.get('kms_key_id', kms_key_id)
                        bucket_config['iam_role_name'] = bucket_config.get('iam_role_name', 'TerraformExecutionRole')
                        
                        project_details = {
                            'project_name': project_name,
                            'bucket_name_base': project_config.get('bucket_base', project_name),
                            'owner': owner,
                            'cost_center': cost_center
                        }

                        self._generate_deployment(account_info, region, 's3-bucket', project_details, bucket_config)
                        generated_count += 1
                        
                    except Exception as e:
                        print(f"❌ Failed to generate {account_info['account_name']}/{region}/{project_config['project_name']}: {e}")
                        failed_count += 1
        
        print(f"\n📊 Bulk Generation Summary:")
        print(f"   ✅ Successfully generated: {generated_count}")
        print(f"   ❌ Failed: {failed_count}")
        print(f"   📋 Total: {generated_count + failed_count}")
    
    def _find_account_by_key(self, account_key: str) -> Dict:
        """Find account info by account ID or name"""
        accounts = self.accounts_config.get('accounts', {})
        
        for acc_id, acc_data in accounts.items():
            if (acc_id == account_key or 
                acc_data.get('account_name') == account_key or 
                acc_data.get('account_id') == account_key):
                return {
                    'account_id': acc_data.get('account_id', acc_id),
                    'account_name': acc_data.get('account_name', account_key),
                    'environment': acc_data.get('environment', 'development'),
                    'regions': acc_data.get('regions', [])
                }
        return None
    
    def _validate_region_for_account(self, account_info: Dict, region: str) -> bool:
        """Validate if region is available for the account"""
        available_regions = account_info.get('regions', [])
        return not available_regions or region in available_regions
    
    def _generate_deployment(self, account_info: Dict, region: str, template_type: str, project_details: Dict, bucket_config: Dict):
        """Generate the deployment files"""
        print(f"\n🔧 Generating S3 deployment...")
        
        # Load template (always use s3-bucket.tfvars)
        template_file = self.templates_dir / "s3-bucket.tfvars"
        if not template_file.exists():
            print(f"❌ Template file not found: {template_file}")
            return
        
        with open(template_file, 'r') as f:
            template_content = f.read()
        
        # Prepare substitution variables
        substitutions = self._prepare_substitutions(account_info, region, project_details, bucket_config)
        
        # Apply substitutions
        generated_content = self._apply_substitutions(template_content, substitutions)
        
        # Create output structure
        output_dir = self._create_output_structure(account_info, region, project_details['project_name'])
        
        # Write tfvars file (name it after the project for consistency)
        output_file = output_dir / f"{project_details['project_name']}.tfvars"
        with open(output_file, 'w') as f:
            f.write(generated_content)
        
        # Generate policy file
        self._generate_policy_file(account_info, region, project_details, bucket_config, output_dir)
        
        print(f"✅ Generated deployment:")
        print(f"   📄 {output_file}")
        print(f"   📋 Account: {account_info['account_name']} ({account_info['account_id']})")
        print(f"   🌍 Region: {region}")
        print(f"   📦 Bucket: {project_details['bucket_name_base']}")
    
    def _prepare_substitutions(self, account_info: Dict, region: str, project_details: Dict, bucket_config: Dict) -> Dict:
        """Prepare all substitution variables with proper AWS naming conventions"""
        region_code = self.region_codes.get(region, region.replace('-', ''))
        

        # Extract first 3 letters from account name
        account_prefix = account_info['account_name'][:3].lower()
        
        # Check if bucket_name_base already contains region codes or environment indicators
        bucket_name_base = project_details['bucket_name_base']
        current_region_code = region_code
        # Shorten environment names for bucket naming
        env_mapping = {
            'production': 'prd',
            'development': 'dev', 
            'staging': 'stg',
            'testing': 'tst',
            'sandbox': 'sbx'
        }
        
        current_env = account_info['environment']
        short_env = env_mapping.get(current_env.lower(), current_env.lower()[:3])
        
        # Always use the full naming convention: {account-prefix}-{project}-{region-code}-{environment}
        bucket_name = f"{account_prefix}-{bucket_name_base}-{region_code}-{short_env}"
        print(f"📝 Full naming convention applied: {account_prefix}-{bucket_name_base}-{region_code}-{short_env}")

        
        substitutions = {
            # Generation info
            'GENERATION_DATE': datetime.now().isoformat(),
            
            # Account info
            'ACCOUNT_ID': account_info['account_id'],
            'ACCOUNT_NAME': account_info['account_name'],
            'ENVIRONMENT': account_info['environment'],
            
            # Location info
            'REGION': region,
            'REGION_CODE': region_code,
            
            # Project info
            'PROJECT_NAME': project_details['project_name'],
            'BUCKET_KEY': project_details['bucket_name_base'],
            'BUCKET_NAME': bucket_name,
            'OWNER': project_details.get('owner', ''),
            'COST_CENTER': project_details.get('cost_center', ''),
            
            # Bucket configuration
            'VERSIONING_ENABLED': str(bucket_config['versioning_enabled']).lower(),
            'FORCE_DESTROY': str(bucket_config['force_destroy']).lower(),
            
            # Security configuration - build full IAM role ARN from role name
            'IAM_ROLE_ARN': f"arn:aws:iam::{account_info['account_id']}:role/{bucket_config.get('iam_role_name', 'REPLACE-WITH-YOUR-ROLE')}",
            
            # VPC Endpoint configuration
            'VPC_ENDPOINT_ID': bucket_config.get('policy_endpoint', 'vpce-XXXXXXXX'),
            'VPC_ENDPOINT_ID_1': bucket_config.get('interface_endpoint', 'vpce-interface-XXXXXXXX'),  # Interface endpoint
            'VPC_ENDPOINT_ID_2': bucket_config.get('gateway_endpoint', 'vpce-gateway-XXXXXXXX'),    # Gateway endpoint
            'VPC_INTERFACE_ENDPOINT': bucket_config.get('interface_endpoint', 'vpce-interface-XXXXXXXX'),
            'VPC_GATEWAY_ENDPOINT': bucket_config.get('gateway_endpoint', 'vpce-gateway-XXXXXXXX'),
            'VPC_ENDPOINT_TYPE': bucket_config.get('endpoint_type', 'interface'),
            'AUTHORIZED_ROLE_ARN': f"arn:aws:iam::{account_info['account_id']}:role/{bucket_config.get('iam_role_name', 'TerraformExecutionRole')}",
            
            # KMS configuration
            'KMS_KEY_ID': bucket_config.get('kms_key_id', ''),
        }
        
        # Add bucket-specific configurations
        for key, value in bucket_config.items():
            if isinstance(value, bool):
                substitutions[key.upper()] = str(value).lower()
            else:
                substitutions[key.upper()] = str(value)
        
        return substitutions
    
    def _apply_substitutions(self, content: str, substitutions: Dict) -> str:
        """Apply variable substitutions to template content"""
        for key, value in substitutions.items():
            placeholder = f"{{{{{key}}}}}"
            content = content.replace(placeholder, str(value))
        
        return content
    
    def _create_output_structure(self, account_info: Dict, region: str, project_name: str) -> Path:
        """Create output directory structure following the expected pattern"""
        output_dir = self.project_root / "Accounts" / account_info['account_name'] / region / project_name
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir
    
    def _generate_policy_file(self, account_info: Dict, region: str, project_details: Dict, bucket_config: Dict, output_dir: Path):
        """Generate corresponding policy file"""
        policy_template_file = self.templates_dir / "s3-bucket-policy.json"
        if not policy_template_file.exists():
            print(f"⚠️  Policy template not found: {policy_template_file}")
            return
        
        with open(policy_template_file, 'r') as f:
            policy_content = f.read()
        
        # Prepare policy substitutions
        substitutions = self._prepare_substitutions(account_info, region, project_details, bucket_config)
        
        # Apply substitutions
        generated_policy = self._apply_substitutions(policy_content, substitutions)
        
        # Write policy file (name it after the project for consistency)
        policy_file = output_dir / f"{project_details['project_name']}.json"
        with open(policy_file, 'w') as f:
            f.write(generated_policy)
        
        print(f"   📜 {policy_file}")

    def _find_account_by_key(self, account_key: str) -> Dict:
        """Find account info by name or ID"""
        accounts = self.accounts_config.get('accounts', {})
        
        for acc_id, acc_data in accounts.items():
            if (acc_id == account_key or 
                acc_data.get('account_name') == account_key or 
                acc_data.get('account_id') == account_key):
                return {
                    'account_id': acc_data.get('account_id', acc_id),
                    'account_name': acc_data.get('account_name', account_key),
                    'environment': acc_data.get('environment', 'development'),
                    'regions': acc_data.get('regions', [])
                }
        return None

    def _is_region_valid_for_account(self, account_info: Dict, region: str) -> bool:
        """Check if region is valid for the account"""
        if not account_info.get('regions'):
            return True  # No region restriction
        return region in account_info['regions']

    def cli_based_generation(self, args):
        """Command-line based generation"""
        print("🚀 Enhanced S3 Generator (CLI Mode)")
        print("=" * 45)
        
        # Find account info
        account_info = self._find_account_by_key(args.account)
        if not account_info:
            print(f"❌ Account '{args.account}' not found in accounts.yaml")
            return
        
        print(f"📋 Account: {account_info['account_name']} ({account_info['account_id']})")
        print(f"🌍 Region: {args.region}")
        print(f"📦 Project: {args.project}")
        print(f"🪣 Bucket Base: {args.bucket_base}")

        if not args.owner or not args.cost_center or not args.kms_key_id:
            print("❌ CLI mode requires --owner, --cost-center, and --kms-key-id arguments.")
            return
        
        # Prepare project details
        project_details = {
            'project_name': args.project,
            'bucket_name_base': args.bucket_base,
            'owner': args.owner.strip(),
            'cost_center': args.cost_center.strip()
        }
        
        # Default bucket configuration
        bucket_config = {
            'description': f'Secure S3 bucket for {args.project}',
            'versioning_enabled': True,
            'force_destroy': False,
            'encryption_type': 'kms',
            'iam_role_name': 'TerraformExecutionRole',
            'kms_key_id': args.kms_key_id.strip()
        }
        
        # VPC endpoint configuration
        vpc_endpoints = self.accounts_config.get('vpc_interface_endpoints', {})
        interface_endpoint = vpc_endpoints.get(args.region, f"vpce-{args.region.replace('-', '')}-interface-s3-shared")
        
        bucket_config.update({
            'interface_endpoint': interface_endpoint,
            'gateway_endpoint': f"vpce-{args.region.replace('-', '')}-gateway-XXXXXXXX",
            'policy_endpoint': interface_endpoint,
            'endpoint_type': 'interface'
        })
        
        # Generate deployment
        self._generate_deployment(account_info, args.region, args.template, project_details, bucket_config)

    def bulk_generation_from_config(self, config_file: str):
        """Bulk generation from configuration file"""
        print("🚀 Enhanced S3 Bulk Generator")
        print("=" * 40)
        
        try:
            with open(config_file, 'r') as f:
                bulk_config = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"❌ Error loading bulk config: {e}")
            return
        
        # Validate bulk configuration
        required_fields = ['accounts', 'regions', 'projects']
        missing_fields = [field for field in required_fields if field not in bulk_config]
        if missing_fields:
            print(f"❌ Missing required fields in bulk config: {missing_fields}")
            return
        
        accounts = bulk_config['accounts']
        regions = bulk_config['regions'] 
        projects = bulk_config['projects']

        for i, project in enumerate(projects):
            required_fields = ['name', 'owner', 'cost_center']
            missing = [field for field in required_fields if field not in project or not str(project[field]).strip()]
            if missing:
                print(f"❌ Project entry {i} missing required fields: {missing}")
                return
            if not project.get('kms_key_id') and not project.get('kms_key_ids'):
                print(f"❌ Project entry {i} must include 'kms_key_id' or 'kms_key_ids'.")
                return
        
        total_deployments = len(accounts) * len(regions) * len(projects)
        print(f"📊 Total deployments to generate: {total_deployments}")
        print(f"   📋 Accounts: {len(accounts)} ({', '.join(accounts)})")
        print(f"   🌍 Regions: {len(regions)} ({', '.join(regions)})")
        print(f"   📦 Projects: {len(projects)}")
        print()
        
        generated_count = 0
        failed_count = 0
        
        for account_key in accounts:
            account_info = self._find_account_by_key(account_key)
            if not account_info:
                print(f"❌ Account '{account_key}' not found, skipping...")
                failed_count += len(regions) * len(projects)
                continue
            
            for region in regions:
                # Validate region for account if specified
                if not self._is_region_valid_for_account(account_info, region):
                    print(f"⚠️  Region '{region}' not valid for account '{account_key}', skipping...")
                    failed_count += len(projects)
                    continue
                
                for project_config in projects:
                    try:
                        owner = str(project_config.get('owner', '')).strip()
                        cost_center = str(project_config.get('cost_center', '')).strip()
                        kms_overrides = project_config.get('kms_key_ids', {}) or {}
                        kms_key_id = kms_overrides.get(region) or str(project_config.get('kms_key_id', '')).strip()

                        project_name = project_config.get('name', project_config.get('project_name'))
                        if not project_name:
                            raise ValueError("Bulk project entries must include 'name' or 'project_name'.")

                        if not owner or not cost_center or not kms_key_id:
                            raise ValueError("Bulk project entries must include owner, cost_center, and either kms_key_id or kms_key_ids per region.")

                        # Prepare project details
                        project_details = {
                            'project_name': project_name,
                            'bucket_name_base': project_config.get('bucket_base', project_name),
                            'owner': owner,
                            'cost_center': cost_center
                        }
                        
                        # Default bucket configuration with project-specific overrides
                        bucket_config = {
                            'description': project_config.get('description', f'Secure S3 bucket for {project_name}'),
                            'versioning_enabled': project_config.get('versioning_enabled', True),
                            'force_destroy': project_config.get('force_destroy', False),
                            'encryption_type': 'kms',
                            'iam_role_name': project_config.get('iam_role_name', 'TerraformExecutionRole'),
                            'kms_key_id': kms_key_id
                        }
                        
                        # VPC endpoint configuration
                        vpc_endpoints = self.accounts_config.get('vpc_interface_endpoints', {})
                        interface_endpoint = vpc_endpoints.get(region, f"vpce-{region.replace('-', '')}-interface-s3-shared")
                        
                        bucket_config.update({
                            'interface_endpoint': interface_endpoint,
                            'gateway_endpoint': f"vpce-{region.replace('-', '')}-gateway-XXXXXXXX",
                            'policy_endpoint': interface_endpoint,
                            'endpoint_type': 'interface'
                        })
                        
                        # Generate deployment
                        self._generate_deployment(account_info, region, 's3-bucket', project_details, bucket_config)
                        generated_count += 1
                        
                    except Exception as e:
                        print(f"❌ Failed to generate {account_key}/{region}/{project_config['name']}: {e}")
                        failed_count += 1
        
        print(f"\n📊 Bulk Generation Summary:")
        print(f"   ✅ Generated: {generated_count}")
        print(f"   ❌ Failed: {failed_count}")
        print(f"   📋 Total: {generated_count + failed_count}")
def main():
    parser = argparse.ArgumentParser(
        description="Enhanced S3 Terraform tfvars Generator with Multi-Account/Region Support",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive mode (default)
  python enhanced-s3-generator.py
  
  # JSON configuration mode  
  python enhanced-s3-generator.py --config my-s3-config.json
  
  # Bulk generation mode
  python enhanced-s3-generator.py --bulk-config bulk-s3-deployments.json
  
  # Single deployment via CLI
  python enhanced-s3-generator.py --account arj-wkld-a-prd --region us-east-1 --project my-app --bucket-base my-app-data
        """
    )
    
    parser.add_argument("--config", "-c", help="JSON configuration file for single deployment")
    parser.add_argument("--bulk-config", help="JSON configuration file for bulk multi-account/region deployments")
    parser.add_argument("--interactive", "-i", action="store_true", help="Force interactive mode")
    parser.add_argument("--account", help="Account name or ID")
    parser.add_argument("--region", help="AWS region")
    parser.add_argument("--project", help="Project name")
    parser.add_argument("--bucket-base", help="Bucket name base")
    parser.add_argument("--owner", help="Owner or team for tagging (required in CLI mode)")
    parser.add_argument("--cost-center", help="Cost center identifier (required in CLI mode)")
    parser.add_argument("--kms-key-id", help="Full KMS key ARN to use for bucket encryption (required in CLI mode)")
    parser.add_argument("--template", help="Template type", default="s3-bucket")
    
    args = parser.parse_args()
    
    try:
        generator = S3TfvarsGenerator()
        
        # Determine mode based on arguments
        if args.bulk_config:
            # Bulk generation mode
            generator.bulk_generation_from_config(args.bulk_config)
        elif args.config:
            # JSON configuration mode
            if args.interactive:
                print("⚠️  --interactive flag ignored when using --config")
            generator.json_based_generation(args.config)
        elif all([args.account, args.region, args.project, args.bucket_base]):
            # Command-line arguments mode
            generator.cli_based_generation(args)
        elif args.interactive or not any([args.account, args.region, args.project, args.bucket_base]):
            # Interactive mode (default)
            generator.interactive_generation()
        else:
            # Missing required arguments
            print("❌ Missing required arguments for CLI mode.")
            print("💡 Required: --account, --region, --project, --bucket-base, --owner, --cost-center, --kms-key-id")
            print("💡 Or use --config <file.json> for JSON configuration")
            print("💡 Or use --bulk-config <file.json> for bulk generation") 
            print("💡 Or run without arguments for interactive mode")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n🛑 Generation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"💥 Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()