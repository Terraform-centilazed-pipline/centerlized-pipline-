#!/usr/bin/env python3
"""
S3 Terraform Deployment Manager
Manages S3 bucket deployments across multiple accounts and regions using template-based approach
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
    # Fallback for environments without PyYAML
    yaml = None

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

class S3DeploymentManager:
    """S3 Deployment Manager for multi-account S3 bucket deployments"""
    
    def __init__(self):
        import os
        self.script_dir = Path(__file__).parent
        # Store the working directory (where discover is run from - has Accounts/)
        self.working_dir = Path.cwd()
        # Check for TERRAFORM_DIR environment variable (used in centralized workflow)
        terraform_dir_env = os.getenv('TERRAFORM_DIR')
        if terraform_dir_env:
            self.project_root = (self.working_dir / terraform_dir_env).resolve()
            debug_print(f"Using TERRAFORM_DIR from environment: {self.project_root}")
            debug_print(f"Working directory (source files): {self.working_dir}")
        else:
            self.project_root = self.script_dir.parent
            self.working_dir = self.project_root
            debug_print(f"Using default project root: {self.project_root}")
        
        self.accounts_config = self._load_accounts_config()
        self.templates_dir = self.project_root / "templates"
        
    def _load_accounts_config(self) -> Dict:
        """Load accounts configuration from accounts.yaml (optional)"""
        accounts_file = self.project_root / "accounts.yaml"
        if not accounts_file.exists():
            debug_print(f"accounts.yaml not found at {accounts_file}, using defaults")
            return {'accounts': {}, 's3_templates': {}, 'regions': {}, 'default_tags': {}}
        
        if yaml is None:
            # Simple YAML parser fallback if PyYAML not available
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
        """Find S3 deployments to process"""
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
                            files.append(file_path)  # Keep as Path object
                            deployment_paths.add(deployment_path)
                    elif file.endswith('.json'):
                        # JSON file changed - look for tfvars in same directory
                        deployment_dir = file_path.parent
                        tfvars_files = list(deployment_dir.glob("*.tfvars"))
                        for tfvars_file in tfvars_files:
                            deployment_path = str(tfvars_file.parent)
                            if deployment_path not in deployment_paths:
                                files.append(tfvars_file)  # Keep as Path object
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
            # Extract account and region from path structure
            # Support both:
            # 1. Full: Accounts/account-name/region/project/file.tfvars
            # 2. Simple: Accounts/account-name/file.tfvars
            path_parts = tfvars_file.parts
            
            if "Accounts" in path_parts:
                accounts_index = path_parts.index("Accounts")
                
                # Full structure: Accounts/account-name/region/project/file.tfvars
                if len(path_parts) > accounts_index + 3:
                    account_name = path_parts[accounts_index + 1]
                    region = path_parts[accounts_index + 2]
                    project = path_parts[accounts_index + 3]
                    
                    # Find account ID from accounts config
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
                
                # Simple structure: Accounts/account-name/file.tfvars
                elif len(path_parts) > accounts_index + 1:
                    account_name = path_parts[accounts_index + 1]
                    
                    # Extract region from tfvars file name or use default
                    region = "us-east-1"  # Default region
                    
                    # Check if accounts_config has this account
                    account_id = None
                    for acc_id, acc_info in self.accounts_config.get('accounts', {}).items():
                        if acc_info.get('account_name') == account_name:
                            account_id = acc_id
                            region = acc_info.get('region', region)
                            break
                    
                    # If no account config, use account_name as account_id
                    if not account_id:
                        account_id = account_name
                        debug_print(f"No account config found for {account_name}, using as account_id")
                    
                    return {
                        'file': str(tfvars_file),
                        'account_id': account_id,
                        'account_name': account_name,
                        'region': region,
                        'project': tfvars_file.stem,  # Use filename without extension as project
                        'deployment_dir': str(tfvars_file.parent),
                        'environment': self.accounts_config.get('accounts', {}).get(account_id, {}).get('environment', 'poc')
                    }
                    
        except Exception as e:
            debug_print(f"Error analyzing {tfvars_file}: {e}")
        
        return None
    
    def _matches_filters(self, deployment_info: Dict, filters: Optional[Dict]) -> bool:
        """Check if deployment matches provided filters"""
        if not filters:
            return True
            
        for key, value in filters.items():
            if key in deployment_info and deployment_info[key] != value:
                return False
        return True
    
    def deploy_s3_buckets(self, deployments: List[Dict], action: str = "plan") -> Dict:
        """Deploy S3 buckets using Terraform - sequential processing like KMS"""
        results = {
            'successful': [],
            'failed': [],
            'summary': {}
        }
        
        print(f"🚀 Starting S3 {action} for {len(deployments)} deployments")
        
        # Process deployments sequentially to avoid terraform.tfvars conflicts
        for i, deployment in enumerate(deployments, 1):
            print(f"🔄 [{i}/{len(deployments)}] Processing {deployment['account_name']}/{deployment['region']}/{deployment['project']}")
            
            try:
                result = self._process_deployment(deployment, action)
                if result['success']:
                    results['successful'].append(result)
                    print(f"✅ {deployment['account_name']}/{deployment['region']}: Success")
                else:
                    results['failed'].append(result)
                    print(f"❌ {deployment['account_name']}/{deployment['region']}: Failed")
                    if DEBUG:
                        print(f"🔍 Error details: {result.get('output', 'No output')[:500]}")
                        
            except Exception as e:
                error_result = {
                    'deployment': deployment,
                    'success': False,
                    'error': str(e),
                    'output': f"Exception during processing: {e}"
                }
                results['failed'].append(error_result)
                print(f"💥 {deployment['account_name']}/{deployment['region']}: Exception - {e}")
        
        # Generate summary
        results['summary'] = {
            'total': len(deployments),
            'successful': len(results['successful']),
            'failed': len(results['failed']),
            'action': action
        }
        
        print(f"📊 Summary: {results['summary']['successful']} successful, {results['summary']['failed']} failed")
        return results
    
    def _process_deployment(self, deployment: Dict, action: str) -> Dict:
        """Process a single deployment - following KMS pattern"""
        import shutil
        
        # Run terraform in main directory like KMS script
        main_dir = self.project_root
        
        try:
            # Clean any existing .terraform directory
            terraform_dir = main_dir / ".terraform"
            if terraform_dir.exists():
                shutil.rmtree(terraform_dir)
            
            # Copy tfvars file to terraform.tfvars in main directory
            # Handle both relative and absolute paths
            tfvars_source = Path(deployment['file'])
            if not tfvars_source.is_absolute():
                # If relative, it's relative to working_dir (where Accounts/ is)
                tfvars_source = self.working_dir / tfvars_source
            
            tfvars_dest = main_dir / "terraform.tfvars"
            shutil.copy2(tfvars_source, tfvars_dest)
            debug_print(f"Copied {tfvars_source} -> {tfvars_dest}")
            
            # Copy policy JSON files referenced in tfvars (if any)
            # This handles the case where tfvars references external JSON files
            # that need to be available in the controller directory
            self._copy_referenced_policy_files(tfvars_source, main_dir, deployment)
            
            # Initialize Terraform with backend config
            state_key = f"s3/{deployment['account_name']}/{deployment['region']}/{deployment['project']}/terraform.tfstate"
            init_cmd = [
                'init', '-input=false',
                f'-backend-config=key={state_key}',
                f'-backend-config=region=us-east-1'
            ]
            
            init_result = self._run_terraform_command(init_cmd, main_dir)
            if init_result['returncode'] != 0:
                # Save init output to file for debugging
                init_error_file = main_dir / "terraform-init-error.log"
                with open(init_error_file, 'w') as f:
                    f.write(f"=== TERRAFORM INIT FAILED ===\n")
                    f.write(f"Command: terraform {' '.join(init_cmd)}\n")
                    f.write(f"Exit Code: {init_result['returncode']}\n")
                    f.write(f"Working Directory: {main_dir}\n\n")
                    f.write("=== STDOUT ===\n")
                    f.write(init_result.get('stdout', init_result['output']))
                    f.write("\n\n=== STDERR ===\n")
                    f.write(init_result.get('stderr', '(captured in output)'))
                    f.write("\n\n=== COMBINED OUTPUT ===\n")
                    f.write(init_result['output'])
                
                # Print key parts of the error for immediate visibility
                print(f"\n🚨 TERRAFORM INIT FAILED for {deployment['account_name']}/{deployment['region']}/{deployment['project']}")
                print(f"📁 Working Directory: {main_dir}")
                print(f"🔧 Command: terraform {' '.join(init_cmd)}")
                print(f"🚦 Exit Code: {init_result['returncode']}")
                print(f"📄 Full output saved to: {init_error_file}")
                
                # Show stderr first (usually has the actual error)
                if 'stderr' in init_result and init_result['stderr'].strip():
                    stderr_lines = init_result['stderr'].strip().split('\n')
                    print(f"\n🔴 STDERR ({len(stderr_lines)} lines):")
                    for line in stderr_lines[-30:]:  # Last 30 lines of stderr
                        if line.strip():
                            print(f"   {line}")
                
                # Show last 20 lines of combined output
                output_lines = init_result['output'].split('\n')
                print(f"\n📋 LAST 20 LINES OF COMBINED OUTPUT:")
                for line in output_lines[-20:]:
                    if line.strip():
                        print(f"   {line}")
                
                return {
                    'deployment': deployment,
                    'success': False,
                    'error': 'Terraform init failed',
                    'output': init_result['output']
                }
            
            # Run the specified action with enhanced error reporting
            plan_file_path = None  # Initialize for all actions
            if action == "plan":
                # Create plans directory if it doesn't exist
                plans_dir = main_dir / "plans"
                plans_dir.mkdir(exist_ok=True)
                
                # Generate plan file name
                plan_filename = f"{deployment['account_name']}_{deployment['region']}_{deployment['project']}.tfplan"
                plan_file_path = plans_dir / plan_filename
                
                cmd = ['plan', '-detailed-exitcode', '-input=false', '-var-file=terraform.tfvars', '-no-color', '-out', str(plan_file_path)]
                debug_print(f"Generating plan file: {plan_file_path}")
            elif action == "apply":
                cmd = ['apply', '-auto-approve', '-input=false', '-var-file=terraform.tfvars', '-no-color']
            elif action == "destroy":
                cmd = ['destroy', '-auto-approve', '-input=false', '-var-file=terraform.tfvars', '-no-color']
            else:
                raise ValueError(f"Unknown action: {action}")
            
            # Set environment variables for more verbose terraform output
            import os
            env = os.environ.copy()
            env['TF_LOG'] = 'DEBUG'  # Enable debug logging
            env['TF_LOG_PATH'] = str(main_dir / f'terraform-{action}-verbose.log')
            self._terraform_env = env  # Store for use in _run_terraform_command
            
            result = self._run_terraform_command(cmd, main_dir)
            
            # Enhanced error reporting with full output capture
            # For terraform plan: 0=no changes, 1=error, 2=changes planned (success)
            is_plan_error = (action == "plan" and result['returncode'] not in [0, 2]) or (action != "plan" and result['returncode'] != 0)
            
            if is_plan_error:
                error_details = f"Terraform {action} failed (exit code: {result['returncode']})"
                
                # Save the complete terraform output to a separate error file for detailed analysis
                error_output_file = main_dir / f"terraform-{action}-error-full.log"
                with open(error_output_file, 'w') as f:
                    f.write(f"=== FULL TERRAFORM {action.upper()} OUTPUT ===\n")
                    f.write(f"Command: terraform {' '.join(cmd)}\n")
                    f.write(f"Exit Code: {result['returncode']}\n")
                    f.write(f"Working Directory: {main_dir}\n\n")
                    f.write("=== COMPLETE OUTPUT ===\n")
                    f.write(result['output'])
                debug_print(f"Complete terraform output saved to: {error_output_file}")
                
                # Get the full terraform output for analysis
                output_lines = result['output'].split('\n')
                
                # Print key diagnostic information immediately (won't be truncated)
                print(f"\n🔍 TERRAFORM DIAGNOSTICS for {deployment['account_name']}/{deployment['region']}/{deployment['project']}:")
                print(f"📁 Working Directory: {main_dir}")
                print(f"📄 Tfvars File: {deployment['file']}")
                print(f"🔧 Command: terraform {' '.join(cmd)}")
                exit_status = "❌ ERROR" if result['returncode'] == 1 else "✅ SUCCESS WITH CHANGES" if result['returncode'] == 2 else f"Exit Code: {result['returncode']}"
                print(f"🚦 Status: {exit_status}")
                print(f"📊 Output Lines: {len(output_lines)}")
                
                # Look for specific terraform resource being processed
                current_resource = "unknown"
                for line in output_lines:
                    if "will be created" in line or "will be updated" in line or "will be destroyed" in line:
                        current_resource = line.strip()
                        print(f"🎯 Last Resource Processing: {current_resource}")
                        break
                
                # Find and display the actual error
                actual_errors = []
                for i, line in enumerate(output_lines):
                    if any(word in line.lower() for word in ["error:", "failed", "invalid", "cannot", "╷"]):
                        # Get surrounding context
                        start = max(0, i-2)
                        end = min(len(output_lines), i+5)
                        error_context = output_lines[start:end]
                        actual_errors.extend(error_context)
                        if len(actual_errors) > 30:  # Limit to prevent overflow
                            break
                
                if actual_errors:
                    print(f"🚨 ACTUAL ERROR DETAILS:")
                    for line in actual_errors:
                        if line.strip():
                            print(f"   {line}")
                else:
                    # Show last significant lines if no explicit errors found
                    print(f"📋 LAST OUTPUT LINES:")
                    for line in output_lines[-10:]:
                        if line.strip():
                            print(f"   {line}")
                
                # Keep the original error details for return value
                error_details += f"\n\nSee terraform-{action}-error-full.log for complete output"
            
            # Determine success based on action type and exit code
            is_successful = (action == "plan" and result['returncode'] in [0, 2]) or (action != "plan" and result['returncode'] == 0)
            
            # Prepare result with plan file info if applicable
            result_data = {
                'deployment': deployment,
                'success': is_successful,
                'error': None if is_successful else error_details,
                'output': result['output']
            }
            
            # Add plan file information for successful plans
            if is_successful and action == "plan":
                result_data['plan_file'] = str(plan_file_path)
                result_data['has_changes'] = result['returncode'] == 2
                debug_print(f"Plan generated successfully: {plan_file_path}")
                debug_print(f"Changes detected: {result['returncode'] == 2}")
                
                # Save plan output as markdown for PR comments
                markdown_file = self._save_plan_as_markdown(deployment, result['output'], result['returncode'] == 2)
                if markdown_file:
                    result_data['markdown_file'] = markdown_file
                    print(f"✅ Generated markdown file: {markdown_file}")
                
                # Convert plan to JSON for OPA validation
                json_file_path = self._convert_plan_to_json(plan_file_path, main_dir)
                if json_file_path:
                    result_data['json_file'] = json_file_path
                    print(f"✅ Generated JSON file: {json_file_path}")
                else:
                    print(f"⚠️ Failed to convert {plan_file_path} to JSON - validation may be skipped")
            
            return result_data
            
        except Exception as e:
            return {
                'deployment': deployment,
                'success': False,
                'error': str(e),
                'output': f"Exception during {action}: {e}"
            }
    
    def _copy_referenced_policy_files(self, tfvars_file: Path, dest_dir: Path, deployment: Dict):
        """
        Copy policy JSON files referenced in tfvars to the destination directory.
        Maintains the same directory structure so Terraform can find them.
        
        Smart lookup:
        1. Try the exact path from tfvars
        2. If not found, look in the deployment directory
        3. Copy to destination preserving the tfvars path
        """
        import shutil
        import re
        
        try:
            # Read tfvars file content
            with open(tfvars_file, 'r') as f:
                tfvars_content = f.read()
            
            # Find all JSON file references in the tfvars
            # Look for patterns like: bucket_policy_file = "Accounts/xxx/yyy.json"
            json_pattern = r'["\']([Aa]ccounts/[^"\']+\.json)["\']'
            json_files = re.findall(json_pattern, tfvars_content)
            
            if not json_files:
                debug_print("No policy JSON files referenced in tfvars")
                return
            
            debug_print(f"Found {len(json_files)} policy file references in tfvars")
            
            for json_file_path in json_files:
                # Get just the filename
                filename = Path(json_file_path).name
                debug_print(f"Looking for policy file: {filename}")
                debug_print(f"  Referenced path: {json_file_path}")
                debug_print(f"  Deployment dir: {deployment.get('deployment_dir', 'NOT SET')}")
                
                # Try to find the actual file
                source_file = None
                
                # Option 1: Try the exact path from tfvars (relative to working_dir)
                candidate1 = self.working_dir / json_file_path
                debug_print(f"  Trying option 1 (tfvars path): {candidate1}")
                if candidate1.exists():
                    source_file = candidate1
                    debug_print(f"✅ Found policy file at tfvars path: {candidate1}")
                else:
                    debug_print(f"  ❌ Not found at option 1")
                    # Option 2: Look in the deployment directory
                    deployment_dir = Path(deployment['deployment_dir'])
                    if not deployment_dir.is_absolute():
                        deployment_dir = self.working_dir / deployment_dir
                    
                    candidate2 = deployment_dir / filename
                    debug_print(f"  Trying option 2 (deployment dir): {candidate2}")
                    if candidate2.exists():
                        source_file = candidate2
                        debug_print(f"✅ Found policy file in deployment dir: {candidate2}")
                    else:
                        debug_print(f"  ❌ Not found at option 2")
                        # Option 3: Search for the file in deployment directory recursively
                        debug_print(f"  Trying option 3 (recursive search in {deployment_dir})")
                        for found_file in deployment_dir.rglob(filename):
                            source_file = found_file
                            debug_print(f"✅ Found policy file recursively: {found_file}")
                            break
                        if not source_file:
                            debug_print(f"  ❌ Not found in recursive search")
                
                if source_file:
                    # Destination preserves the tfvars path (what terraform expects)
                    dest_file = dest_dir / json_file_path
                    
                    # Create destination directory if needed
                    dest_file.parent.mkdir(parents=True, exist_ok=True)
                    
                    # Copy the policy file
                    shutil.copy2(source_file, dest_file)
                    print(f"✅ Copied policy file: {filename}")
                    debug_print(f"   From: {source_file}")
                    debug_print(f"   To:   {dest_file}")
                else:
                    print(f"⚠️ Warning: Policy file '{filename}' not found")
                    print(f"   Searched in tfvars path: {self.working_dir / json_file_path}")
                    print(f"   Searched in deployment: {deployment['deployment_dir']}")
                    debug_print(f"Full tfvars path tried: {json_file_path}")
                    
        except Exception as e:
            # Don't fail the deployment, just warn
            print(f"⚠️ Warning: Error copying policy files: {e}")
            debug_print(f"Error in _copy_referenced_policy_files: {e}")
    
    def _run_terraform_command(self, cmd: List[str], cwd: Path) -> Dict:
        """Run terraform command and return result"""
        full_cmd = ['terraform'] + cmd
        debug_print(f"Running: {' '.join(full_cmd)} in {cwd}")
        
        try:
            # Use enhanced environment if available (set in _process_deployment)
            import os
            env = getattr(self, '_terraform_env', os.environ.copy())
            
            result = subprocess.run(
                full_cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=600,  # 10 minute timeout
                env=env
            )
            
            output = result.stdout + result.stderr
            clean_output = strip_ansi_colors(output)
            
            # Save full terraform output to file for debugging (including init)
            if 'plan' in cmd or 'apply' in cmd or 'init' in cmd:
                action = 'plan' if 'plan' in cmd else 'apply' if 'apply' in cmd else 'init'
                output_file = cwd / f"terraform-{action}-debug.log"
                with open(output_file, 'w') as f:
                    f.write(f"Command: {' '.join(full_cmd)}\n")
                    f.write(f"Return Code: {result.returncode}\n")
                    f.write(f"CWD: {cwd}\n\n")
                    f.write(f"=== STDOUT ({len(result.stdout)} chars) ===\n")
                    f.write(result.stdout if result.stdout else "(empty)\n")
                    f.write(f"\n=== STDERR ({len(result.stderr)} chars) ===\n")
                    f.write(result.stderr if result.stderr else "(empty)\n")
                    f.write(f"\n=== COMBINED OUTPUT ===\n")
                    f.write(clean_output)
                debug_print(f"Full terraform output saved to: {output_file}")
            
            return {
                'returncode': result.returncode,
                'output': clean_output,
                'stdout': result.stdout,
                'stderr': result.stderr
            }
            
        except subprocess.TimeoutExpired:
            return {
                'returncode': 1,
                'output': f"Command timed out after 600 seconds: {' '.join(full_cmd)}"
            }
        except Exception as e:
            return {
                'returncode': 1,
                'output': f"Error running command: {e}"
            }

    def _convert_plan_to_json(self, plan_file_path: Path, main_dir: Path) -> Optional[str]:
        """Convert terraform plan file to JSON format"""
        try:
            # Generate JSON filename based on plan filename
            plan_filename = plan_file_path.stem  # removes .tfplan extension
            json_filename = f"{plan_filename}.json"
            
            # Create terraform-json directory in project root (where terraform runs)
            json_dir = self.project_root / "terraform-json"
            json_dir.mkdir(exist_ok=True)
            json_file_path = json_dir / json_filename
            
            # Also create in working_dir if different (for centralized workflow)
            working_json_dir = self.working_dir / "terraform-json"
            if self.working_dir != self.project_root:
                working_json_dir.mkdir(exist_ok=True)
                working_json_file_path = working_json_dir / json_filename
            else:
                working_json_file_path = json_file_path
            
            debug_print(f"Converting {plan_file_path} to {json_file_path}")
            
            # Run terraform show -json to convert plan to JSON
            result = subprocess.run(
                ['terraform', 'show', '-json', str(plan_file_path)],
                cwd=main_dir,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            if result.returncode == 0 and result.stdout:
                # Validate JSON output
                try:
                    json.loads(result.stdout)  # Validate JSON
                    
                    # Write JSON to file in project root
                    with open(json_file_path, 'w') as f:
                        f.write(result.stdout)
                    
                    debug_print(f"Successfully converted plan to JSON: {json_file_path}")
                    
                    # Also write to working_dir if different (for centralized workflow)
                    if self.working_dir != self.project_root:
                        with open(working_json_file_path, 'w') as f:
                            f.write(result.stdout)
                        debug_print(f"Also copied JSON to working_dir: {working_json_file_path}")
                    
                    return str(json_file_path)
                    
                except json.JSONDecodeError as e:
                    print(f"❌ Invalid JSON output from terraform show: {e}")
                    return None
            else:
                print(f"❌ terraform show failed for {plan_file_path}")
                print(f"Exit code: {result.returncode}")
                print(f"Error: {result.stderr}")
                return None
                
        except subprocess.TimeoutExpired:
            print(f"❌ terraform show timed out for {plan_file_path}")
            return None
        except Exception as e:
            print(f"❌ Error converting plan to JSON: {e}")
            return None

    def _save_plan_as_markdown(self, deployment: Dict, plan_output: str, has_changes: bool) -> Optional[str]:
        """Save terraform plan output as markdown file for PR comments"""
        try:
            # Create plan-markdown directory in project root
            markdown_dir = self.project_root / "plan-markdown"
            markdown_dir.mkdir(exist_ok=True)
            
            # Also create in working_dir if different (for centralized workflow)
            if self.working_dir != self.project_root:
                working_markdown_dir = self.working_dir / "plan-markdown"
                working_markdown_dir.mkdir(exist_ok=True)
            
            # Generate markdown filename
            deployment_name = f"{deployment['account_name']}-{deployment['region']}-{deployment['project']}"
            markdown_filename = f"{deployment_name}-plan.md"
            markdown_file_path = markdown_dir / markdown_filename
            
            debug_print(f"Creating markdown plan file: {markdown_file_path}")
            
            # Create markdown content
            status_emoji = "🔄" if has_changes else "➖"
            status_text = "Changes Detected" if has_changes else "No Changes"
            
            markdown_content = f"""### 📋 {deployment_name}

**Status:** {status_emoji} {status_text}

<details><summary><strong>🔍 Click to view terraform plan</strong></summary>

```terraform
{plan_output}
```

</details>

---
"""
            
            # Write markdown to file
            with open(markdown_file_path, 'w') as f:
                f.write(markdown_content)
            
            debug_print(f"Successfully created markdown plan: {markdown_file_path}")
            
            # Also write to working_dir if different (for centralized workflow)
            if self.working_dir != self.project_root:
                working_markdown_file_path = working_markdown_dir / markdown_filename
                with open(working_markdown_file_path, 'w') as f:
                    f.write(markdown_content)
                debug_print(f"Also copied markdown to working_dir: {working_markdown_file_path}")
            
            return str(markdown_file_path)
            
        except Exception as e:
            print(f"❌ Error creating markdown plan: {e}")
            return None


def main():
    parser = argparse.ArgumentParser(description="S3 Deployment Manager")
    parser.add_argument('action', choices=['discover', 'plan', 'apply', 'destroy'], help='Action to perform')
    parser.add_argument("--account", help="Filter by account name")
    parser.add_argument("--region", help="Filter by region")
    parser.add_argument("--environment", help="Filter by environment")
    parser.add_argument("--changed-files", help="Space-separated changed files")
    parser.add_argument("--output-summary", help="JSON output file")
    parser.add_argument("--deployments-json", help="Load deployments from JSON")
    parser.add_argument("--state-bucket", help="S3 bucket for Terraform state")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be deployed without executing")
    parser.add_argument("--debug", action="store_true", help="Enable debug output")
    
    args = parser.parse_args()
    
    global DEBUG
    DEBUG = args.debug
    
    debug_print(f"Arguments: {vars(args)}")
    
    try:
        manager = S3DeploymentManager()
        
        # Build filters
        filters = {}
        if args.account:
            filters['account_name'] = args.account
        if args.region:
            filters['region'] = args.region
        if args.environment:
            filters['environment'] = args.environment
        
        # Get deployments
        if args.deployments_json and Path(args.deployments_json).exists():
            debug_print(f"Loading deployments from JSON: {args.deployments_json}")
            with open(args.deployments_json, 'r') as f:
                data = json.load(f)
            deployments = data.get('deployments', data) if isinstance(data, dict) else data
        else:
            debug_print("Discovering deployments from filesystem")
            changed_files = args.changed_files.split() if args.changed_files else None
            deployments = manager.find_deployments(changed_files, filters)
        
        print(f"🔍 Processing {len(deployments)} deployments")
        
        # Initialize results for all actions
        results = {}
        
        if args.action == 'discover':
            results = {
                'deployments': deployments, 
                'total': len(deployments),
                'total_deployments': len(deployments)  # Match what workflow expects
            }
            for dep in deployments:
                deployment_key = f"{dep['account_name']}-{dep['region']}-{dep['project']}"
                dep['deployment_key'] = deployment_key
                dep['tfvars_file'] = dep['file']  # Match KMS format
                print(f"   - {deployment_key}: {dep['file']}")
        
        elif args.action in ['plan', 'apply', 'destroy']:
            if args.dry_run:
                print("🔍 Dry run - no actions will be performed")
                return
                
            # Execute deployments
            deployment_results = manager.deploy_s3_buckets(deployments, args.action)
            
            # Format results to match KMS output
            action_plural = f"{args.action}s" if args.action != 'apply' else 'applies'
            results = {
                'total_deployments': len(deployments),
                'plans': [],
                'has_changes': False,
                f'successful_{action_plural}': deployment_results['summary']['successful'],
                f'failed_{action_plural}': deployment_results['summary']['failed']
            }
            
            for result in deployment_results['successful']:
                dep = result['deployment']
                plan_entry = {
                    'deployment': f"{dep['account_name']}-{dep['region']}-{dep['project']}",
                    'status': 'success',
                    'has_changes': result.get('has_changes', True),  # Use actual detection
                    'plan_output': result['output'][:500] + "..." if len(result['output']) > 500 else result['output']  # Brief summary for JSON
                }
                # Add plan file information if available
                if 'plan_file' in result:
                    plan_entry['plan_file'] = result['plan_file']
                    debug_print(f"Plan file recorded: {result['plan_file']}")
                
                results['plans'].append(plan_entry)
                if result.get('has_changes', True):
                    results['has_changes'] = True
                
            for result in deployment_results['failed']:
                dep = result['deployment']
                results['plans'].append({
                    'deployment': f"{dep['account_name']}-{dep['region']}-{dep['project']}",
                    'status': 'failed',
                    'has_changes': False,
                    'error': result['error'],
                    'plan_output': result['output'][:500] + "..." if len(result['output']) > 500 else result['output']  # Brief summary for JSON
                })
        
        # Save results to JSON if requested
        if args.output_summary:
            with open(args.output_summary, 'w') as f:
                json.dump(results, f, indent=2)
            debug_print(f"Results saved to {args.output_summary}")
        
        # Exit with error if any deployments failed
        if args.action in ['plan', 'apply', 'destroy'] and results.get(f'failed_{args.action}s', 0) > 0:
            exit(1)
            
    except Exception as e:
        print(f"💥 Error: {e}")
        if args.debug:
            import traceback
            traceback.print_exc()
        exit(1)

if __name__ == "__main__":
    main()