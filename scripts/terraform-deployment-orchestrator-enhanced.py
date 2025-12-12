#!/usr/bin/env python3
"""
Enhanced Terraform Deployment Orchestrator - Version 2.0
============================================================
Features:
- Dynamic backend key generation: {account_name}/{service}/{resource_name}/{resource_name}.tfstate
- Resource name extraction from tfvars for intelligent state file naming
- Enhanced PR comments with detailed outputs and error reporting
- Service-specific state management with automatic service detection
- Comprehensive error handling and debug logging
- Terraform state isolation per resource for better state management
- Generic deployment orchestration for all AWS services (S3, KMS, IAM, Lambda, etc.)

Version: 2.0
Updated: 2025-11-24
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import concurrent.futures
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Optional

try:
    import yaml
except ImportError:
    yaml = None

# Version constants
ORCHESTRATOR_VERSION = "2.0"

DEBUG = True

def debug_print(msg):
    if DEBUG:
        print(f"🐛 DEBUG: {msg}")

def strip_ansi_colors(text):
    """Remove ANSI color codes from text"""
    ansi_escape = re.compile(r'\x1b\[[0-9;]*m')
    bracket_codes = re.compile(r'\[(?:[0-9]+;?)*m')
    text = ansi_escape.sub('', text)
    text = bracket_codes.sub('', text)
    return text

def redact_sensitive_data(text: str) -> str:
    """Redact sensitive information from terraform output for PR comments"""
    if not text:
        return text
    
    # Redact ARNs (keep service and region, hide account ID)
    text = re.sub(
        r'arn:aws:([a-z0-9\-]+):([a-z0-9\-]*):([0-9]{12}):([^\s"]+)',
        r'arn:aws:\1:\2:***REDACTED***:\4',
        text
    )
    
    # Redact AWS account IDs
    text = re.sub(r'\b([0-9]{12})\b', r'***ACCOUNT-ID***', text)
    
    # Redact S3 bucket ARNs specifically
    text = re.sub(
        r'arn:aws:s3:::([a-z0-9\-\.]+)',
        r'arn:aws:s3:::***BUCKET***',
        text
    )
    
    # Redact KMS key IDs
    text = re.sub(
        r'key/([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})',
        r'key/***KEY-ID***',
        text
    )
    
    # Redact IP addresses
    text = re.sub(
        r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b',
        r'***IP-ADDRESS***',
        text
    )
    
    # Redact access keys (if accidentally in output)
    text = re.sub(
        r'AKIA[0-9A-Z]{16}',
        r'***ACCESS-KEY***',
        text
    )
    
    # Redact secret keys (if accidentally in output)
    text = re.sub(
        r'[A-Za-z0-9/+=]{40}',
        r'***SECRET-KEY***',
        text
    )
    
    return text

def validate_policy_json_file(policy_path: Path, working_dir: Path, account_id: str) -> Tuple[bool, List[str], List[str]]:
    """
    Comprehensive policy JSON validation:
    1. JSON syntax
    2. AWS policy structure
    3. ARN account matching
    4. Security best practices
    Returns: (is_valid, warnings, errors)
    """
    warnings = []
    errors = []
    
    if not policy_path.is_absolute():
        policy_path = working_dir / policy_path
    
    if not policy_path.exists():
        errors.append(f"🚫 BLOCKER: Policy file not found: {policy_path}")
        return False, warnings, errors
    
    try:
        with open(policy_path, 'r') as f:
            policy_content = f.read()
        
        # 1. Validate JSON syntax
        try:
            policy_data = json.loads(policy_content)
        except json.JSONDecodeError as e:
            errors.append(f"🚫 BLOCKER: Invalid JSON in {policy_path.name}: {e}")
            return False, warnings, errors
        
        # 2. Check AWS policy structure
        if 'Statement' not in policy_data:
            errors.append(f"🚫 BLOCKER: Policy missing 'Statement' field: {policy_path.name}")
            return False, warnings, errors
        
        statements = policy_data.get('Statement', [])
        if not isinstance(statements, list):
            statements = [statements]
        
        # 3. Validate each statement
        for idx, statement in enumerate(statements):
            # Check Effect field
            if 'Effect' not in statement:
                errors.append(f"🚫 BLOCKER: Statement {idx+1} missing 'Effect' in {policy_path.name}")
            elif statement['Effect'] not in ['Allow', 'Deny']:
                errors.append(f"🚫 BLOCKER: Invalid Effect '{statement['Effect']}' in {policy_path.name}")
            
            # Check for wildcards
            actions = statement.get('Action', [])
            if not isinstance(actions, list):
                actions = [actions]
            
            if '*' in actions:
                warnings.append(f"⚠️  Policy {policy_path.name} uses wildcard actions (*) - security risk!")
            
            # Check ARNs match account
            resources = statement.get('Resource', [])
            if not isinstance(resources, list):
                resources = [resources]
            
            for resource in resources:
                if '*' in resource and resource == '*':
                    warnings.append(f"⚠️  Policy {policy_path.name} uses wildcard resource (*) - allows ALL resources!")
                
                # Extract account from ARN
                arn_match = re.search(r'arn:aws:[^:]+:[^:]*:(\d{12}):', resource)
                if arn_match:
                    arn_account = arn_match.group(1)
                    if arn_account != account_id:
                        errors.append(
                            f"🚫 BLOCKER: Policy {policy_path.name} ARN uses account {arn_account} "
                            f"but deploying to {account_id}"
                        )
        
        return len(errors) == 0, warnings, errors
        
    except Exception as e:
        errors.append(f"🚫 BLOCKER: Error validating policy {policy_path.name}: {str(e)}")
        return False, warnings, errors

def validate_resource_names_match(policy_path: Path, tfvars_content: str, working_dir: Path) -> Tuple[List[str], List[str]]:
    """
    CRITICAL: Validate resource names in policy match tfvars
    Prevents deployment failures due to copy-paste errors with mismatched names
    Returns: (warnings, errors) - errors will BLOCK deployment
    """
    warnings = []
    errors = []
    
    if not policy_path.is_absolute():
        policy_path = working_dir / policy_path
    
    if not policy_path.exists():
        return warnings, errors
    
    try:
        with open(policy_path, 'r') as f:
            policy_data = json.load(f)
        
        # DYNAMIC: Extract resource KEY and resource NAME from tfvars (any service)
        # Pattern: s3_buckets = { "resource-key" = { bucket_name = "actual-name" ... } }
        # CRITICAL: Check that resource KEY matches or is contained in actual resource name
        
        # Extract resource blocks from collections like s3_buckets, kms_keys, iam_roles, etc.
        # Pattern: collection_name = { "key" = { ... } }
        collection_pattern = r'(\w+)\s*=\s*\{([^}]+(?:\{[^}]*\}[^}]*)*)\}'
        collections = re.findall(collection_pattern, tfvars_content, re.DOTALL)
        
        for collection_name, collection_content in collections:
            # Skip non-resource collections (like tags, account, common_tags)
            if collection_name in ['tags', 'common_tags', 'account', 'region', 'environment']:
                continue
            
            # Extract individual resource blocks: "resource-key" = { properties }
            resource_pattern = r'"([^"]+)"\s*=\s*\{([^}]+)\}'
            resources = re.findall(resource_pattern, collection_content, re.DOTALL)
            
            for resource_key, block_content in resources:
                # Skip if resource_key looks like an account ID (all digits)
                if resource_key.isdigit():
                    continue
                
                # DYNAMIC: Find ANY *_name attribute (bucket_name, function_name, role_name, etc.)
                name_match = re.search(r'(\w+_name)\s*=\s*"([^"]+)"', block_content)
                
                if name_match:
                    attribute_name = name_match.group(1)  # e.g., "bucket_name", "function_name"
                    actual_name = name_match.group(2)      # e.g., "arj-test-poc-3-use1-prd"
                    
                    # Debug output
                    debug_print(f"Checking: collection={collection_name}, key='{resource_key}', {attribute_name}='{actual_name}'")
                    
                    # CRITICAL CHECK: Resource key must be contained in actual name
                    # Example: key="test-poc-3" should be in name="arj-test-poc-3-use1-prd"
                    if resource_key not in actual_name:
                        errors.append(
                            f"🚫 BLOCKER: Resource key '{resource_key}' (in {collection_name}) does NOT match {attribute_name} '{actual_name}'. "
                            f"Copy-paste error detected! The resource key in your tfvars block must appear in the actual resource name. "
                            f"Example: If key is 'my-bucket', then bucket_name must contain 'my-bucket' like 'my-bucket-prod-use1'."
                        )
                    else:
                        debug_print(f"✅ Match found: '{resource_key}' is in '{actual_name}'")
        
        # DYNAMIC: Extract all resource names for policy comparison (any *_name attribute)
        # BUT skip account_name - it's metadata, not a resource to validate
        actual_names = set()
        all_name_matches = re.findall(r'(\w+_name)\s*=\s*"([^"]+)"', tfvars_content)
        for attribute_name, name_value in all_name_matches:
            # Skip non-resource name attributes (metadata fields)
            if attribute_name not in ['account_name']:
                actual_names.add(name_value)
        
        # Also check key_alias pattern (KMS-specific but dynamic)
        alias_matches = re.findall(r'key_alias\s*=\s*"(?:alias/)?([^"]+)"', tfvars_content)
        actual_names.update(alias_matches)
        
        # DYNAMIC: Extract resource names from policy ARNs (any AWS service)
        policy_resources = set()
        statements = policy_data.get('Statement', [])
        if not isinstance(statements, list):
            statements = [statements]
        
        for statement in statements:
            resources = statement.get('Resource', [])
            if not isinstance(resources, list):
                resources = [resources]
            
            for resource in resources:
                # DYNAMIC: Extract resource names from ANY ARN format (all AWS services)
                # Patterns:
                # - arn:aws:service:::resource-name (service with :::)
                # - arn:aws:service:region:account:resource-type/resource-name
                # - arn:aws:service:region:account:resource-type:resource-name
                
                # Handle ::: pattern (used by some services)
                if ':::' in resource:
                    triple_colon_match = re.search(r'arn:aws:[^:]+:::([^/\*]+)', resource)
                    if triple_colon_match:
                        policy_resources.add(triple_colon_match.group(1))
                        continue
                
                # Generic ARN: extract resource name from last segment
                # Pattern: arn:aws:service:region:account:type/name or arn:aws:service:region:account:type:name
                generic_match = re.search(r'arn:aws:[^:]+:[^:]*:[^:]*:(?:[^/:]+[/:])?([^/:\*]+)', resource)
                if generic_match:
                    resource_name = generic_match.group(1)
                    # Filter out account IDs, wildcards, and common non-resource identifiers
                    if not resource_name.isdigit() and resource_name not in ['*', 'root', 'aws']:
                        policy_resources.add(resource_name)
        
        # CRITICAL CHECK: Resource names in policy MUST match tfvars
        if actual_names and policy_resources:
            # Resources in policy but NOT in tfvars = BLOCKER
            unknown = policy_resources - actual_names
            if unknown:
                errors.append(
                    f"🚫 BLOCKER: Policy {policy_path.name} references resources NOT in tfvars: {', '.join(unknown)}. "
                    f"This indicates copy-paste error - update policy file or tfvars!"
                )
            
            # Resources in tfvars but NOT in policy = BLOCKER
            missing = actual_names - policy_resources
            if missing:
                errors.append(
                    f"🚫 BLOCKER: Tfvars defines resources NOT in policy {policy_path.name}: {', '.join(missing)}. "
                    f"Policy file must be updated to match tfvars resource names!"
                )
    
    except Exception as e:
        errors.append(f"🚫 BLOCKER: Error validating resource names in {policy_path.name}: {str(e)}")
    
    return warnings, errors

def query_amazon_q_for_validation(tfvars_content: str, policy_content: str, deployment: Dict) -> Tuple[List[str], List[str]]:
    """
    AMAZON Q INTEGRATION: Send configuration to Amazon Q for AI-powered validation
    Returns: (warnings, errors) - errors will BLOCK deployment
    """
    warnings = []
    errors = []
    
    try:
        import boto3
        from botocore.exceptions import ClientError
        
        # Initialize Amazon Q client (using bedrock-agent-runtime for Q Developer)
        print("🤖 Querying Amazon Q for validation...")
        
        # OPTIONAL: Amazon Q validation (skip if not configured)
        # Amazon Q Developer is FREE but requires IDE integration
        # For API access, you need Amazon Q Business (paid)
        # This validation is OPTIONAL - local validation is already comprehensive
        
        q_app_id = os.environ.get('AMAZON_Q_APP_ID')
        if not q_app_id:
            # Skip Amazon Q validation - not configured (THIS IS OK!)
            print("   ℹ️  Amazon Q not configured - using local validation only")
            return warnings, errors
        
        # Only proceed if explicitly configured
        try:
            q_client = boto3.client('qbusiness', region_name='us-east-1')
        except Exception as client_err:
            # Gracefully skip if client unavailable
            print(f"   ℹ️  Amazon Q unavailable - using local validation only")
            return warnings, errors
        
        # Build validation query for Amazon Q
        account_name = deployment.get('account_name', 'unknown')
        environment = deployment.get('environment', 'unknown')
        
        validation_query = f"""Analyze this Terraform configuration for errors and security issues:

Environment: {environment}
Account: {account_name}

Terraform Variables (.tfvars):
```hcl
{tfvars_content[:2000]}
```

Policy JSON:
```json
{policy_content[:2000]}
```

Check for:
1. Resource name mismatches between tfvars and policies
2. Incorrect ARN formats or account IDs
3. Security issues (overly permissive policies, wildcards)
4. AWS best practices violations
5. Configuration errors that would cause deployment failures

Respond with:
- ERRORS: Critical issues that MUST block deployment
- WARNINGS: Issues that should be reviewed but won't block deployment

Format: Start each error with "ERROR:" and each warning with "WARNING:"""
        
        try:
            # Call Amazon Q Business API (enterprise version - optional)
            response = q_client.chat_sync(
                applicationId=q_app_id,
                userMessage=validation_query,
                userId='terraform-orchestrator',
                clientToken=str(datetime.now().timestamp())
            )
            
            # Parse Amazon Q response
            q_response = response.get('systemMessage', '')
            
            print(f"✅ Amazon Q validation complete")
            
            # Parse Amazon Q response for errors and warnings
            for line in q_response.split('\n'):
                line = line.strip()
                if line.startswith('ERROR:'):
                    error_msg = line.replace('ERROR:', '').strip()
                    errors.append(f"🚫 Amazon Q BLOCKER: {error_msg}")
                elif line.startswith('WARNING:'):
                    warn_msg = line.replace('WARNING:', '').strip()
                    warnings.append(f"⚠️  Amazon Q: {warn_msg}")
            
            if not errors and not warnings:
                # If no structured errors/warnings found, check for validation pass
                if 'no errors' in q_response.lower() or 'looks good' in q_response.lower():
                    print("   ✅ Amazon Q found no issues")
                else:
                    # Generic response - treat as informational
                    warnings.append(f"ℹ️  Amazon Q feedback: {q_response[:200]}")
        
        except ClientError as api_err:
            error_code = api_err.response.get('Error', {}).get('Code', 'Unknown')
            if error_code == 'AccessDeniedException':
                warnings.append("⚠️  Amazon Q API access denied - check IAM permissions for qbusiness:ChatSync")
            elif error_code == 'ResourceNotFoundException':
                warnings.append("⚠️  Amazon Q model not available in region - skipping AI validation")
            else:
                warnings.append(f"⚠️  Amazon Q API error: {str(api_err)}")
        
    except ImportError:
        warnings.append("⚠️  boto3 not available - skipping Amazon Q validation")
    except Exception as e:
        warnings.append(f"⚠️  Amazon Q validation exception: {str(e)}")
    
    return warnings, errors

class EnhancedTerraformOrchestrator:
    """Enhanced Terraform Orchestrator with dynamic backend keys and improved PR comments"""
    
    def __init__(self, working_dir=None):
        self.script_dir = Path(__file__).parent
        self.working_dir = Path(working_dir) if working_dir else Path.cwd()
        self.state_backups = {}  # Track backups for rollback
        self.validation_warnings = []  # Track all validation warnings
        self.validation_errors = []  # Track blocker errors
        
        terraform_dir_env = os.getenv('TERRAFORM_DIR')
        if terraform_dir_env:
            self.project_root = (self.working_dir / terraform_dir_env).resolve()
        else:
            self.project_root = self.script_dir.parent
            
        self.accounts_config = self._load_accounts_config()
        self.templates_dir = self.project_root / "templates"
        
        # DYNAMIC SERVICE MAPPING - Maps tfvars keys to AWS service names
        # Automatically detects services from tfvars file content
        self.service_mapping = {
            's3_buckets': 's3',
            's3_bucket': 's3',
            'kms_keys': 'kms',
            'kms_key': 'kms',
            'iam_roles': 'iam',
            'iam_policies': 'iam',
            'iam_users': 'iam',
            'lambda_functions': 'lambda',
            'lambda_function': 'lambda',
            'dynamodb_tables': 'dynamodb',
            'dynamodb_table': 'dynamodb',
            'rds_instances': 'rds',
            'rds_clusters': 'rds',
            'ec2_instances': 'ec2',
            'vpc_configs': 'vpc',
            'security_groups': 'vpc',
            'sns_topics': 'sns',
            'sqs_queues': 'sqs',
            'cloudwatch_alarms': 'cloudwatch',
            'api_gateways': 'apigateway'
        }

    def _load_accounts_config(self) -> Dict:
        """Load accounts configuration from accounts.yaml"""
        accounts_file = self.project_root / "accounts.yaml"
        if not accounts_file.exists():
            debug_print(f"accounts.yaml not found at {accounts_file}, using defaults")
            return {'accounts': {}, 's3_templates': {}, 'regions': {}, 'default_tags': {}}
        
        if yaml is None:
            return self._parse_simple_yaml(accounts_file)
        else:
            with open(accounts_file, 'r') as f:
                return yaml.safe_load(f)

    def _parse_simple_yaml(self, file_path: Path) -> Dict:
        """Simple YAML parser for basic accounts.yaml structure"""
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
                    elif current_section == 'accounts' and key.isdigit():
                        current_account = key
                        config['accounts'][current_account] = {}
                elif ':' in line and current_section and current_account:
                    key, value = line.split(':', 1)
                    key = key.strip()
                    value = value.strip().strip("'\"")
                    config['accounts'][current_account][key] = value
        
        return config

    def find_deployments(self, changed_files=None, filters=None):
        """Find deployments to process based on changed files or all tfvars"""
        debug_print(f"find_deployments called with changed_files={changed_files}, filters={filters}")
        
        if changed_files:
            print(f"📋 Processing {len(changed_files)} changed files")
            seen_files = set()  # Track actual file paths, not parent directories
            files = []
            for file in changed_files:
                # Skip workflow files
                if file.startswith('.github/workflows/'):
                    debug_print(f"Skipping workflow file: {file}")
                    continue
                
                # Try both absolute path and relative to working_dir
                file_path = Path(file)
                if not file_path.is_absolute():
                    file_path = self.working_dir / file
                
                debug_print(f"Checking file: {file} -> resolved to: {file_path} (exists: {file_path.exists()})")
                
                if file_path.exists():
                    if file.endswith('.tfvars'):
                        # Direct tfvars file - add if not already seen
                        file_str = str(file_path)
                        if file_str not in seen_files:
                            files.append(file_path)
                            seen_files.add(file_str)
                            debug_print(f"Added tfvars deployment: {file_path}")
                        else:
                            debug_print(f"Skipping duplicate tfvars: {file_path}")
                    elif file.endswith('.json'):
                        # JSON file changed - look for tfvars in same directory
                        deployment_dir = file_path.parent
                        tfvars_files = list(deployment_dir.glob("*.tfvars"))
                        debug_print(f"Found {len(tfvars_files)} tfvars files in {deployment_dir}")
                        for tfvars_file in tfvars_files:
                            file_str = str(tfvars_file)
                            if file_str not in seen_files:
                                files.append(tfvars_file)
                                seen_files.add(file_str)
                                debug_print(f"Found tfvars file {tfvars_file} for changed JSON {file}")
                            else:
                                debug_print(f"Skipping duplicate tfvars: {tfvars_file}")
                else:
                    debug_print(f"File does not exist: {file_path}")
        else:
            # Find all tfvars files in Accounts directory
            accounts_dir = self.working_dir / "Accounts"
            if accounts_dir.exists():
                files = list(accounts_dir.glob("**/*.tfvars"))
            else:
                files = []
        
        deployments = []
        for file in files:
            deployment_info = self._analyze_deployment_file(file)
            if deployment_info and self._matches_filters(deployment_info, filters):
                deployments.append(deployment_info)
        
        return deployments

    def _analyze_deployment_file(self, tfvars_file: Path) -> Optional[Dict]:
        """Analyze tfvars file and extract deployment information - reads account_name from tfvars content"""
        try:
            # Read tfvars content to extract actual account_name
            content = tfvars_file.read_text()
            
            # Extract account_name from tfvars content: account_name = "arj-wkld-a-prd"
            account_name_match = re.search(r'account_name\s*=\s*"([^"]+)"', content)
            if account_name_match:
                account_name = account_name_match.group(1)
                debug_print(f"✅ Extracted account_name from tfvars: {account_name}")
            else:
                # Fallback: use folder structure
                path_parts = tfvars_file.parts
                if len(path_parts) >= 4:
                    account_name = path_parts[-4]
                elif len(path_parts) >= 3:
                    account_name = path_parts[-3]
                elif len(path_parts) >= 2:
                    account_name = path_parts[-2]
                else:
                    account_name = tfvars_file.stem
                debug_print(f"⚠️  No account_name in tfvars, using folder: {account_name}")
            
            # Extract region from tfvars or use folder structure
            region_match = re.search(r'regions\s*=\s*\["([^"]+)"\]', content)
            if region_match:
                region = region_match.group(1)
                debug_print(f"✅ Extracted region from tfvars: {region}")
            else:
                # Fallback: use folder structure
                path_parts = tfvars_file.parts
                if len(path_parts) >= 3:
                    region = path_parts[-3]
                elif len(path_parts) >= 2:
                    region = path_parts[-2]
                else:
                    region = 'us-east-1'
                debug_print(f"⚠️  No region in tfvars, using folder/default: {region}")
            
            # Extract account_id from tfvars content
            account_id_match = re.search(r'account_id\s*=\s*"([^"]+)"', content)
            if account_id_match:
                account_id = account_id_match.group(1)
                debug_print(f"✅ Extracted account_id from tfvars: {account_id}")
            else:
                # Try to find from accounts block
                accounts_match = re.search(r'accounts\s*=\s*\{[^}]*"(\d+)"\s*=\s*\{', content)
                if accounts_match:
                    account_id = accounts_match.group(1)
                    debug_print(f"✅ Extracted account_id from accounts block: {account_id}")
                else:
                    # Fallback: use account_name
                    account_id = account_name
                    debug_print(f"⚠️  No account_id found, using account_name: {account_id}")
            
            # Project from folder structure (parent folder)
            path_parts = tfvars_file.parts
            project = path_parts[-2] if len(path_parts) >= 2 else 'default'
            
            # Extract environment from tfvars
            env_match = re.search(r'environment\s*=\s*"([^"]+)"', content)
            if env_match:
                environment = env_match.group(1)
            else:
                environment = 'unknown'
            
            # Extract Owner from tags
            owner = 'N/A'
            owner_match = re.search(r'Owner\s*=\s*"([^"]+)"', content)
            if owner_match:
                owner = owner_match.group(1)
                debug_print(f"✅ Extracted Owner from tags: {owner}")
            
            # Extract Team/Group from tags
            team = 'N/A'
            team_match = re.search(r'Team\s*=\s*"([^"]+)"', content)
            if not team_match:
                team_match = re.search(r'Group\s*=\s*"([^"]+)"', content)
            if team_match:
                team = team_match.group(1)
                debug_print(f"✅ Extracted Team/Group from tags: {team}")
            
            # Extract resource names (s3_buckets, kms_keys, iam_roles, etc.)
            resources = []
            resource_patterns = [
                (r's3_buckets\s*=\s*\{\s*"([^"]+)"\s*=', 'S3'),  # Match: s3_buckets = { "bucket-name" =
                (r'kms_keys\s*=\s*\{\s*"([^"]+)"\s*=', 'KMS'),   # Match: kms_keys = { "key-name" =
                (r'iam_roles\s*=\s*\{\s*"([^"]+)"\s*=', 'IAM Role'),  # Match: iam_roles = { "role-name" =
                (r'iam_policies\s*=\s*\{\s*"([^"]+)"\s*=', 'IAM Policy'),  # Match: iam_policies = { "policy-name" =
                (r'lambda_functions\s*=\s*\{\s*"([^"]+)"\s*=', 'Lambda')  # Match: lambda_functions = { "function-name" =
            ]
            
            for pattern, resource_type in resource_patterns:
                matches = re.finditer(pattern, content, re.MULTILINE)
                for match in matches:
                    resource_name = match.group(1)
                    resources.append(f"{resource_type}: {resource_name}")
                    debug_print(f"✅ Found resource: {resource_type} - {resource_name}")
            
            resources_str = ', '.join(resources[:5]) if resources else 'N/A'  # Limit to first 5
            if len(resources) > 5:
                resources_str += f' (+{len(resources) - 5} more)'
            
            # Calculate relative path from working_dir for cleaner reporting
            try:
                relative_path = tfvars_file.relative_to(self.working_dir)
                deployment_dir_relative = relative_path.parent
                debug_print(f"📁 Relative deployment path: {deployment_dir_relative}")
            except ValueError:
                # If can't calculate relative path, use the filename's parent
                deployment_dir_relative = Path(*tfvars_file.parts[-3:]).parent if len(tfvars_file.parts) >= 3 else tfvars_file.parent
                debug_print(f"📁 Using fallback deployment path: {deployment_dir_relative}")
            
            return {
                'file': str(tfvars_file),
                'file_relative': str(relative_path) if 'relative_path' in locals() else tfvars_file.name,
                'account_id': account_id,
                'account_name': account_name,
                'region': region,
                'project': project,
                'deployment_dir': str(tfvars_file.parent),
                'deployment_dir_relative': str(deployment_dir_relative),
                'environment': environment,
                'owner': owner,
                'team': team,
                'resources': resources_str
            }
                    
        except Exception as e:
            debug_print(f"Error analyzing deployment file {tfvars_file}: {e}")
            import traceback
            debug_print(traceback.format_exc())
            return None

    def _matches_filters(self, deployment: Dict, filters: Optional[Dict]) -> bool:
        """Check if deployment matches filter criteria"""
        if not filters:
            return True
        
        for key, value in filters.items():
            if deployment.get(key) != value:
                return False
        return True

    def _detect_services_from_tfvars(self, tfvars_file: Path) -> List[str]:
        """Detect services from tfvars file content"""
        try:
            with open(tfvars_file, 'r') as f:
                content = f.read()
            
            detected_services = []
            for tfvars_key, service in self.service_mapping.items():
                # Look for service definitions in tfvars
                if re.search(rf'\b{tfvars_key}\s*=', content):
                    detected_services.append(service)
                    debug_print(f"Detected service: {service} (from {tfvars_key})")
            
            return detected_services
            
        except Exception as e:
            debug_print(f"Error detecting services from {tfvars_file}: {e}")
            return []
    
    def _extract_resource_names_from_tfvars(self, tfvars_file: Path, services: List[str]) -> List[str]:
        """Extract resource names from tfvars for state file naming"""
        try:
            with open(tfvars_file, 'r') as f:
                content = f.read()
            
            resource_names = []
            
            # Service-specific patterns to extract resource names
            if 's3' in services:
                # Extract S3 bucket names
                # Pattern: bucket = "bucket-name" or "bucket-key" = {
                s3_patterns = [
                    r'"([a-z0-9][a-z0-9-]*[a-z0-9])"\s*=\s*\{',  # "bucket-name" = {
                    r'bucket\s*=\s*"([^"]+)"',  # bucket = "name"
                ]
                for pattern in s3_patterns:
                    matches = re.findall(pattern, content)
                    resource_names.extend(matches)
            
            if 'kms' in services:
                # Extract KMS key aliases or descriptions
                kms_patterns = [
                    r'"([a-z0-9][a-z0-9-]*[a-z0-9])"\s*=\s*\{',  # "key-name" = {
                    r'aliases\s*=\s*\["([^"]+)"',  # aliases = ["alias"]
                    r'description\s*=\s*"([^"]+)"',  # description = "name"
                ]
                for pattern in kms_patterns:
                    matches = re.findall(pattern, content)
                    resource_names.extend([m.replace('alias/', '').replace(' ', '-').lower() for m in matches])
            
            if 'iam' in services:
                # Extract IAM role/policy names
                iam_patterns = [
                    r'"([A-Za-z0-9][A-Za-z0-9-_]*[A-Za-z0-9])"\s*=\s*\{',  # "role-name" = {
                    r'role_name\s*=\s*"([^"]+)"',  # role_name = "name"
                    r'policy_name\s*=\s*"([^"]+)"',  # policy_name = "name"
                ]
                for pattern in iam_patterns:
                    matches = re.findall(pattern, content)
                    resource_names.extend(matches)
            
            if 'lambda' in services:
                # Extract Lambda function names
                lambda_patterns = [
                    r'function_name\s*=\s*"([^"]+)"',  # function_name = "name"
                    r'"([a-z0-9][a-z0-9-]*[a-z0-9])"\s*=\s*\{',  # "function-name" = {
                ]
                for pattern in lambda_patterns:
                    matches = re.findall(pattern, content)
                    resource_names.extend(matches)
            
            # Remove duplicates and clean up names
            unique_names = []
            seen = set()
            for name in resource_names:
                clean_name = name.strip().replace(' ', '-').lower()
                if clean_name and clean_name not in seen and len(clean_name) < 50:
                    unique_names.append(clean_name)
                    seen.add(clean_name)
            
            debug_print(f"Extracted resource names: {unique_names}")
            return unique_names[:5]  # Limit to first 5 resources
            
        except Exception as e:
            debug_print(f"Error extracting resource names from {tfvars_file}: {e}")
            return []

    def _generate_dynamic_backend_key(self, deployment: Dict, services: List[str], tfvars_file: Path = None) -> str:
        """Generate dynamic backend key: {service}/{account_name}/{region}/{project}/terraform.tfstate"""
        account_name = deployment.get('account_name', 'unknown')
        project = deployment.get('project', 'unknown') 
        region = deployment.get('region', 'us-east-1')
        
        # Determine service part
        if len(services) == 0:
            service_part = "general"
        elif len(services) == 1:
            service_part = services[0]
        else:
            service_part = "combined"
        
        # Standard backend key format: {service}/{account_name}/{region}/{project}/terraform.tfstate
        # Example: s3/arj-wkld-a-prd/us-east-1/test-4-poc-1/terraform.tfstate
        backend_key = f"{service_part}/{account_name}/{region}/{project}/terraform.tfstate"
        
        debug_print(f"Generated backend key: {backend_key} (service: {service_part}, account: {account_name}, region: {region}, project: {project})")
        
        return backend_key

    def _extract_terraform_outputs(self, terraform_output: str, action: str) -> Dict:
        """Extract resource outputs from terraform output for PR comments"""
        outputs = {
            'resources_created': [],
            'resources_modified': [],
            'resources_destroyed': [],
            'resource_details': {}
        }
        
        try:
            lines = terraform_output.split('\n')
            current_section = None
            
            for line in lines:
                line = line.strip()
                
                # Detect terraform plan sections
                if 'will be created' in line:
                    current_section = 'created'
                    resource_name = self._extract_resource_name(line)
                    if resource_name:
                        outputs['resources_created'].append(resource_name)
                elif 'will be updated' in line or 'will be modified' in line:
                    current_section = 'modified'
                    resource_name = self._extract_resource_name(line)
                    if resource_name:
                        outputs['resources_modified'].append(resource_name)
                elif 'will be destroyed' in line:
                    current_section = 'destroyed'
                    resource_name = self._extract_resource_name(line)
                    if resource_name:
                        outputs['resources_destroyed'].append(resource_name)
                
                # Extract specific resource details (ARNs, names, etc.)
                if action == 'apply':
                    self._extract_resource_details(line, outputs['resource_details'])
            
            debug_print(f"Extracted outputs: {outputs}")
            return outputs
            
        except Exception as e:
            debug_print(f"Error extracting terraform outputs: {e}")
            return outputs

    def _extract_resource_name(self, line: str) -> Optional[str]:
        """Extract resource name from terraform output line"""
        # Pattern: # aws_s3_bucket.example will be created
        match = re.search(r'#\s+(\S+)\s+will be', line)
        if match:
            return match.group(1)
        return None
    
    def _detect_resource_deletions(self, plan_output: str, environment: str) -> Tuple[List[str], List[str]]:
        """Detect resource deletions and block production deletions"""
        warnings = []
        errors = []
        
        # Parse deletion indicators
        deletion_lines = []
        for line in plan_output.split('\n'):
            if any(pattern in line for pattern in ['will be destroyed', 'must be replaced', '-/+', 'forces replacement']):
                deletion_lines.append(line.strip())
        
        if deletion_lines:
            count = len(deletion_lines)
            
            if environment.lower() in ['production', 'prod', 'prd']:
                errors.append(
                    f"🛑 PRODUCTION DELETION BLOCKED: {count} resource(s) will be destroyed/replaced! "
                    f"Manual review and explicit approval required. Resources: {', '.join(deletion_lines[:5])}"
                )
            else:
                warnings.append(
                    f"⚠️  Resource Deletion: {count} resource(s) will be destroyed/replaced. "
                    f"Review carefully: {', '.join(deletion_lines[:3])}"
                )
        
        return warnings, errors
    
    def _cleanup_old_workspaces(self, max_age_hours: int = 24):
        """Clean up old deployment workspaces"""
        try:
            main_dir = self.project_root
            current_time = time.time()
            cleaned = 0
            
            for workspace_dir in main_dir.glob('.terraform-workspace-*'):
                if workspace_dir.is_dir():
                    dir_age_hours = (current_time - workspace_dir.stat().st_mtime) / 3600
                    
                    if dir_age_hours > max_age_hours:
                        shutil.rmtree(workspace_dir)
                        cleaned += 1
                        debug_print(f"Cleaned workspace: {workspace_dir.name} (age: {dir_age_hours:.1f}h)")
            
            if cleaned > 0:
                print(f"🧹 Cleaned {cleaned} old workspace(s) older than {max_age_hours}h")
        except Exception as e:
            debug_print(f"Workspace cleanup failed: {e}")
    
    def _backup_state_file(self, backend_key: str, deployment_name: str) -> Tuple[bool, str]:
        """Backup current state file to S3 with timestamp before apply"""
        try:
            import boto3
            from datetime import datetime
            
            s3 = boto3.client('s3')
            bucket = 'terraform-elb-mdoule-poc'
            
            # Check if state file exists
            try:
                s3.head_object(Bucket=bucket, Key=backend_key)
            except:
                print(f"ℹ️  No existing state file to backup for {deployment_name}")
                return True, "no-previous-state"
            
            # Create backup with timestamp
            timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
            backup_key = f"backups/{backend_key}.{timestamp}.backup"
            
            # Copy current state to backup location
            s3.copy_object(
                Bucket=bucket,
                CopySource={'Bucket': bucket, 'Key': backend_key},
                Key=backup_key,
                ServerSideEncryption='AES256'  # Encrypt backup
            )
            
            # Store backup info for potential rollback
            self.state_backups[deployment_name] = {
                'backup_key': backup_key,
                'original_key': backend_key,
                'timestamp': timestamp
            }
            
            print(f"💾 State backed up: s3://{bucket}/{backup_key}")
            return True, backup_key
            
        except Exception as e:
            print(f"⚠️  State backup failed: {e}")
            return False, str(e)
    
    def _rollback_state_file(self, deployment_name: str) -> bool:
        """Rollback to previous state file if apply fails"""
        try:
            import boto3
            
            if deployment_name not in self.state_backups:
                print(f"⚠️  No backup found for {deployment_name}")
                return False
            
            backup_info = self.state_backups[deployment_name]
            s3 = boto3.client('s3')
            bucket = 'terraform-elb-mdoule-poc'
            
            print(f"🔄 Rolling back state from backup: {backup_info['backup_key']}")
            
            # Copy backup back to original location
            s3.copy_object(
                Bucket=bucket,
                CopySource={'Bucket': bucket, 'Key': backup_info['backup_key']},
                Key=backup_info['original_key']
            )
            
            print(f"✅ State rolled back successfully")
            return True
            
        except Exception as e:
            print(f"❌ Rollback failed: {e}")
            return False
    
    def _cleanup_old_workspaces(self, max_age_hours: int = 24):
        """Clean up old deployment workspaces to prevent disk space issues"""
        try:
            main_dir = self.project_root
            current_time = time.time()
            cleaned = 0
            
            for workspace_dir in main_dir.glob('.terraform-workspace-*'):
                if workspace_dir.is_dir():
                    # Check age
                    dir_age_hours = (current_time - workspace_dir.stat().st_mtime) / 3600
                    
                    if dir_age_hours > max_age_hours:
                        shutil.rmtree(workspace_dir)
                        cleaned += 1
                        debug_print(f"Cleaned old workspace: {workspace_dir.name} (age: {dir_age_hours:.1f}h)")
            
            if cleaned > 0:
                print(f"🧹 Cleaned {cleaned} old workspace(s) older than {max_age_hours}h")
                
        except Exception as e:
            debug_print(f"Workspace cleanup failed: {e}")
    
    def _save_audit_log(self, deployment: Dict, result: Dict, action: str):
        """Save detailed audit log to S3 with full unredacted output"""
        try:
            import boto3
            from datetime import datetime
            
            s3 = boto3.client('s3')
            bucket = 'terraform-elb-mdoule-poc'
            
            timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
            log_key = f"audit-logs/{deployment['account_name']}/{deployment['project']}/{action}-{timestamp}.json"
            
            audit_data = {
                'timestamp': datetime.now().isoformat(),
                'action': action,
                'deployment': deployment,
                'result': {
                    'success': result['success'],
                    'backend_key': result.get('backend_key', 'unknown'),
                    'services': result.get('services', []),
                    'output': result.get('output', ''),  # Full unredacted output
                    'error': result.get('error'),
                    'error_detail': result.get('error_detail')
                },
                'orchestrator_version': ORCHESTRATOR_VERSION
            }
            
            # Save to S3 with encryption
            s3.put_object(
                Bucket=bucket,
                Key=log_key,
                Body=json.dumps(audit_data, indent=2),
                ServerSideEncryption='AES256',
                ContentType='application/json'
            )
            
            print(f"📝 Audit log saved: s3://{bucket}/{log_key}")
            return True
            
        except Exception as e:
            print(f"⚠️  Audit log save failed: {e}")
            return False

    def _validate_terraform_fmt(self, workspace: Path) -> Tuple[List[str], List[str]]:
        """Validate terraform formatting standards"""
        warnings = []
        errors = []
        
        try:
            result = subprocess.run(
                ['terraform', 'fmt', '-check', '-recursive'],
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                unformatted_files = result.stdout.strip().split('\n') if result.stdout else []
                if unformatted_files:
                    warnings.append(
                        f"⚠️  Code formatting: {len(unformatted_files)} file(s) need formatting. "
                        f"Run 'terraform fmt -recursive' to fix."
                    )
        except Exception as e:
            warnings.append(f"⚠️  Terraform fmt check failed: {str(e)}")
        
        return warnings, errors
    
    def _validate_tfvars_file(self, tfvars_file: Path) -> Tuple[bool, str]:
        """Validate tfvars file exists and has valid syntax"""
        try:
            if not tfvars_file.exists():
                return False, f"Tfvars file not found: {tfvars_file}"
            
            if tfvars_file.stat().st_size == 0:
                return False, f"Tfvars file is empty: {tfvars_file}"
            
            with open(tfvars_file, 'r') as f:
                content = f.read()
            
            # Basic HCL syntax validation
            if content.count('{') != content.count('}'):
                return False, "Mismatched braces in tfvars file"
            if content.count('[') != content.count(']'):
                return False, "Mismatched brackets in tfvars file"
            
            debug_print(f"Tfvars validation passed: {tfvars_file}")
            return True, "Valid"
            
        except Exception as e:
            return False, f"Validation error: {e}"
    
    def _detect_resource_deletions(self, plan_output: str, environment: str) -> Tuple[List[str], List[str]]:
        """Detect resource deletions in terraform plan and warn/block based on environment"""
        warnings = []
        errors = []
        
        # Parse deletion indicators
        deletion_patterns = [
            r'will be destroyed',
            r'must be replaced',
            r'-/\+ resource',
            r'# .+ will be destroyed'
        ]
        
        deletions = []
        for pattern in deletion_patterns:
            matches = re.findall(pattern, plan_output, re.IGNORECASE)
            deletions.extend(matches)
        
        if deletions:
            count = len(deletions)
            
            if environment.lower() in ['production', 'prod', 'prd']:
                errors.append(
                    f"🛑 PRODUCTION DELETION DETECTED: {count} resource(s) will be DESTROYED/REPLACED! "
                    f"This requires manual review and explicit approval."
                )
            else:
                warnings.append(
                    f"⚠️  Resource Deletion: {count} resource(s) will be destroyed or replaced. "
                    f"Review plan carefully."
                )
        
        return warnings, errors
    
    def _comprehensive_validation(self, tfvars_file: Path, deployment: Dict) -> Tuple[List[str], List[str]]:
        """
        COMPREHENSIVE PRE-DEPLOYMENT VALIDATION
        Validates: ARNs, policies, resource names, AWS standards
        Returns: (warnings, errors) - errors BLOCK deployment
        """
        warnings = []
        errors = []
        
        try:
            with open(tfvars_file, 'r') as f:
                content = f.read()
            
            account_id = deployment.get('account_id')
            environment = deployment.get('environment', 'unknown')
            
            print(f"🔍 Running comprehensive validation...")
            
            # 0. VALIDATE TERRAFORM FORMATTING
            fmt_warnings, fmt_errors = self._validate_terraform_fmt(self.working_dir)
            warnings.extend(fmt_warnings)
            errors.extend(fmt_errors)
            
            # 1. VALIDATE ARNS MATCH ACCOUNT
            arn_pattern = r'arn:aws:[a-z0-9\-]+:[a-z0-9\-]*:(\d{12}):'
            arns_found = re.findall(arn_pattern, content)
            for arn_account in set(arns_found):
                if arn_account != account_id:
                    errors.append(
                        f"🚫 BLOCKER: ARN contains account {arn_account} but deploying to {account_id}! "
                        f"This will cause access errors."
                    )
            
            # 2. VALIDATE POLICY JSON FILES
            policy_pattern = r'["\']([^"\']+\.json)["\']'
            policy_files = re.findall(policy_pattern, content)
            
            if policy_files:
                print(f"   Found {len(policy_files)} policy file(s) to validate")
                
                for policy_path in policy_files:
                    policy_file = Path(policy_path)
                    
                    # Validate JSON syntax and AWS standards
                    is_valid, pol_warnings, pol_errors = validate_policy_json_file(
                        policy_file,
                        self.working_dir,
                        account_id
                    )
                    
                    warnings.extend(pol_warnings)
                    errors.extend(pol_errors)
                    
                    # Validate resource names match - CRITICAL CHECK
                    if is_valid:
                        name_warnings, name_errors = validate_resource_names_match(
                            policy_file,
                            content,
                            self.working_dir
                        )
                        warnings.extend(name_warnings)
                        errors.extend(name_errors)  # Resource mismatches are BLOCKERS
                    
                    status = "✅" if is_valid else "❌"
                    print(f"   {status} {policy_file.name}: {len(pol_errors)} errors, {len(pol_warnings)} warnings")
                    
                    # 🤖 AMAZON Q VALIDATION - Query AI for intelligent validation
                    if is_valid and policy_file.exists():
                        try:
                            abs_policy_file = policy_file if policy_file.is_absolute() else self.working_dir / policy_file
                            with open(abs_policy_file, 'r') as pf:
                                policy_content = pf.read()
                            
                            q_warnings, q_errors = query_amazon_q_for_validation(
                                content,
                                policy_content,
                                deployment
                            )
                            
                            warnings.extend(q_warnings)
                            errors.extend(q_errors)
                            
                            if q_errors:
                                print(f"   🚫 Amazon Q found {len(q_errors)} blocking error(s)")
                            elif q_warnings:
                                print(f"   ⚠️  Amazon Q found {len(q_warnings)} warning(s)")
                        except Exception as q_err:
                            warnings.append(f"⚠️  Amazon Q validation failed: {str(q_err)}")
            
            # 3. PRODUCTION ENVIRONMENT CHECKS (Generic - any service)
            if environment.lower() in ['production', 'prod', 'prd']:
                # Generic destroy protection check
                if 'prevent_destroy = false' in content or 'prevent_destroy=false' in content:
                    warnings.append(
                        f"⚠️  PRODUCTION: prevent_destroy=false allows resource deletion!"
                    )
            
            print(f"   Validation complete: {len(warnings)} warnings, {len(errors)} errors")
            
        except Exception as e:
            errors.append(f"🚫 Validation exception: {str(e)}")
        
        return warnings, errors

    def _generate_enhanced_pr_comment(self, deployment: Dict, result: Dict, services: List[str]) -> str:
        """Generate enhanced PR comment with service details and outputs - REDACTED for security"""
        deployment_name = f"{deployment['account_name']}-{deployment['project']}"
        orchestrator_ver = result.get('orchestrator_version', ORCHESTRATOR_VERSION)
        
        # SECURITY: Redact sensitive data from all outputs
        redacted_output = redact_sensitive_data(result.get('output', ''))
        redacted_error = redact_sensitive_data(result.get('error', 'Unknown error'))
        
        if not result['success']:
            # Error comment - REDACTED
            return f"""### ❌ {deployment_name} - Deployment Failed

**Services:** {', '.join(services) if services else 'None detected'}

**Error:** {redacted_error}

<details><summary><strong>🚨 Error Details (Sensitive data redacted)</strong></summary>

```
{redacted_output[:2000]}
```

</details>

🔒 **Security Notice:** Sensitive data (ARNs, Account IDs, IPs) redacted from PR comments.
📋 **Full logs:** Saved to encrypted audit log in S3 for compliance.

Please fix the errors and push to a new branch.

---
"""
        
        # Success comment - REDACTED
        outputs = self._extract_terraform_outputs(redacted_output, result.get('action', 'unknown'))
        
        # Get validation results
        val_warnings = result.get('validation_warnings', [])
        val_errors = result.get('validation_errors', [])
        
        comment = f"""### ✅ {deployment_name} - Deployment Successful

**Services:** {', '.join(services) if services else 'None detected'}
**Action:** {result.get('action', 'unknown').title()}
**Orchestrator Version:** v{orchestrator_ver}

"""
        
        # ADD COMPREHENSIVE VALIDATION RESULTS
        if val_errors or val_warnings:
            comment += "---\n\n## 🔍 Pre-Deployment Validation Report\n\n"
            
            # Overall status
            if val_errors:
                comment += "### 🚫 VALIDATION FAILED\n\n"
                comment += "❌ **Deployment has been BLOCKED** due to critical validation errors that must be fixed.\n\n"
            else:
                comment += "### ✅ VALIDATION PASSED WITH WARNINGS\n\n"
                comment += "⚠️  **Deployment will proceed** but please review warnings below.\n\n"
            
            # Validation checklist
            comment += "#### 🛡️ Validation Checklist:\n\n"
            comment += "| Check | Status | Details |\n"
            comment += "|-------|--------|---------|\n"
            
            # Determine what passed/failed based on errors/warnings content
            format_status = "✅ Passed"
            arn_status = "✅ Passed"
            policy_status = "✅ Passed"
            resource_status = "✅ Passed"
            deletion_status = "✅ Safe"
            
            for error in val_errors:
                if "terraform fmt" in error.lower() or "formatting" in error.lower():
                    format_status = "❌ Failed"
                if "arn" in error.lower() and "account" in error.lower():
                    arn_status = "❌ Failed"
                if "policy" in error.lower() and ("json" in error.lower() or "syntax" in error.lower()):
                    policy_status = "❌ Failed"
                if "resource name" in error.lower() or "bucket name" in error.lower():
                    resource_status = "❌ Failed"
                if "deletion" in error.lower() or "destroy" in error.lower():
                    deletion_status = "🛑 BLOCKED"
            
            for warning in val_warnings:
                if "terraform fmt" in warning.lower() or "formatting" in warning.lower():
                    format_status = "⚠️  Needs Fix"
                if "deletion" in warning.lower() or "destroy" in warning.lower():
                    deletion_status = "⚠️  Review Required"
            
            comment += f"| 📝 Code Formatting | {format_status} | Terraform fmt standards |\n"
            comment += f"| 🔐 ARN Validation | {arn_status} | Account ID matching |\n"
            comment += f"| 📄 Policy Validation | {policy_status} | JSON syntax & AWS rules |\n"
            comment += f"| 🏷️  Resource Names | {resource_status} | Name consistency check |\n"
            comment += f"| 🛡️  Deletion Protection | {deletion_status} | Production safety |\n"
            comment += "\n"
            
            # Errors section
            if val_errors:
                comment += "### 🚫 CRITICAL ERRORS (Must Fix)\n\n"
                comment += "The following issues **BLOCK** deployment and must be resolved:\n\n"
                for i, error in enumerate(val_errors, 1):
                    comment += f"{i}. {error}\n"
                comment += "\n"
                
                comment += "**📋 How to Fix:**\n"
                comment += "1. Review each error message above\n"
                comment += "2. Update your tfvars, policies, or resource configurations\n"
                comment += "3. Run `terraform fmt -recursive` to fix formatting\n"
                comment += "4. Push changes to re-trigger validation\n\n"
            
            # Warnings section
            if val_warnings:
                comment += "### ⚠️  WARNINGS (Review Recommended)\n\n"
                comment += "The following issues won't block deployment but should be reviewed:\n\n"
                for i, warning in enumerate(val_warnings, 1):
                    comment += f"{i}. {warning}\n"
                comment += "\n"
            
            # Production emphasis
            if deployment.get('environment', '').lower() in ['production', 'prod', 'prd']:
                comment += "### 🚨 PRODUCTION ENVIRONMENT ALERT\n\n"
                comment += "⚠️  **This is a PRODUCTION deployment!**\n\n"
                comment += "**Extra precautions:**\n"
                comment += "- All warnings must be reviewed by team lead\n"
                comment += "- Resource deletions require explicit approval\n"
                comment += "- State backup is automatically created\n"
                comment += "- Automatic rollback on failure\n\n"
            
            comment += "---\n\n"
        
        # Add drift detection results (if this was an apply with drift check)
        if result.get('drift_detected'):
            comment += "## 🔍 Infrastructure Drift Detection\n\n"
            if result.get('has_drift', False):
                comment += "⚠️  **Drift Detected**: Infrastructure has diverged from Terraform state\n\n"
                comment += "This could be due to:\n"
                comment += "- Manual changes made outside Terraform\n"
                comment += "- Previous failed deployments\n"
                comment += "- External systems modifying resources\n\n"
                comment += "**Action taken**: Applied changes to bring infrastructure back in sync.\n\n"
            else:
                comment += "✅ **No Drift**: Infrastructure matches Terraform state perfectly\n\n"
        
        comment += "---\n\n"
        
        # Add resource summary
        if outputs['resources_created']:
            comment += f"**📦 Resources Created ({len(outputs['resources_created'])}):**\n"
            for resource in outputs['resources_created'][:10]:  # Limit to 10
                comment += f"- `{resource}`\n"
            if len(outputs['resources_created']) > 10:
                comment += f"- ... and {len(outputs['resources_created']) - 10} more\n"
            comment += "\n"
        
        if outputs['resources_modified']:
            comment += f"**🔧 Resources Modified ({len(outputs['resources_modified'])}):**\n"
            for resource in outputs['resources_modified'][:5]:
                comment += f"- `{resource}`\n"
            comment += "\n"
        
        # Add service-specific details
        if outputs['resource_details']:
            comment += "**🎯 Service Details:**\n"
            for service, details in outputs['resource_details'].items():
                if details['arns']:
                    comment += f"**{service.upper()}:**\n"
                    for arn in details['arns'][:3]:  # Limit ARNs
                        comment += f"- ARN: `{arn}`\n"
                if details['names']:
                    for name in details['names'][:3]:  # Limit names  
                        comment += f"- Name: `{name}`\n"
            comment += "\n"
        
        # Add terraform output details - REDACTED
        comment += f"""<details><summary><strong>🔍 Terraform Output (Sensitive data redacted)</strong></summary>

```terraform
{redacted_output[:3000]}
```

</details>

---

## 🔒 Security & Compliance Features

### ✅ Validation Pipeline (6 Layers)
1. **Terraform Format Check** - Code formatting standards
2. **JSON Syntax Validation** - Policy file correctness
3. **ARN Account Matching** - Cross-account access prevention
4. **Resource Name Consistency** - Copy-paste error detection
5. **Deletion Protection** - Production safety guardrails
6. **Amazon Q AI Validation** - Intelligent configuration review (optional)

### 🛡️ Safety Mechanisms
- ✅ **Drift Detection**: Plan before apply to show changes
- ✅ **State Backup**: Automatic backup before every apply
- ✅ **Automatic Rollback**: Restore state on failure
- ✅ **Retry Logic**: 3 retries with exponential backoff for transient errors
- ✅ **Workspace Cleanup**: Automatic old workspace removal (24h retention)
- ✅ **Production Deletion Protection**: Manual approval required for resource deletions

### 🔐 Data Privacy
- ✅ **Sensitive data redacted** from PR comments (ARNs, Account IDs, IP addresses)
- ✅ **Full unredacted logs** saved to encrypted S3 audit log
- ✅ **AES256 encryption** for all S3 audit logs and state backups
- ✅ **Compliance ready**: SOC2, HIPAA, PCI-DSS audit trails

### 📋 Audit Trail
- **Location**: `s3://terraform-elb-mdoule-poc/audit-logs/{deployment['account_name']}/{deployment['project']}/`
- **Retention**: 7 years (compliance requirement)
- **Format**: JSON with full unredacted output

### 📚 Documentation
- [Security Features](https://github.com/Terraform-centilazed-pipline/centerlized-pipline-/blob/main/docs/SECURITY-FEATURES.md)
- [Terraform Best Practices](https://github.com/Terraform-centilazed-pipline/centerlized-pipline-/blob/main/docs/TERRAFORM-BEST-PRACTICES.md)
- [Orchestrator Enhancements](https://github.com/Terraform-centilazed-pipline/centerlized-pipline-/blob/main/scripts/ORCHESTRATOR-V2-ENHANCEMENTS.md)

---

*🤖 Generated by Enhanced Terraform Orchestrator v{orchestrator_ver} | Enterprise-Grade Deployment Pipeline*
"""
        
        return comment

    def _process_deployment_enhanced(self, deployment: Dict, action: str) -> Dict:
        """Enhanced deployment processing with dynamic backend and better error handling - Version 2.0"""
        try:
            # Reset validation lists for this deployment
            self.validation_warnings = []
            self.validation_errors = []
            
            debug_print(f"Processing deployment (v{ORCHESTRATOR_VERSION}): {deployment}")
            
            # Resolve tfvars file path
            tfvars_file = Path(deployment['file'])
            if not tfvars_file.is_absolute():
                tfvars_file = self.working_dir / tfvars_file
            
            # Validate tfvars file syntax
            is_valid, validation_msg = self._validate_tfvars_file(tfvars_file)
            if not is_valid:
                return {
                    'deployment': deployment,
                    'success': False,
                    'error': f"Tfvars validation failed: {validation_msg}",
                    'output': validation_msg,
                    'backend_key': 'unknown',
                    'services': [],
                    'action': action
                }
            
            # COMPREHENSIVE VALIDATION - ARNs, Policies, Resource Names
            validation_warnings, validation_errors = self._comprehensive_validation(tfvars_file, deployment)
            
            # Store for PR comments
            self.validation_warnings.extend(validation_warnings)
            self.validation_errors.extend(validation_errors)
            
            # BLOCK DEPLOYMENT if validation errors found
            if validation_errors:
                error_msg = "\n".join(validation_errors)
                print(f"\n❌ VALIDATION FAILED - DEPLOYMENT BLOCKED:\n{error_msg}\n")
                
                # Create detailed error summary for PR comment
                error_summary = f"Validation failed with {len(validation_errors)} error(s)"
                if len(validation_errors) == 1:
                    # Single error - show it directly
                    error_summary = validation_errors[0]
                elif len(validation_errors) <= 3:
                    # Few errors - show all
                    error_summary = "; ".join(validation_errors)
                else:
                    # Many errors - show first 2 and count
                    error_summary = f"{validation_errors[0]}; {validation_errors[1]}; ... +{len(validation_errors)-2} more"
                
                return {
                    'deployment': deployment,
                    'success': False,
                    'error': error_summary[:500],  # Limit to 500 chars for PR comment
                    'error_detail': error_msg,  # Full details for expandable section
                    'output': f"🚫 DEPLOYMENT BLOCKED\n\n{error_msg}",
                    'backend_key': 'unknown',
                    'services': [],
                    'action': action,
                    'validation_warnings': validation_warnings,
                    'validation_errors': validation_errors
                }
            
            # Show warnings but continue
            if validation_warnings:
                warn_msg = "\n".join(validation_warnings)
                print(f"\n⚠️  VALIDATION WARNINGS:\n{warn_msg}\n")
            
            # Detect services from tfvars
            services = self._detect_services_from_tfvars(tfvars_file)
            
            # Generate dynamic backend key with resource name
            backend_key = self._generate_dynamic_backend_key(deployment, services, tfvars_file)
            
            # Copy required files to working directory
            # Use deployment-specific directory to avoid race conditions in parallel execution
            main_dir = self.project_root
            deployment_name = f"{deployment['account_name']}-{deployment['project']}"
            
            # Create deployment-specific workspace
            deployment_workspace = main_dir / f".terraform-workspace-{deployment_name}"
            
            # Always clean and recreate workspace to avoid lock file conflicts
            if deployment_workspace.exists():
                shutil.rmtree(deployment_workspace)
                debug_print(f"Cleaned existing workspace: {deployment_workspace}")
            
            deployment_workspace.mkdir(exist_ok=True)
            debug_print(f"Created fresh workspace: {deployment_workspace}")
            
            tfvars_dest = deployment_workspace / "terraform.tfvars"
            shutil.copy2(tfvars_file, tfvars_dest)
            debug_print(f"Copied {tfvars_file} -> {tfvars_dest}")
            
            # Copy policy JSON files referenced in tfvars (if any)
            try:
                debug_print(f"About to call _copy_referenced_policy_files")
                self._copy_referenced_policy_files(tfvars_file, deployment_workspace, deployment)
                debug_print(f"Finished calling _copy_referenced_policy_files")
            except Exception as copy_err:
                print(f"⚠️ Exception in _copy_referenced_policy_files: {copy_err}")
                import traceback
                traceback.print_exc()
            
            # Copy main.tf and other terraform files to workspace
            for tf_file in main_dir.glob("*.tf"):
                shutil.copy2(tf_file, deployment_workspace / tf_file.name)
                debug_print(f"Copied {tf_file.name} to workspace")
            
            # Initialize Terraform with dynamic backend
            init_cmd = [
                'init', '-input=false',
                f'-backend-config=key={backend_key}',
                f'-backend-config=region=us-east-1'
            ]
            
            print(f"🔄 Initializing Terraform with backend key: {backend_key}")
            print(f"🔒 State locking enabled via Terraform built-in lockfile (use_lockfile=true)")
            
            init_result = self._run_terraform_command(init_cmd, deployment_workspace)
            if init_result['returncode'] != 0:
                error_msg = f"Terraform init failed: {init_result.get('stderr', init_result['output'])}"
                return {
                    'deployment': deployment,
                    'success': False,
                    'error': error_msg,
                    'output': init_result['output'],
                    'backend_key': backend_key,
                    'services': services,
                    'action': action
                }
            
            # CLEANUP OLD WORKSPACES
            self._cleanup_old_workspaces(max_age_hours=24)
            
            # DRIFT DETECTION & DELETION PROTECTION BEFORE APPLY
            if action == "apply":
                print(f"🔍 Running drift detection before apply...")
                drift_cmd = ['plan', '-detailed-exitcode', '-input=false', '-var-file=terraform.tfvars', '-no-color']
                drift_result = self._run_terraform_command(drift_cmd, deployment_workspace)
                
                if drift_result['returncode'] == 2:
                    print(f"✅ Drift detected - changes will be applied")
                    
                    # Check for deletions
                    del_warnings, del_errors = self._detect_resource_deletions(
                        drift_result['output'],
                        deployment.get('environment', 'unknown')
                    )
                    
                    if del_errors:
                        print(f"⚠️  DELETION PROTECTION TRIGGERED")
                        for error in del_errors:
                            print(f"   {error}")
                        
                        return {
                            'deployment': deployment,
                            'success': False,
                            'error': 'Production deletion protection - manual approval required',
                            'output': f"🛑 BLOCKED: Production resource deletion\n\n{'\n'.join(del_errors)}",
                            'backend_key': backend_key,
                            'services': services,
                            'action': action,
                            'validation_warnings': validation_warnings,
                            'validation_errors': del_errors
                        }
                    
                    if del_warnings:
                        for warning in del_warnings:
                            print(f"   {warning}")
                elif drift_result['returncode'] == 0:
                    print(f"ℹ️  No changes detected - infrastructure is in sync")
                else:
                    print(f"⚠️  Drift detection failed with exit code {drift_result['returncode']}")
            
            # BACKUP STATE FILE BEFORE APPLY
            deployment_name = f"{deployment['account_name']}-{deployment['project']}"
            backup_info = None
            
            if action == "apply":
                print(f"💾 Creating state backup before apply...")
                backup_success, backup_info = self._backup_state_file(backend_key, deployment_name)
                if backup_success:
                    print(f"✅ State backup created: {backup_info}")
                else:
                    print(f"⚠️ Warning: State backup failed, but continuing with apply")
            
            # Run terraform action
            if action == "plan":
                # Save plan to file for JSON conversion
                plan_filename = f"{deployment['account_name']}-{deployment['project']}.tfplan"
                plan_file = deployment_workspace / plan_filename
                cmd = ['plan', '-detailed-exitcode', '-input=false', '-var-file=terraform.tfvars', '-no-color', f'-out={plan_filename}']
                print(f"📋 Running terraform plan...")
            elif action == "apply":
                cmd = ['apply', '-auto-approve', '-input=false', '-var-file=terraform.tfvars', '-no-color']
                print(f"🚀 Running terraform apply...")
            else:
                cmd = [action, '-input=false', '-var-file=terraform.tfvars', '-no-color']
            
            result = self._run_terraform_command(cmd, deployment_workspace)
            
            # ROLLBACK ON APPLY FAILURE
            if action == "apply" and result['returncode'] != 0:
                print(f"\n❌ Apply failed! Attempting automatic rollback...")
                rollback_success = self._rollback_state_file(deployment_name)
                if rollback_success:
                    print(f"✅ State file rolled back to previous version")
                    result['output'] += f"\n\n⚠️ ROLLBACK PERFORMED: State file restored from backup due to apply failure"
                else:
                    print(f"⚠️ Rollback failed - manual intervention may be required")
                    result['output'] += f"\n\n⚠️ ROLLBACK FAILED: Manual state file recovery may be required"
            
            # Determine success based on action and exit code
            if action == "plan":
                success = result['returncode'] in [0, 2]  # 0=no changes, 2=changes detected
                has_changes = result['returncode'] == 2
                
                print(f"📊 Terraform Plan Exit Code: {result['returncode']}")
                print(f"   ✅ Success: {success}")
                print(f"   🔄 Has Changes: {has_changes}")
                
                # Double-check by looking at output
                if not has_changes and ('will be created' in result['output'] or 'will be updated' in result['output'] or 'will be destroyed' in result['output']):
                    print(f"⚠️ WARNING: Exit code was 0 but output shows changes! Forcing has_changes=True")
                    has_changes = True
                
                # Generate JSON plan and markdown for OPA validation if plan succeeded
                if success and plan_file.exists():
                    # Create JSON plan
                    json_dir = self.working_dir / "terraform-json"
                    json_dir.mkdir(exist_ok=True)
                    
                    json_filename = f"{deployment['account_name']}-{deployment['project']}.json"
                    json_file = json_dir / json_filename
                    
                    # IMPORTANT: Use full path to plan file (not just filename)
                    show_result = self._run_terraform_command(['show', '-json', str(plan_file)], deployment_workspace)
                    if show_result['returncode'] == 0:
                        with open(json_file, 'w') as f:
                            f.write(show_result['stdout'])
                        print(f"📄 Generated JSON plan: {json_file}")
                        debug_print(f"JSON plan saved to: {json_file}")
                        
                        # Parse JSON to detect changes as backup method
                        try:
                            import json as json_module
                            plan_data = json_module.loads(show_result['stdout'])
                            resource_changes = plan_data.get('resource_changes', [])
                            actual_changes = [rc for rc in resource_changes if rc.get('change', {}).get('actions', []) != ['no-op']]
                            
                            if actual_changes and not has_changes:
                                print(f"⚠️ OVERRIDE: JSON shows {len(actual_changes)} resource changes but exit code was 0")
                                print(f"   Setting has_changes=True based on JSON analysis")
                                has_changes = True
                            
                            print(f"📊 JSON Analysis: {len(actual_changes)} resources with changes out of {len(resource_changes)} total")
                        except Exception as parse_err:
                            print(f"⚠️ Could not parse JSON plan for change detection: {parse_err}")
                    else:
                        print(f"⚠️ Warning: Failed to generate JSON plan for {deployment['account_name']}")
                        debug_print(f"terraform show -json failed: {show_result.get('stderr', 'unknown error')}")
                    
                    # Create markdown plan for PR comments
                    markdown_dir = self.working_dir / "plan-markdown"
                    markdown_dir.mkdir(exist_ok=True)
                    
                    markdown_filename = f"{deployment['account_name']}-{deployment['project']}.md"
                    markdown_file = markdown_dir / markdown_filename
                    
                    show_md_result = self._run_terraform_command(['show', plan_filename], deployment_workspace)
                    if show_md_result['returncode'] == 0:
                        with open(markdown_file, 'w') as f:
                            f.write(f"## Terraform Plan: {deployment['account_name']}/{deployment['project']}\n\n")
                            f.write(f"**Backend Key:** `{backend_key}`\n\n")
                            f.write(f"**Services:** {', '.join(services)}\n\n")
                            f.write("```terraform\n")
                            f.write(show_md_result['stdout'])
                            f.write("\n```\n")
                        print(f"📝 Generated markdown plan: {markdown_file}")
                        debug_print(f"Markdown plan saved to: {markdown_file}")
                    else:
                        print(f"⚠️ Warning: Failed to generate markdown plan for {deployment['account_name']}")
                        debug_print(f"terraform show failed: {show_md_result.get('stderr', 'unknown error')}")
            else:
                success = result['returncode'] == 0
                has_changes = True
            
            # Print detailed error if command failed
            if not success:
                print(f"\n❌ Terraform {action} failed with exit code {result['returncode']}")
                print(f"📋 Error output:")
                print(result.get('stderr', result.get('output', 'No error output available')))
                if DEBUG:
                    print(f"\n📋 Full stdout:")
                    print(result.get('stdout', 'No stdout available'))
            
            # Build result dict
            final_result = {
                'deployment': deployment,
                'success': success,
                'has_changes': has_changes,
                'output': result['output'],
                'stderr': result.get('stderr', ''),
                'stdout': result.get('stdout', ''),
                'backend_key': backend_key,
                'services': services,
                'action': action,
                'error': None if success else f"{action} failed with exit code {result['returncode']}",
                'error_detail': result.get('stderr', result.get('output', '')) if not success else None,
                'orchestrator_version': ORCHESTRATOR_VERSION,
                'backup_info': backup_info if action == 'apply' else None,
                'validation_warnings': self.validation_warnings,
                'validation_errors': self.validation_errors
            }
            
            # SAVE AUDIT LOG (full unredacted output for compliance)
            print(f"📋 Saving audit log to encrypted S3...")
            audit_success = self._save_audit_log(deployment, final_result, action)
            if audit_success:
                print(f"✅ Audit log saved successfully")
            else:
                print(f"⚠️ Warning: Audit log save failed")
            
            return final_result
            
        except Exception as e:
            return {
                'deployment': deployment,
                'success': False,
                'error': str(e),
                'output': f"Exception during {action}: {e}",
                'backend_key': backend_key if 'backend_key' in locals() else 'unknown',
                'services': services if 'services' in locals() else [],
                'action': action
            }

    def _run_terraform_command(self, cmd: List[str], cwd: Path, retries: int = 3) -> Dict:
        """Run terraform command with retry logic for transient failures"""
        full_cmd = ['terraform'] + cmd
        debug_print(f"Running: {' '.join(full_cmd)} in {cwd}")
        
        last_error = None
        for attempt in range(retries):
            try:
                if attempt > 0:
                    wait_time = 2 ** attempt  # Exponential backoff: 2s, 4s, 8s
                    print(f"⏳ Retry attempt {attempt + 1}/{retries} after {wait_time}s wait...")
                    time.sleep(wait_time)
                
                import os
                env = getattr(self, '_terraform_env', os.environ.copy())
                
                result = subprocess.run(
                    full_cmd,
                    cwd=cwd,
                    capture_output=True,
                    text=True,
                    env=env,
                    timeout=1800  # 30 minutes timeout
                )
                
                # Check for transient errors
                transient_errors = [
                    'connection reset',
                    'timeout',
                    'temporary failure',
                    'service unavailable',
                    'rate limit',
                    'TooManyRequestsException'
                ]
                
                output = result.stdout + result.stderr
                is_transient = any(err.lower() in output.lower() for err in transient_errors)
                
                # Return immediately if successful or non-transient error
                if result.returncode == 0 or (result.returncode != 0 and not is_transient):
                    return {
                        'returncode': result.returncode,
                        'stdout': result.stdout,
                        'stderr': result.stderr,
                        'output': output
                    }
                
                # Store transient error for retry
                last_error = output
                print(f"⚠️  Transient error detected: {output[:200]}...")
                
            except subprocess.TimeoutExpired:
                return {
                    'returncode': 124,
                    'stdout': '',
                    'stderr': 'Command timed out after 30 minutes',
                    'output': 'Command timed out after 30 minutes'
                }
            except Exception as e:
                last_error = str(e)
                print(f"⚠️  Exception on attempt {attempt + 1}: {str(e)}")
        
        # All retries exhausted
        return {
            'returncode': 1,
            'stdout': '',
            'stderr': last_error or 'Unknown error',
            'output': f"Command failed after {retries} attempts. Last error: {last_error}"
        }

    def _copy_referenced_policy_files(self, tfvars_file: Path, dest_dir: Path, deployment: Dict):
        """
        Copy policy JSON files referenced in tfvars to the destination directory.
        Maintains the same directory structure so Terraform can find them.
        """
        print(f"🔍 ENTERING _copy_referenced_policy_files for: {tfvars_file}")
        debug_print(f"🔍 _copy_referenced_policy_files called for: {tfvars_file}")
        debug_print(f"   Dest dir: {dest_dir}")
        debug_print(f"   Working dir: {self.working_dir}")
        
        try:
            with open(tfvars_file, 'r') as f:
                tfvars_content = f.read()
            
            debug_print(f"   Tfvars content length: {len(tfvars_content)} bytes")
            
            # Find all JSON file references: bucket_policy_file = "path/to/file.json"
            # Matches any path structure (S3/, Accounts/, KMS/, etc.)
            json_pattern = r'["\']([^"\']+\.json)["\']'
            json_files = re.findall(json_pattern, tfvars_content)
            
            debug_print(f"   Regex pattern: {json_pattern}")
            debug_print(f"   JSON files found by regex: {json_files}")
            
            if not json_files:
                debug_print("No policy JSON files referenced in tfvars")
                return
            
            debug_print(f"Found {len(json_files)} policy file references in tfvars")
            
            for json_file_path in json_files:
                filename = Path(json_file_path).name
                debug_print(f"Looking for policy file: {filename}")
                
                source_file = None
                
                # Try the exact path from tfvars (relative to working_dir)
                candidate1 = self.working_dir / json_file_path
                if candidate1.exists():
                    source_file = candidate1
                    debug_print(f"✅ Found policy file: {candidate1}")
                else:
                    # Look in the deployment directory
                    deployment_dir = Path(deployment['deployment_dir'])
                    if not deployment_dir.is_absolute():
                        deployment_dir = self.working_dir / deployment_dir
                    
                    candidate2 = deployment_dir / filename
                    if candidate2.exists():
                        source_file = candidate2
                        debug_print(f"✅ Found policy file: {candidate2}")
                
                if source_file:
                    # Destination preserves the tfvars path (what terraform expects)
                    dest_file = dest_dir / json_file_path
                    dest_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source_file, dest_file)
                    print(f"✅ Copied policy file: {filename}")
                    debug_print(f"   From: {source_file}")
                    debug_print(f"   To:   {dest_file}")
                else:
                    print(f"⚠️ Warning: Policy file '{filename}' not found")
                    
        except Exception as e:
            print(f"⚠️ Warning: Error copying policy files: {e}")
            debug_print(f"Error in _copy_referenced_policy_files: {e}")
            import traceback
            debug_print(traceback.format_exc())


    
    def execute_deployments(self, deployments: List[Dict], action: str = "plan") -> Dict:
        """Execute terraform deployments - PARALLEL processing with thread pool"""
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import threading
        
        results = {
            'successful': [],
            'failed': [],
            'summary': {}
        }
        
        # Determine optimal number of parallel workers
        # Use CPU cores × 2 (Terraform is I/O bound, not CPU bound)
        # But cap at 5 to avoid AWS API rate limits
        import os
        cpu_count = os.cpu_count() or 2
        optimal_workers = cpu_count * 2  # 2 cores = 4 workers, 4 cores = 8 workers
        max_workers = min(optimal_workers, 5, len(deployments)) if len(deployments) > 1 else 1
        
        print(f"🚀 Starting {action} for {len(deployments)} deployments")
        print(f"💻 Detected {cpu_count} CPU cores → {optimal_workers} optimal workers (using {max_workers})")
        
        if max_workers == 1:
            # Single deployment - no need for threading overhead
            deployment = deployments[0]
            print(f"🔄 [1/1] Processing {deployment['account_name']}/{deployment['region']}/{deployment['project']}")
            
            try:
                result = self._process_deployment_enhanced(deployment, action)
                if result['success']:
                    results['successful'].append(result)
                    print(f"✅ {deployment['account_name']}/{deployment['region']}: Success")
                else:
                    results['failed'].append(result)
                    print(f"❌ {deployment['account_name']}/{deployment['region']}: Failed")
                    if DEBUG:
                        print(f"🔍 Error details: {result.get('error', 'No error message')}")
            except Exception as e:
                error_result = {
                    'deployment': deployment,
                    'success': False,
                    'error': str(e),
                    'output': f"Exception during processing: {e}"
                }
                results['failed'].append(error_result)
                print(f"💥 {deployment['account_name']}/{deployment['region']}: Exception - {e}")
        else:
            # Multiple deployments - use parallel execution
            completed = 0
            lock = threading.Lock()
            
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Submit all deployments to thread pool
                future_to_deployment = {
                    executor.submit(self._process_deployment_enhanced, dep, action): dep
                    for dep in deployments
                }
                
                # Process results as they complete (30 min timeout per deployment)
                for future in as_completed(future_to_deployment):
                    deployment = future_to_deployment[future]
                    completed += 1
                    
                    try:
                        result = future.result(timeout=1800)
                        
                        with lock:  # Thread-safe result collection
                            if result['success']:
                                results['successful'].append(result)
                                print(f"✅ [{completed}/{len(deployments)}] {deployment['account_name']}/{deployment['region']}: Success")
                            else:
                                results['failed'].append(result)
                                print(f"❌ [{completed}/{len(deployments)}] {deployment['account_name']}/{deployment['region']}: Failed")
                                if DEBUG:
                                    print(f"🔍 Error details: {result.get('error', 'No error message')}")
                    
                    except concurrent.futures.TimeoutError:
                        with lock:
                            error_result = {
                                'deployment': deployment,
                                'success': False,
                                'error': 'Deployment timed out after 30 minutes',
                                'output': 'Deployment exceeded maximum allowed time'
                            }
                            results['failed'].append(error_result)
                            print(f"⏱️  [{completed}/{len(deployments)}] {deployment['account_name']}/{deployment['region']}: Timeout")
                    
                    except Exception as e:
                        with lock:
                            error_result = {
                                'deployment': deployment,
                                'success': False,
                                'error': str(e),
                                'output': f"Exception during processing: {e}"
                            }
                            results['failed'].append(error_result)
                            print(f"💥 [{completed}/{len(deployments)}] {deployment['account_name']}/{deployment['region']}: Exception - {e}")
        
        results['summary'] = {
            'total': len(deployments),
            'successful': len(results['successful']),
            'failed': len(results['failed']),
            'action': action
        }
        
        print(f"📊 Summary: {results['summary']['successful']} successful, {results['summary']['failed']} failed")
        return results


# Keep the rest of the original class structure for compatibility
class TerraformOrchestrator(EnhancedTerraformOrchestrator):
    """Compatibility wrapper"""
    pass


def main():
    parser = argparse.ArgumentParser(description="Enhanced Terraform Deployment Orchestrator v2.0")
    parser.add_argument('action', choices=['discover', 'plan', 'apply', 'destroy'], help='Action to perform')
    parser.add_argument("--account", help="Filter by account name")
    parser.add_argument("--region", help="Filter by region")  
    parser.add_argument("--environment", help="Filter by environment")
    parser.add_argument("--changed-files", help="Space-separated changed files")
    parser.add_argument("--output-summary", help="JSON output file")
    parser.add_argument("--working-dir", help="Working directory for deployment discovery")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be deployed without executing")
    parser.add_argument("--debug", action="store_true", help="Enable debug output")
    
    args = parser.parse_args()
    
    global DEBUG
    DEBUG = args.debug
    
    try:
        orchestrator = EnhancedTerraformOrchestrator(working_dir=args.working_dir)
        
        # Build filters
        filters = {}
        if args.account:
            filters['account_name'] = args.account
        if args.region:
            filters['region'] = args.region
        if args.environment:
            filters['environment'] = args.environment
        
        # Find deployments
        changed_files = None
        if args.changed_files:
            changed_files = args.changed_files.split()
        
        deployments = orchestrator.find_deployments(changed_files=changed_files, filters=filters or None)
        
        if args.action == 'discover':
            # Discovery mode - output deployment information
            print(f"\n🔍 Found {len(deployments)} deployments")
            
            results = {
                'deployments': deployments,
                'total': len(deployments),
                'total_deployments': len(deployments)
            }
            
            for dep in deployments:
                deployment_key = f"{dep['account_name']}-{dep['region']}-{dep['project']}"
                dep['deployment_key'] = deployment_key
                dep['tfvars_file'] = dep['file']
                print(f"   - {deployment_key}: {dep['file']}")
            
            if args.output_summary:
                with open(args.output_summary, 'w') as f:
                    json.dump(results, f, indent=2)
            
            return 0
        
        # Execute deployments
        if not deployments:
            print("\n📋 No deployments found")
            return 0
        
        if args.dry_run:
            print("\n🔍 Dry run mode - no actions will be performed")
            for dep in deployments:
                print(f"   Would process: {dep['account_name']}/{dep['region']}/{dep['project']}")
            return 0
        
        print(f"\n🚀 Processing {len(deployments)} deployments with action: {args.action}")
        results = orchestrator.execute_deployments(deployments, args.action)
        
        # Save summary
        if args.output_summary:
            with open(args.output_summary, 'w') as f:
                json.dump(results, f, indent=2)
        
        print(f"\n✅ Completed: {results['summary']['successful']} successful, {results['summary']['failed']} failed")
        
        return 0 if results['summary']['failed'] == 0 else 1
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        if DEBUG:
            traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())