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

class EnhancedTerraformOrchestrator:
    """Enhanced Terraform Orchestrator with dynamic backend keys and improved PR comments"""
    
    def __init__(self, working_dir=None):
        import os
        self.script_dir = Path(__file__).parent
        self.working_dir = Path(working_dir) if working_dir else Path.cwd()
        
        terraform_dir_env = os.getenv('TERRAFORM_DIR')
        if terraform_dir_env:
            self.project_root = (self.working_dir / terraform_dir_env).resolve()
        else:
            self.project_root = self.script_dir.parent
            
        self.accounts_config = self._load_accounts_config()
        self.templates_dir = self.project_root / "templates"
        
        # Service mapping for backend key generation
        self.service_mapping = {
            's3_buckets': 's3',
            'kms_keys': 'kms',
            'iam_roles': 'iam',
            'iam_policies': 'iam',
            'iam_users': 'iam',
            'lambda_functions': 'lambda',
            'sqs_queues': 'sqs',
            'sns_topics': 'sns',
            'ec2_instances': 'ec2',
            'vpc_config': 'vpc',
            'rds_instances': 'rds',
            'dynamodb_tables': 'dynamodb',
            'cloudfront_distributions': 'cloudfront',
            'route53_zones': 'route53'
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
    
    def _extract_resource_details(self, line: str, details: Dict):
        """Extract resource details like ARNs, names from terraform output"""
        # Extract ARNs
        arn_match = re.search(r'arn:aws:[^:]+:[^:]*:[^:]*:[^"\']+', line)
        if arn_match:
            arn = arn_match.group(0)
            service = arn.split(':')[2] if ':' in arn else 'unknown'
            if service not in details:
                details[service] = {'arns': [], 'names': []}
            details[service]['arns'].append(arn)
        
        # Extract resource names/IDs
        # Patterns for common AWS resources
        name_patterns = [
            (r'bucket\s*=\s*"([^"]+)"', 's3'),
            (r'function_name\s*=\s*"([^"]+)"', 'lambda'),
            (r'queue_url\s*=\s*"([^"]+)"', 'sqs'),
            (r'topic_arn\s*=\s*"([^"]+)"', 'sns'),
            (r'id\s*=\s*"([^"]+)"', 'general')
        ]
        
        for pattern, service in name_patterns:
            match = re.search(pattern, line)
            if match:
                name = match.group(1)
                if service not in details:
                    details[service] = {'arns': [], 'names': []}
                if name not in details[service]['names']:
                    details[service]['names'].append(name)

    def _generate_enhanced_pr_comment(self, deployment: Dict, result: Dict, services: List[str]) -> str:
        """Generate enhanced PR comment with service details and outputs for any Terraform deployment"""
        deployment_name = f"{deployment['account_name']}-{deployment['project']}"
        orchestrator_ver = result.get('orchestrator_version', ORCHESTRATOR_VERSION)
        
        if not result['success']:
            # Error comment
            return f"""### ❌ {deployment_name} - Deployment Failed

**Services:** {', '.join(services) if services else 'None detected'}
**Backend Key:** `{result.get('backend_key', 'unknown')}`

**Error:** {result.get('error', 'Unknown error')}

<details><summary><strong>🚨 Error Details</strong></summary>

```
{result.get('output', 'No output available')[:2000]}
```

</details>

Please fix the errors and push to a new branch.

---
"""
        
        # Success comment
        outputs = self._extract_terraform_outputs(result.get('output', ''), result.get('action', 'unknown'))
        
        comment = f"""### ✅ {deployment_name} - Deployment Successful

**Services:** {', '.join(services) if services else 'None detected'}
**Backend Key:** `{result.get('backend_key', 'unknown')}`
**Action:** {result.get('action', 'unknown').title()}
**Orchestrator Version:** v{orchestrator_ver}

"""
        
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
        
        # Add terraform output details
        comment += f"""<details><summary><strong>🔍 Full Terraform Output</strong></summary>

```terraform
{result.get('output', 'No output available')[:3000]}
```

</details>

---
"""
        
        return comment

    def _process_deployment_enhanced(self, deployment: Dict, action: str) -> Dict:
        """Enhanced deployment processing with dynamic backend and better error handling - Version 2.0"""
        try:
            debug_print(f"Processing deployment (v{ORCHESTRATOR_VERSION}): {deployment}")
            
            # Resolve tfvars file path
            tfvars_file = Path(deployment['file'])
            if not tfvars_file.is_absolute():
                tfvars_file = self.working_dir / tfvars_file
            
            # Validate tfvars file
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
            
            # Detect services from tfvars
            services = self._detect_services_from_tfvars(tfvars_file)
            
            # Generate dynamic backend key with resource name
            backend_key = self._generate_dynamic_backend_key(deployment, services, tfvars_file)
            
            # Copy required files to working directory
            main_dir = self.project_root
            terraform_dir = main_dir / ".terraform"
            if terraform_dir.exists():
                shutil.rmtree(terraform_dir)
            
            tfvars_dest = main_dir / "terraform.tfvars"
            shutil.copy2(tfvars_file, tfvars_dest)
            debug_print(f"Copied {tfvars_file} -> {tfvars_dest}")
            
            # Copy policy JSON files referenced in tfvars (if any)
            try:
                debug_print(f"About to call _copy_referenced_policy_files")
                self._copy_referenced_policy_files(tfvars_file, main_dir, deployment)
                debug_print(f"Finished calling _copy_referenced_policy_files")
            except Exception as copy_err:
                print(f"⚠️ Exception in _copy_referenced_policy_files: {copy_err}")
                import traceback
                traceback.print_exc()
            
            # Initialize Terraform with dynamic backend
            # -upgrade flag ensures latest module versions are downloaded from GitHub
            # -reconfigure forces backend reconfiguration and ignores cached state
            init_cmd = [
                'init', '-input=false', '-upgrade', '-reconfigure',
                f'-backend-config=key={backend_key}',
                f'-backend-config=region=us-east-1'
            ]
            
            print(f"🔄 Initializing Terraform with backend key: {backend_key}")
            print(f"🔧 Using -reconfigure to ensure fresh state download")
            
            init_result = self._run_terraform_command(init_cmd, main_dir)
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
            
            # Run terraform refresh first to sync state with AWS reality
            print(f"🔄 Refreshing state from AWS to detect drift...")
            refresh_result = self._run_terraform_command(['refresh', '-input=false', '-var-file=terraform.tfvars'], main_dir)
            if refresh_result['returncode'] != 0:
                print(f"⚠️ Warning: Refresh had issues (may be expected if resources deleted): {refresh_result['stderr'][:500]}")
            else:
                print(f"✅ State refreshed from AWS")
            
            # Run terraform action
            if action == "plan":
                # Save plan to file for JSON conversion
                plan_filename = f"{deployment['account_name']}-{deployment['project']}.tfplan"
                plan_file = main_dir / plan_filename
                cmd = ['plan', '-detailed-exitcode', '-input=false', '-refresh=true', '-var-file=terraform.tfvars', '-no-color', f'-out={plan_filename}']
                print(f"📋 Running terraform plan...")
            elif action == "apply":
                cmd = ['apply', '-auto-approve', '-input=false', '-refresh=true', '-var-file=terraform.tfvars', '-no-color']
            else:
                cmd = [action, '-input=false', '-var-file=terraform.tfvars', '-no-color']
            
            result = self._run_terraform_command(cmd, main_dir)
            
            # Determine success based on action and exit code
            if action == "plan":
                success = result['returncode'] in [0, 2]  # 0=no changes, 2=changes detected
                has_changes = result['returncode'] == 2
                
                # Generate JSON plan and markdown for OPA validation if plan succeeded
                if success and plan_file.exists():
                    # Create JSON plan
                    json_dir = self.working_dir / "terraform-json"
                    json_dir.mkdir(exist_ok=True)
                    
                    json_filename = f"{deployment['account_name']}-{deployment['project']}.json"
                    json_file = json_dir / json_filename
                    
                    show_result = self._run_terraform_command(['show', '-json', plan_filename], main_dir)
                    if show_result['returncode'] == 0:
                        with open(json_file, 'w') as f:
                            f.write(show_result['stdout'])
                        print(f"📄 Generated JSON plan: {json_file}")
                        debug_print(f"JSON plan saved to: {json_file}")
                    else:
                        print(f"⚠️ Warning: Failed to generate JSON plan for {deployment['account_name']}")
                        debug_print(f"terraform show -json failed: {show_result.get('stderr', 'unknown error')}")
                    
                    # Create markdown plan for PR comments
                    markdown_dir = self.working_dir / "plan-markdown"
                    markdown_dir.mkdir(exist_ok=True)
                    
                    markdown_filename = f"{deployment['account_name']}-{deployment['project']}.md"
                    markdown_file = markdown_dir / markdown_filename
                    
                    show_md_result = self._run_terraform_command(['show', plan_filename], main_dir)
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
            
            return {
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
                'orchestrator_version': ORCHESTRATOR_VERSION
            }
            
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

    def _run_terraform_command(self, cmd: List[str], cwd: Path) -> Dict:
        """Run terraform command and return enhanced result"""
        full_cmd = ['terraform'] + cmd
        debug_print(f"Running: {' '.join(full_cmd)} in {cwd}")
        
        try:
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
            
            return {
                'returncode': result.returncode,
                'stdout': result.stdout,
                'stderr': result.stderr,
                'output': result.stdout + result.stderr
            }
            
        except subprocess.TimeoutExpired:
            return {
                'returncode': 124,
                'stdout': '',
                'stderr': 'Command timed out after 30 minutes',
                'output': 'Command timed out after 30 minutes'
            }
        except Exception as e:
            return {
                'returncode': 1,
                'stdout': '',
                'stderr': str(e),
                'output': f"Error running command: {e}"
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
            
            # Find all JSON file references: bucket_policy_file = "Accounts/xxx/yyy.json"
            json_pattern = r'["\']([Aa]ccounts/[^"\']+\.json)["\']'
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

    def find_deployments(self, changed_files=None, filters=None):
        """Find deployments to process from changed files"""
        debug_print(f"find_deployments called with changed_files={changed_files}, filters={filters}")
        
        if changed_files:
            print(f"📋 Processing {len(changed_files)} changed files")
            deployment_paths = set()
            files = []
            for file in changed_files:
                file_path = Path(file)
                if file_path.exists():
                    if file.endswith('.tfvars'):
                        # Direct tfvars file
                        deployment_path = str(file_path.parent)
                        if deployment_path not in deployment_paths:
                            files.append(file_path)
                            deployment_paths.add(deployment_path)
                    elif file.endswith('.json'):
                        # JSON file changed - look for tfvars in same directory
                        deployment_dir = file_path.parent
                        tfvars_files = list(deployment_dir.glob("*.tfvars"))
                        for tfvars_file in tfvars_files:
                            deployment_path = str(tfvars_file.parent)
                            if deployment_path not in deployment_paths:
                                files.append(tfvars_file)
                                deployment_paths.add(deployment_path)
                                debug_print(f"Found tfvars file {tfvars_file} for changed JSON {file}")
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
        """Analyze tfvars file and extract deployment information"""
        try:
            path_parts = tfvars_file.parts
            
            if "Accounts" in path_parts:
                accounts_index = path_parts.index("Accounts")
                
                # Full structure: Accounts/account-name/region/project/file.tfvars
                if len(path_parts) > accounts_index + 3:
                    account_name = path_parts[accounts_index + 1]
                    region = path_parts[accounts_index + 2]
                    project = path_parts[accounts_index + 3]
                    
                    account_id = None
                    for acc_id, acc_info in self.accounts_config.get('accounts', {}).items():
                        if acc_info.get('account_name') == account_name:
                            account_id = acc_id
                            break
                    
                    if account_id:
                        return {
                            'file': str(tfvars_file),
                            'account_id': account_id,
                            'account_name': account_name,
                            'region': region,
                            'project': project,
                            'deployment_dir': str(tfvars_file.parent),
                            'environment': self.accounts_config['accounts'][account_id].get('environment', 'unknown')
                        }
                
                # Simple structure: Accounts/project-name/file.tfvars
                elif len(path_parts) > accounts_index + 1:
                    project = path_parts[accounts_index + 1]
                    region = "us-east-1"
                    
                    # Extract real account_name from tfvars content
                    account_name = self._extract_account_name_from_tfvars(tfvars_file)
                    
                    # If not found in tfvars, try accounts config
                    if not account_name:
                        account_id = None
                        for acc_id, acc_info in self.accounts_config.get('accounts', {}).items():
                            if acc_info.get('account_name') == project:
                                account_id = acc_id
                                account_name = acc_info.get('account_name')
                                region = acc_info.get('region', region)
                                break
                        
                        if not account_name:
                            account_name = project
                            account_id = project
                            debug_print(f"No account config found for {project}, using project name as account")
                    else:
                        # Find account_id from account_name
                        account_id = None
                        for acc_id, acc_info in self.accounts_config.get('accounts', {}).items():
                            if acc_info.get('account_name') == account_name:
                                account_id = acc_id
                                region = acc_info.get('region', region)
                                break
                        
                        if not account_id:
                            account_id = account_name
                            debug_print(f"No account_id found for {account_name}, using account_name")
                    
                    return {
                        'file': str(tfvars_file),
                        'account_id': account_id,
                        'account_name': account_name,
                        'region': region,
                        'project': tfvars_file.stem,
                        'deployment_dir': str(tfvars_file.parent),
                        'environment': self.accounts_config.get('accounts', {}).get(account_id, {}).get('environment', 'poc')
                    }
                    
        except Exception as e:
            debug_print(f"Error analyzing {tfvars_file}: {e}")
        
        return None
    
    def _extract_account_name_from_tfvars(self, tfvars_file: Path) -> Optional[str]:
        """Extract the real account_name from tfvars file content"""
        try:
            content = tfvars_file.read_text()
            match = re.search(r'account_name\s*=\s*"([^"]+)"', content)
            if match:
                return match.group(1)
            return None
        except Exception as e:
            debug_print(f"Error extracting account name from {tfvars_file}: {e}")
            return None
    
    def _matches_filters(self, deployment_info: Dict, filters: Optional[Dict]) -> bool:
        """Check if deployment matches provided filters"""
        if not filters:
            return True
            
        for key, value in filters.items():
            if key in deployment_info and deployment_info[key] != value:
                return False
        return True
    
    def execute_deployments(self, deployments: List[Dict], action: str = "plan") -> Dict:
        """Execute terraform deployments - sequential processing"""
        results = {
            'successful': [],
            'failed': [],
            'summary': {}
        }
        
        print(f"🚀 Starting {action} for {len(deployments)} deployments")
        
        for i, deployment in enumerate(deployments, 1):
            print(f"🔄 [{i}/{len(deployments)}] Processing {deployment['account_name']}/{deployment['region']}/{deployment['project']}")
            
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
        
        results['summary'] = {
            'total': len(deployments),
            'successful': len(results['successful']),
            'failed': len(results['failed']),
            'action': action
        }
        
        print(f"📊 Summary: {results['summary']['successful']} successful, {results['summary']['failed']} failed")
        return results
    
    def process_deployments_enhanced(self, deployments: List[Dict], action: str) -> List[Dict]:
        """Process deployments with enhanced features"""
        results = []
        
        for deployment in deployments:
            print(f"\n🚀 Processing {deployment['account_name']}/{deployment['project']} - {action}")
            
            result = self._process_deployment_enhanced(deployment, action)
            results.append(result)
            
            # Generate and print enhanced PR comment
            services = result.get('services', [])
            pr_comment = self._generate_enhanced_pr_comment(deployment, result, services)
            
            print("\n📝 PR Comment:")
            print(pr_comment)
            
            # Save PR comment to file
            comment_dir = self.project_root / "pr-comments"
            comment_dir.mkdir(exist_ok=True)
            
            comment_file = comment_dir / f"{deployment['account_name']}-{deployment['project']}-comment.md"
            with open(comment_file, 'w') as f:
                f.write(pr_comment)
            
            print(f"💾 PR comment saved to: {comment_file}")
        
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
    import sys
    sys.exit(main())