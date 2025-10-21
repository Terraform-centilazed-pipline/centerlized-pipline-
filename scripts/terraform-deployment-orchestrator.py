#!/usr/bin/env python3
"""
Terraform Deployment Orchestrator
Universal deployment manager for all AWS resources (S3, IAM, KMS, VPC, EC2, etc.)
Supports multi-account, multi-region deployments with template-based approach

Performance Optimizations:
- Parallel discovery of deployment files
- Efficient subprocess handling with proper timeouts
- Minimal file I/O operations
- Smart caching of account configurations
"""

import argparse
import json
import os
import re
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Set

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

DEBUG = False  # Global debug flag


def debug_print(msg: str) -> None:
    """Print debug messages if DEBUG is enabled"""
    if DEBUG:
        print(f"🐛 DEBUG: {msg}")


def strip_ansi_colors(text: str) -> str:
    """Remove ANSI color codes from text - optimized regex"""
    return re.sub(r'\x1b\[[0-9;]*m', '', text)


class TerraformOrchestrator:
    """Universal Terraform deployment orchestrator for all AWS resources"""
    
    __slots__ = ('script_dir', 'working_dir', 'project_root', 'accounts_config', 
                 'templates_dir', '_terraform_env', '_deployment_cache')
    
    def __init__(self):
        self.script_dir = Path(__file__).parent
        self.working_dir = Path.cwd()
        self._deployment_cache: Dict[str, Dict] = {}
        
        # Check for TERRAFORM_DIR environment variable (centralized workflow)
        terraform_dir_env = os.getenv('TERRAFORM_DIR')
        if terraform_dir_env:
            self.project_root = (self.working_dir / terraform_dir_env).resolve()
            debug_print(f"TERRAFORM_DIR: {self.project_root}")
            debug_print(f"Working directory: {self.working_dir}")
        else:
            self.project_root = self.script_dir.parent
            self.working_dir = self.project_root
            debug_print(f"Project root: {self.project_root}")
        
        self.templates_dir = self.project_root / "templates"
        self.accounts_config = self._load_accounts_config()
        self._terraform_env = os.environ.copy()
        
    def _load_accounts_config(self) -> Dict:
        """Load accounts configuration - cached for performance"""
        accounts_file = self.project_root / "accounts.yaml"
        
        if not accounts_file.exists():
            debug_print("accounts.yaml not found, using defaults")
            return {'accounts': {}, 'regions': {}, 'default_tags': {}}
        
        try:
            if HAS_YAML:
                with open(accounts_file, 'r') as f:
                    return yaml.safe_load(f) or {}
            else:
                # Lightweight YAML parser fallback
                return self._parse_yaml_simple(accounts_file)
        except Exception as e:
            print(f"⚠️ Error loading accounts.yaml: {e}")
            return {'accounts': {}, 'regions': {}, 'default_tags': {}}
    
    def _parse_yaml_simple(self, file_path: Path) -> Dict:
        """Minimal YAML parser for basic structure - optimized"""
        config = {'accounts': {}, 'regions': {}, 'default_tags': {}}
        
        with open(file_path, 'r') as f:
            lines = [l.strip() for l in f if l.strip() and not l.strip().startswith('#')]
        
        current_section = None
        current_key = None
        
        for line in lines:
            if line.endswith(':') and not line.startswith(' '):
                key = line[:-1]
                if key in config:
                    current_section = key
                    current_key = None
            elif ':' in line and current_section:
                parts = line.split(':', 1)
                key, value = parts[0].strip(), parts[1].strip().strip("'\"")
                if current_section == 'accounts' and key.isdigit():
                    current_key = key
                    config['accounts'][current_key] = {}
                elif current_key:
                    config['accounts'][current_key][key] = value
        
        return config
    
    def find_deployments(self, changed_files: Optional[List[str]] = None, 
                        filters: Optional[Dict] = None) -> List[Dict]:
        """
        Discover deployments from filesystem - OPTIMIZED with parallel processing
        
        Args:
            changed_files: List of changed files (from PR/Git)
            filters: Dict of filters (account_name, region, environment, etc.)
        
        Returns:
            List of deployment info dictionaries
        """
        print("🔍 Discovering deployments...")
        debug_print(f"Working directory (where Accounts/ should be): {self.working_dir}")
        debug_print(f"Project root (where main.tf is): {self.project_root}")
        
        accounts_dir = self.working_dir / "Accounts"
        debug_print(f"Looking for Accounts directory at: {accounts_dir}")
        
        if not accounts_dir.exists():
            print(f"⚠️ No Accounts directory found at {accounts_dir}")
            # Try to list what IS in working_dir to help debug
            if self.working_dir.exists():
                try:
                    contents = list(self.working_dir.iterdir())
                    debug_print(f"Contents of {self.working_dir}: {[p.name for p in contents[:10]]}")
                except Exception as e:
                    debug_print(f"Could not list directory: {e}")
            return []
        
        # Build file list to analyze
        files_to_check: Set[Path] = set()
        
        if changed_files:
            # Only check changed files - fastest path
            debug_print(f"Checking {len(changed_files)} changed files")
            for file_str in changed_files:
                file_path = self.working_dir / file_str
                if file_path.exists() and file_path.suffix in {'.tfvars', '.json', '.yaml', '.yml'}:
                    files_to_check.add(file_path)
        else:
            # Scan all deployment files - use glob for speed
            debug_print("Scanning all deployment files")
            for pattern in ['**/*.tfvars', '**/*.json', '**/*.yaml']:
                files_to_check.update(accounts_dir.glob(pattern))
        
        if not files_to_check:
            print("ℹ️ No deployment files found")
            return []
        
        debug_print(f"Analyzing {len(files_to_check)} files...")
        
        # Parallel processing for large file sets
        deployments = []
        if len(files_to_check) > 10:
            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = {executor.submit(self._analyze_deployment_file, f): f 
                          for f in files_to_check}
                
                for future in as_completed(futures):
                    result = future.result()
                    if result and self._matches_filters(result, filters):
                        deployments.append(result)
        else:
            # Sequential for small sets (less overhead)
            for file_path in files_to_check:
                result = self._analyze_deployment_file(file_path)
                if result and self._matches_filters(result, filters):
                    deployments.append(result)
        
        print(f"✅ Found {len(deployments)} deployments")
        return deployments
    
    def _analyze_deployment_file(self, file_path: Path) -> Optional[Dict]:
        """Analyze a deployment file and extract metadata - OPTIMIZED"""
        # Cache check
        cache_key = str(file_path)
        if cache_key in self._deployment_cache:
            return self._deployment_cache[cache_key]
        
        try:
            # CRITICAL: Only .tfvars files are deployment configs
            # .json files are policies, .yaml are configs - not deployments
            if file_path.suffix != '.tfvars':
                debug_print(f"Skipping {file_path.name}: Not a tfvars file (type: {file_path.suffix})")
                return None
            
            # Fast path extraction from path structure
            # Expected patterns:
            # 1. Accounts/<account>/<region>/<project>/<file>  (4 parts after Accounts)
            # 2. Accounts/<project>/<file>                      (2 parts after Accounts)
            parts = file_path.parts
            if 'Accounts' not in parts:
                debug_print(f"Skipping {file_path}: No 'Accounts' in path")
                return None
            
            accounts_idx = parts.index('Accounts')
            parts_after_accounts = len(parts) - accounts_idx - 1
            
            debug_print(f"Analyzing: {file_path.name}, parts after Accounts: {parts_after_accounts}")
            
            # Pattern 1: Full path with account/region/project/file
            if parts_after_accounts >= 4:
                account_name = parts[accounts_idx + 1]
                region = parts[accounts_idx + 2]
                project = parts[accounts_idx + 3]
            # Pattern 2: Simplified path with project/file (use project as all identifiers)
            elif parts_after_accounts >= 2:
                project = parts[accounts_idx + 1]
                account_name = project  # Use project name as account
                region = 'us-east-1'  # Default region
                debug_print(f"Using simplified pattern: project={project}")
            else:
                debug_print(f"Skipping {file_path}: Not enough path components ({parts_after_accounts} parts)")
                return None
            
            # Get account ID from config (fast dict lookup)
            account_id = (self.accounts_config.get('accounts', {})
                         .get(account_name, {})
                         .get('account_id', account_name))
            
            environment = (self.accounts_config.get('accounts', {})
                          .get(account_id, {})
                          .get('environment', 'poc'))
            
            result = {
                'file': str(file_path),
                'account_id': account_id,
                'account_name': account_name,
                'region': region,
                'project': project,
                'deployment_dir': str(file_path.parent),
                'environment': environment
            }
            
            # Cache for future calls
            self._deployment_cache[cache_key] = result
            return result
            
        except (IndexError, ValueError) as e:
            debug_print(f"Error analyzing {file_path}: {e}")
            return None
    
    def _matches_filters(self, deployment: Dict, filters: Optional[Dict]) -> bool:
        """Check if deployment matches filters - inline for speed"""
        if not filters:
            return True
        return all(deployment.get(k) == v for k, v in filters.items())
    
    def execute_deployments(self, deployments: List[Dict], 
                           action: str = "plan") -> Dict:
        """
        Execute terraform deployments - OPTIMIZED sequential processing
        
        Args:
            deployments: List of deployment info dicts
            action: 'plan', 'apply', or 'destroy'
        
        Returns:
            Results dictionary with success/failure info
        """
        if not deployments:
            print("ℹ️ No deployments to process")
            return {
                'successful': [],
                'failed': [],
                'summary': {'total': 0, 'successful': 0, 'failed': 0, 'action': action}
            }
        
        print(f"🚀 Starting {action} for {len(deployments)} deployment(s)")
        
        results = {'successful': [], 'failed': []}
        
        # Sequential processing to avoid terraform.tfvars conflicts
        for i, deployment in enumerate(deployments, 1):
            dep_key = f"{deployment['account_name']}/{deployment['region']}/{deployment['project']}"
            print(f"🔄 [{i}/{len(deployments)}] {dep_key}")
            
            try:
                result = self._process_single_deployment(deployment, action)
                if result['success']:
                    results['successful'].append(result)
                    print(f"✅ {dep_key}: Success")
                else:
                    results['failed'].append(result)
                    print(f"❌ {dep_key}: Failed - {result.get('error', 'Unknown error')}")
                    
            except Exception as e:
                error_result = {
                    'deployment': deployment,
                    'success': False,
                    'error': str(e),
                    'output': f"Exception: {e}"
                }
                results['failed'].append(error_result)
                print(f"💥 {dep_key}: Exception - {e}")
        
        # Generate summary
        results['summary'] = {
            'total': len(deployments),
            'successful': len(results['successful']),
            'failed': len(results['failed']),
            'action': action
        }
        
        print(f"📊 {results['summary']['successful']} successful, {results['summary']['failed']} failed")
        return results
    
    def _process_single_deployment(self, deployment: Dict, action: str) -> Dict:
        """Process a single deployment - OPTIMIZED with minimal I/O"""
        main_dir = self.project_root
        
        try:
            # Clean .terraform directory if exists (faster than full cleanup)
            terraform_dir = main_dir / ".terraform"
            if terraform_dir.exists():
                shutil.rmtree(terraform_dir, ignore_errors=True)
            
            # Copy tfvars file
            tfvars_source = Path(deployment['file'])
            if not tfvars_source.is_absolute():
                tfvars_source = self.working_dir / tfvars_source
            
            tfvars_dest = main_dir / "terraform.tfvars"
            shutil.copy2(tfvars_source, tfvars_dest)
            debug_print(f"Copied tfvars: {tfvars_source.name}")
            
            # Copy referenced policy files (optimized)
            self._copy_policy_files(tfvars_source, main_dir, deployment)
            
            # Terraform init
            init_result = self._run_terraform(['init', '-input=false'], main_dir)
            if init_result['returncode'] != 0:
                return {
                    'deployment': deployment,
                    'success': False,
                    'error': 'Terraform init failed',
                    'output': init_result['output']
                }
            
            # Build command for specified action
            if action == "plan":
                plans_dir = main_dir / "plans"
                plans_dir.mkdir(exist_ok=True)
                
                plan_file = plans_dir / f"{deployment['account_name']}_{deployment['region']}_{deployment['project']}.tfplan"
                cmd = ['plan', '-detailed-exitcode', '-input=false', 
                       '-var-file=terraform.tfvars', '-no-color', '-out', str(plan_file)]
                
            elif action == "apply":
                cmd = ['apply', '-auto-approve', '-input=false', 
                       '-var-file=terraform.tfvars', '-no-color']
                
            elif action == "destroy":
                cmd = ['destroy', '-auto-approve', '-input=false', 
                       '-var-file=terraform.tfvars', '-no-color']
            else:
                raise ValueError(f"Unknown action: {action}")
            
            # Execute terraform command
            result = self._run_terraform(cmd, main_dir)
            
            # Determine success
            # Plan: 0=no changes, 2=changes (both success), 1=error
            # Apply/Destroy: 0=success, >0=error
            is_success = ((action == "plan" and result['returncode'] in {0, 2}) or 
                         (action != "plan" and result['returncode'] == 0))
            
            result_data = {
                'deployment': deployment,
                'success': is_success,
                'error': None if is_success else f"Exit code: {result['returncode']}",
                'output': result['output']
            }
            
            # Add plan-specific data
            if is_success and action == "plan":
                result_data['plan_file'] = str(plan_file)
                result_data['has_changes'] = result['returncode'] == 2
                
                # Generate artifacts (parallel possible, but sequential is cleaner)
                markdown_file = self._save_plan_markdown(deployment, result['output'], 
                                                        result['returncode'] == 2)
                if markdown_file:
                    result_data['markdown_file'] = markdown_file
                
                json_file = self._convert_plan_to_json(plan_file, main_dir)
                if json_file:
                    result_data['json_file'] = json_file
            
            return result_data
            
        except Exception as e:
            return {
                'deployment': deployment,
                'success': False,
                'error': str(e),
                'output': f"Exception: {e}"
            }
    
    def _copy_policy_files(self, tfvars_file: Path, dest_dir: Path, 
                          deployment: Dict) -> None:
        """Copy policy JSON files - OPTIMIZED with regex and smart search"""
        try:
            # Read file once
            content = tfvars_file.read_text()
            
            # Fast regex to find all JSON file references
            json_files = re.findall(r'["\']([Aa]ccounts/[^"\']+\.json)["\']', content)
            
            if not json_files:
                return
            
            debug_print(f"Found {len(json_files)} policy references")
            
            for json_path in json_files:
                filename = Path(json_path).name
                
                # Smart search: try most likely locations first
                candidates = [
                    self.working_dir / json_path,  # Exact path
                    Path(deployment['deployment_dir']) / filename,  # Same dir
                ]
                
                source_file = next((c for c in candidates if c.exists()), None)
                
                if source_file:
                    dest_file = dest_dir / json_path
                    dest_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source_file, dest_file)
                    debug_print(f"Copied policy: {filename}")
                else:
                    print(f"⚠️ Policy file not found: {filename}")
                    
        except Exception as e:
            print(f"⚠️ Error copying policy files: {e}")
    
    def _run_terraform(self, cmd: List[str], cwd: Path) -> Dict:
        """Run terraform command - OPTIMIZED subprocess handling"""
        full_cmd = ['terraform'] + cmd
        debug_print(f"Running: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(
                full_cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=600,  # 10 min timeout
                env=self._terraform_env
            )
            
            output = strip_ansi_colors(result.stdout + result.stderr)
            
            return {
                'returncode': result.returncode,
                'output': output,
                'stdout': result.stdout,
                'stderr': result.stderr
            }
            
        except subprocess.TimeoutExpired:
            return {
                'returncode': 1,
                'output': f"Command timed out after 600s"
            }
        except Exception as e:
            return {
                'returncode': 1,
                'output': f"Command error: {e}"
            }
    
    def _convert_plan_to_json(self, plan_file: Path, main_dir: Path) -> Optional[str]:
        """Convert plan to JSON - OPTIMIZED"""
        try:
            json_dir = self.project_root / "terraform-json"
            json_dir.mkdir(exist_ok=True)
            
            json_file = json_dir / f"{plan_file.stem}.json"
            
            # Also create in working_dir if different
            if self.working_dir != self.project_root:
                working_json_dir = self.working_dir / "terraform-json"
                working_json_dir.mkdir(exist_ok=True)
            
            result = subprocess.run(
                ['terraform', 'show', '-json', str(plan_file)],
                cwd=main_dir,
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if result.returncode == 0 and result.stdout:
                # Validate JSON
                json.loads(result.stdout)
                
                # Write to file
                json_file.write_text(result.stdout)
                
                # Copy to working_dir if different
                if self.working_dir != self.project_root:
                    (self.working_dir / "terraform-json" / json_file.name).write_text(result.stdout)
                
                debug_print(f"Converted plan to JSON: {json_file.name}")
                return str(json_file)
            
            return None
            
        except Exception as e:
            debug_print(f"JSON conversion error: {e}")
            return None
    
    def _save_plan_markdown(self, deployment: Dict, plan_output: str, 
                           has_changes: bool) -> Optional[str]:
        """Save plan as markdown - OPTIMIZED"""
        try:
            markdown_dir = self.project_root / "plan-markdown"
            markdown_dir.mkdir(exist_ok=True)
            
            # Also create in working_dir if different
            if self.working_dir != self.project_root:
                (self.working_dir / "plan-markdown").mkdir(exist_ok=True)
            
            dep_name = f"{deployment['account_name']}-{deployment['region']}-{deployment['project']}"
            markdown_file = markdown_dir / f"{dep_name}-plan.md"
            
            status_emoji = "🔄" if has_changes else "➖"
            status_text = "Changes Detected" if has_changes else "No Changes"
            
            content = f"""### 📋 {dep_name}

**Status:** {status_emoji} {status_text}

<details><summary><strong>🔍 Click to view terraform plan</strong></summary>

```terraform
{plan_output}
```

</details>

---
"""
            
            markdown_file.write_text(content)
            
            # Copy to working_dir if different
            if self.working_dir != self.project_root:
                (self.working_dir / "plan-markdown" / markdown_file.name).write_text(content)
            
            debug_print(f"Saved markdown: {markdown_file.name}")
            return str(markdown_file)
            
        except Exception as e:
            debug_print(f"Markdown error: {e}")
            return None


def main():
    """Main entry point - OPTIMIZED argument parsing"""
    parser = argparse.ArgumentParser(
        description="Terraform Deployment Orchestrator - Universal AWS Resource Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Discover all deployments
  %(prog)s discover --output-summary deployments.json
  
  # Plan specific account
  %(prog)s plan --account my-account --output-summary results.json
  
  # Apply from discovery JSON
  %(prog)s apply --deployments-json deployments.json
        """
    )
    
    parser.add_argument('action', choices=['discover', 'plan', 'apply', 'destroy'],
                       help='Action to perform')
    parser.add_argument("--account", help="Filter by account name")
    parser.add_argument("--region", help="Filter by region")
    parser.add_argument("--environment", help="Filter by environment")
    parser.add_argument("--changed-files", help="Space-separated changed files")
    parser.add_argument("--output-summary", help="JSON output file path")
    parser.add_argument("--deployments-json", help="Load deployments from JSON file")
    parser.add_argument("--dry-run", action="store_true", 
                       help="Show deployments without executing")
    parser.add_argument("--debug", action="store_true", help="Enable debug output")
    
    args = parser.parse_args()
    
    # Set global debug flag
    global DEBUG
    DEBUG = args.debug
    
    try:
        orchestrator = TerraformOrchestrator()
        
        # Build filters
        filters = {k: v for k, v in {
            'account_name': args.account,
            'region': args.region,
            'environment': args.environment
        }.items() if v}
        
        # Get deployments
        if args.deployments_json and Path(args.deployments_json).exists():
            with open(args.deployments_json, 'r') as f:
                data = json.load(f)
            deployments = data.get('deployments', data if isinstance(data, list) else [])
        else:
            changed_files = args.changed_files.split() if args.changed_files else None
            deployments = orchestrator.find_deployments(changed_files, filters)
        
        print(f"🔍 Found {len(deployments)} deployment(s)")
        
        # Initialize results
        results = {}
        
        if args.action == 'discover':
            # Discovery results
            results = {
                'deployments': deployments,
                'total_deployments': len(deployments)
            }
            for dep in deployments:
                dep['deployment_key'] = f"{dep['account_name']}-{dep['region']}-{dep['project']}"
                dep['tfvars_file'] = dep['file']
                print(f"   - {dep['deployment_key']}")
        
        elif args.action in {'plan', 'apply', 'destroy'}:
            if args.dry_run:
                print("🔍 Dry run - no actions performed")
                for dep in deployments:
                    print(f"   Would {args.action}: {dep['account_name']}/{dep['region']}/{dep['project']}")
                return
            
            # Execute deployments
            exec_results = orchestrator.execute_deployments(deployments, args.action)
            
            # Format results
            action_suffix = 's' if args.action != 'apply' else 'ies'
            results = {
                'total_deployments': len(deployments),
                'plans': [],
                'has_changes': False,
                f'successful_{args.action}{action_suffix}': exec_results['summary']['successful'],
                f'failed_{args.action}{action_suffix}': exec_results['summary']['failed']
            }
            
            for result in exec_results['successful']:
                dep = result['deployment']
                plan_entry = {
                    'deployment': f"{dep['account_name']}-{dep['region']}-{dep['project']}",
                    'status': 'success',
                    'has_changes': result.get('has_changes', True)
                }
                
                if 'plan_file' in result:
                    plan_entry['plan_file'] = result['plan_file']
                
                results['plans'].append(plan_entry)
                if result.get('has_changes'):
                    results['has_changes'] = True
            
            for result in exec_results['failed']:
                dep = result['deployment']
                results['plans'].append({
                    'deployment': f"{dep['account_name']}-{dep['region']}-{dep['project']}",
                    'status': 'failed',
                    'has_changes': False,
                    'error': result['error']
                })
        
        # Save results to JSON
        if args.output_summary:
            with open(args.output_summary, 'w') as f:
                json.dump(results, f, indent=2)
            debug_print(f"Results saved to {args.output_summary}")
        
        # Exit with error if any deployments failed
        if args.action in {'plan', 'apply', 'destroy'}:
            failed_key = f'failed_{args.action}{"s" if args.action != "apply" else "ies"}'
            if results.get(failed_key, 0) > 0:
                exit(1)
        
    except Exception as e:
        print(f"💥 Error: {e}")
        if args.debug:
            import traceback
            traceback.print_exc()
        exit(1)


if __name__ == "__main__":
    main()
