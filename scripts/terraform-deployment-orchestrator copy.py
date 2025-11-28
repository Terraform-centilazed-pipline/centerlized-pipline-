#!/usr/bin/env python3
"""
Terraform Deployment Orchestrator - Universal AWS Resource Manager
Enhanced with:
- Dynamic backend key generation based on detected services
- No accounts.yaml dependency - all info extracted from tfvars
- Enhanced PR comments with detailed resource information
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

class TerraformOrchestrator:
    """Terraform Deployment Orchestrator for multi-account, multi-resource deployments"""
    
    def __init__(self, working_dir=None):
        import os
        self.script_dir = Path(__file__).parent
        # Store the working directory (where discover is run from - has Accounts/)
        self.working_dir = Path(working_dir) if working_dir else Path.cwd()
        # Check for TERRAFORM_DIR environment variable (used in centralized workflow)
        terraform_dir_env = os.getenv('TERRAFORM_DIR')
        if terraform_dir_env:
            self.project_root = (self.working_dir / terraform_dir_env).resolve()
            debug_print(f"Using TERRAFORM_DIR from environment: {self.project_root}")
            debug_print(f"Working directory (source files): {self.working_dir}")
        else:
            self.project_root = self.script_dir.parent
            debug_print(f"Using default project root: {self.project_root}")
            debug_print(f"Working directory (source files): {self.working_dir}")
        
        # No need for accounts.yaml - all info is in tfvars files
        # self.accounts_config = self._load_accounts_config()  # REMOVED
        self.templates_dir = self.project_root / "templates"
        
        # Service mapping for dynamic backend key generation
        self.service_mapping = {
            's3_buckets': 's3',
            's3_bucket': 's3',
            'kms_keys': 'kms',
            'kms_key': 'kms',
            'iam_roles': 'iam',
            'iam_role': 'iam',
            'iam_policies': 'iam',
            'iam_policy': 'iam',
            'iam_users': 'iam',
            'lambda_functions': 'lambda',
            'lambda_function': 'lambda',
            'sqs_queues': 'sqs',
            'sqs_queue': 'sqs',
            'sns_topics': 'sns',
            'sns_topic': 'sns',
            'ec2_instances': 'ec2',
            'ec2_instance': 'ec2',
            'vpc_config': 'vpc',
            'vpc': 'vpc',
            'rds_instances': 'rds',
            'rds_instance': 'rds',
            'dynamodb_tables': 'dynamodb',
            'dynamodb_table': 'dynamodb',
            'cloudfront_distributions': 'cloudfront',
            'cloudfront_distribution': 'cloudfront',
            'route53_zones': 'route53',
            'route53_zone': 'route53',
            'elasticache_clusters': 'elasticache',
            'security_groups': 'ec2',
            'load_balancers': 'elb'
        }
        
        # Valid AWS regions for validation
        self.valid_aws_regions = {
            'us-east-1', 'us-east-2', 'us-west-1', 'us-west-2',
            'eu-west-1', 'eu-west-2', 'eu-west-3', 'eu-central-1',
            'eu-north-1', 'ap-southeast-1', 'ap-southeast-2', 
            'ap-northeast-1', 'ap-northeast-2', 'ap-south-1',
            'sa-east-1', 'ca-central-1', 'af-south-1', 'ap-east-1'
        }
        
    def _detect_services_from_tfvars(self, tfvars_file: Path) -> List[str]:
        """Detect services from tfvars file content for dynamic backend key generation"""
        try:
            with open(tfvars_file, 'r') as f:
                content = f.read()
            
            detected_services = []
            for tfvars_key, service in self.service_mapping.items():
                # Look for service definitions in tfvars
                if re.search(rf'\b{tfvars_key}\s*=', content):
                    detected_services.append(service)
                    debug_print(f"Detected service: {service} (from {tfvars_key})")
            
            # Remove duplicates and return
            return list(set(detected_services))
            
        except Exception as e:
            debug_print(f"Error detecting services from {tfvars_file}: {e}")
            return []
    
    def _extract_resource_names_from_tfvars(self, tfvars_file: Path, services: List[str]) -> List[str]:
        """Extract actual resource names from tfvars for more descriptive state file names"""
        try:
            with open(tfvars_file, 'r') as f:
                content = f.read()
            
            resource_names = []
            
            # Extract resource names based on detected services
            for service in services:
                if service == 's3':
                    # Extract S3 bucket names
                    bucket_names = re.findall(r'bucket_name\s*=\s*"([^"]+)"', content)
                    resource_names.extend(bucket_names)
                    
                elif service == 'lambda':
                    # Extract Lambda function names
                    func_names = re.findall(r'function_name\s*=\s*"([^"]+)"', content)
                    resource_names.extend(func_names)
                    
                elif service == 'iam':
                    # Extract IAM role/policy names
                    role_names = re.findall(r'role_name\s*=\s*"([^"]+)"', content)
                    policy_names = re.findall(r'policy_name\s*=\s*"([^"]+)"', content)
                    resource_names.extend(role_names + policy_names)
                    
                elif service == 'sqs':
                    # Extract SQS queue names
                    queue_names = re.findall(r'queue_name\s*=\s*"([^"]+)"', content)
                    resource_names.extend(queue_names)
                    
                elif service == 'sns':
                    # Extract SNS topic names
                    topic_names = re.findall(r'topic_name\s*=\s*"([^"]+)"', content)
                    resource_names.extend(topic_names)
                    
                elif service == 'kms':
                    # Extract KMS key descriptions or aliases
                    key_names = re.findall(r'key_description\s*=\s*"([^"]+)"', content)
                    alias_names = re.findall(r'key_alias\s*=\s*"([^"]+)"', content)
                    resource_names.extend(key_names + alias_names)
                    
                elif service == 'ec2':
                    # Extract EC2 instance names
                    instance_names = re.findall(r'instance_name\s*=\s*"([^"]+)"', content)
                    resource_names.extend(instance_names)
            
            # Clean up names (remove special characters, make filesystem-safe)
            cleaned_names = []
            for name in resource_names:
                # Keep only alphanumeric, hyphens, and underscores
                clean_name = re.sub(r'[^a-zA-Z0-9\-_]', '-', name)
                # Remove multiple consecutive hyphens
                clean_name = re.sub(r'-+', '-', clean_name)
                # Remove leading/trailing hyphens
                clean_name = clean_name.strip('-')
                if clean_name:
                    cleaned_names.append(clean_name)
            
            debug_print(f"Extracted resource names: {cleaned_names}")
            return cleaned_names
            
        except Exception as e:
            debug_print(f"Error extracting resource names from {tfvars_file}: {e}")
            return []
    
    def _generate_dynamic_backend_key(self, account_name: str, region: str, project: str, services: List[str], tfvars_file: Path = None) -> str:
        """Generate dynamic backend key based on detected services and resource names"""
        
        # Determine service part based on detected services
        if len(services) == 0:
            # No services detected, keep original 's3' format
            service_part = "s3"
            state_filename = "terraform.tfstate"
        elif len(services) == 1:
            # Single service - use service name
            service_part = services[0]
            
            # Extract resource names for single service
            resource_names = []
            if tfvars_file:
                resource_names = self._extract_resource_names_from_tfvars(tfvars_file, services)
            
            if resource_names:
                # Use first resource name for state file
                state_filename = f"{resource_names[0]}.tfstate"
            else:
                # Fallback to project name
                state_filename = f"{project}.tfstate"
        else:
            # Multiple services - use project name for organization
            service_part = project
            state_filename = f"{project}-stack.tfstate"
        
        # Generate the backend key with resource-specific state file name
        backend_key = f"{service_part}/{account_name}/{region}/{project}/{state_filename}"
        
        debug_print(f"Generated dynamic backend key: {backend_key}")
        debug_print(f"  Original would be: s3/{account_name}/{region}/{project}/terraform.tfstate")
        debug_print(f"  Services detected: {services} -> service_part: {service_part}")
        debug_print(f"  State filename: {state_filename}")
        
        return backend_key

    # ===== PRE-DEPLOYMENT VALIDATION METHODS =====
    
    def _validate_tfvars_syntax(self, tfvars_file: Path) -> Tuple[bool, List[str]]:
        """Validate HCL syntax in tfvars file"""
        try:
            content = tfvars_file.read_text()
            errors = []
            
            # Basic HCL syntax checks
            if not content.strip():
                errors.append("Tfvars file is empty")
                return False, errors
            
            # Check for basic HCL structure issues
            open_braces = content.count('{')
            close_braces = content.count('}')
            if open_braces != close_braces:
                errors.append(f"Mismatched braces: {open_braces} opening, {close_braces} closing")
            
            open_brackets = content.count('[')
            close_brackets = content.count(']')
            if open_brackets != close_brackets:
                errors.append(f"Mismatched brackets: {open_brackets} opening, {close_brackets} closing")
            
            # Check for unterminated strings
            lines = content.split('\n')
            for i, line in enumerate(lines, 1):
                # Skip comments
                if line.strip().startswith('#') or line.strip().startswith('//'):
                    continue
                
                # Check for odd number of quotes (unterminated strings)
                if line.count('"') % 2 != 0 and '=' in line:
                    errors.append(f"Line {i}: Possible unterminated string")
            
            # Check for required structure (accounts block)
            if 'accounts' not in content:
                errors.append("Missing required 'accounts' configuration block")
            
            return len(errors) == 0, errors
            
        except Exception as e:
            return False, [f"Error reading tfvars file: {str(e)}"]
    
    def _validate_file_structure(self, deployment_dir: Path) -> Tuple[bool, List[str]]:
        """Validate deployment directory structure"""
        errors = []
        
        try:
            if not deployment_dir.exists():
                errors.append(f"Deployment directory does not exist: {deployment_dir}")
                return False, errors
            
            # Check for tfvars files
            tfvars_files = list(deployment_dir.glob("*.tfvars"))
            if not tfvars_files:
                errors.append(f"No .tfvars files found in {deployment_dir}")
            
            # Check file permissions
            for tfvars_file in tfvars_files:
                if not tfvars_file.is_file():
                    errors.append(f"Tfvars path is not a file: {tfvars_file}")
                elif not os.access(tfvars_file, os.R_OK):
                    errors.append(f"Cannot read tfvars file: {tfvars_file}")
            
            return len(errors) == 0, errors
            
        except Exception as e:
            return False, [f"Error validating file structure: {str(e)}"]
    
    def _validate_aws_region(self, region: str) -> Tuple[bool, List[str]]:
        """Validate AWS region"""
        if not region:
            return False, ["Region is empty or None"]
        
        if region not in self.valid_aws_regions:
            return False, [f"Invalid AWS region: {region}. Valid regions: {', '.join(sorted(self.valid_aws_regions))}"]
        
        return True, []
    
    def _validate_account_configuration(self, tfvars_content: str) -> Tuple[bool, List[str]]:
        """Validate account configuration in tfvars"""
        errors = []
        
        try:
            # Check for accounts block
            accounts_match = re.search(r'accounts\s*=\s*{([^}]+)}', tfvars_content, re.DOTALL)
            if not accounts_match:
                errors.append("Missing 'accounts' configuration block")
                return False, errors
            
            accounts_content = accounts_match.group(1)
            
            # Check for account ID (12-digit number)
            account_id_match = re.search(r'"([0-9]{12})"', accounts_content)
            if not account_id_match:
                errors.append("Missing valid 12-digit account ID in accounts block")
            
            # Check for required fields
            required_fields = ['account_name', 'environment', 'regions']
            for field in required_fields:
                if not re.search(rf'{field}\s*=', accounts_content):
                    errors.append(f"Missing required field '{field}' in accounts block")
            
            # Check regions format
            regions_match = re.search(r'regions\s*=\s*\[([^\]]+)\]', accounts_content)
            if regions_match:
                regions_content = regions_match.group(1)
                # Extract region names and validate each
                region_names = re.findall(r'"([^"]+)"', regions_content)
                for region in region_names:
                    if region not in self.valid_aws_regions:
                        errors.append(f"Invalid region '{region}' in regions list")
            
            return len(errors) == 0, errors
            
        except Exception as e:
            return False, [f"Error validating account configuration: {str(e)}"]
    
    def _validate_required_variables(self, tfvars_content: str, services: List[str]) -> Tuple[bool, List[str]]:
        """Check service-specific required variables"""
        errors = []
        warnings = []
        
        # Service-specific validation rules
        service_requirements = {
            's3': ['bucket_name'],
            'lambda': ['function_name', 'runtime'],
            'iam': ['role_name'],
            'sqs': ['queue_name'],
            'sns': ['topic_name']
        }
        
        for service in services:
            if service in service_requirements:
                for required_var in service_requirements[service]:
                    if not re.search(rf'{required_var}\s*=', tfvars_content):
                        errors.append(f"Service '{service}' missing required variable '{required_var}'")
        
        return len(errors) == 0, errors + warnings
    
    def run_pre_deployment_validation(self, deployment: Dict) -> Dict:
        """Comprehensive pre-deployment validation (excluding security - handled by OPA)"""
        
        start_time = time.time()
        validation_results = {
            "deployment": deployment['project'],
            "account": deployment['account_name'],
            "region": deployment['region'],
            "timestamp": datetime.now().isoformat(),
            "validations": {},
            "overall_status": "pending",
            "errors": [],
            "warnings": [],
            "summary": ""
        }
        
        try:
            tfvars_file = Path(deployment['file'])
            deployment_dir = Path(deployment['deployment_dir'])
            
            # 1. File structure validation
            file_valid, file_errors = self._validate_file_structure(deployment_dir)
            validation_results["validations"]["file_structure"] = {
                "status": "passed" if file_valid else "failed",
                "errors": file_errors
            }
            if not file_valid:
                validation_results["errors"].extend(file_errors)
            
            # 2. Tfvars syntax validation
            syntax_valid, syntax_errors = self._validate_tfvars_syntax(tfvars_file)
            validation_results["validations"]["syntax"] = {
                "status": "passed" if syntax_valid else "failed", 
                "errors": syntax_errors
            }
            if not syntax_valid:
                validation_results["errors"].extend(syntax_errors)
            
            # 3. AWS region validation
            region_valid, region_errors = self._validate_aws_region(deployment['region'])
            validation_results["validations"]["aws_region"] = {
                "status": "passed" if region_valid else "failed",
                "errors": region_errors
            }
            if not region_valid:
                validation_results["errors"].extend(region_errors)
            
            # 4. Account configuration validation
            tfvars_content = tfvars_file.read_text()
            account_valid, account_errors = self._validate_account_configuration(tfvars_content)
            validation_results["validations"]["account_config"] = {
                "status": "passed" if account_valid else "failed",
                "errors": account_errors
            }
            if not account_valid:
                validation_results["errors"].extend(account_errors)
            
            # 5. Service-specific variable validation
            services = self._detect_services_from_tfvars(tfvars_file)
            vars_valid, vars_errors = self._validate_required_variables(tfvars_content, services)
            validation_results["validations"]["required_variables"] = {
                "status": "passed" if vars_valid else "failed",
                "errors": vars_errors,
                "services_detected": services
            }
            if not vars_valid:
                validation_results["errors"].extend(vars_errors)
            
            # Determine overall status
            total_errors = len(validation_results["errors"])
            if total_errors == 0:
                validation_results["overall_status"] = "passed"
                validation_results["summary"] = f"✅ All {len(validation_results['validations'])} pre-deployment validations passed"
            else:
                validation_results["overall_status"] = "failed"
                validation_results["summary"] = f"❌ {total_errors} validation error(s) found across {len(validation_results['validations'])} checks"
            
        except Exception as e:
            validation_results["overall_status"] = "error"
            validation_results["errors"].append(f"Validation process failed: {str(e)}")
            validation_results["summary"] = f"❌ Validation process error: {str(e)}"
        
        validation_results["duration_seconds"] = round(time.time() - start_time, 2)
        return validation_results
    
    def generate_validation_report_markdown(self, validation_results: Dict) -> str:
        """Generate a markdown report from validation results"""
        
        report = f"## 🔍 Pre-Deployment Validation Report\n\n"
        report += f"**Deployment**: `{validation_results['deployment']}`  \n"
        report += f"**Account**: `{validation_results['account']}`  \n"
        report += f"**Region**: `{validation_results['region']}`  \n"
        report += f"**Status**: {validation_results['summary']}  \n"
        report += f"**Duration**: {validation_results['duration_seconds']}s  \n"
        report += f"**Timestamp**: {validation_results['timestamp']}\n\n"
        
        # Validation details
        if validation_results['validations']:
            report += "### 📋 Validation Details\n\n"
            report += "| Check | Status | Details |\n"
            report += "|-------|--------|----------|\n"
            
            for check_name, check_result in validation_results['validations'].items():
                status_icon = "✅" if check_result['status'] == 'passed' else "❌"
                status_text = check_result['status'].title()
                
                details = ""
                if check_result.get('errors'):
                    details = "; ".join(check_result['errors'])
                elif check_name == "required_variables" and 'services_detected' in check_result:
                    details = f"Services: {', '.join(check_result['services_detected'])}"
                else:
                    details = "No issues found"
                
                # Truncate details if too long
                if len(details) > 100:
                    details = details[:97] + "..."
                
                report += f"| {check_name.replace('_', ' ').title()} | {status_icon} {status_text} | {details} |\n"
            
            report += "\n"
        
        # Error summary
        if validation_results['errors']:
            report += "### ❌ Issues Found\n\n"
            for i, error in enumerate(validation_results['errors'], 1):
                report += f"{i}. {error}\n"
            report += "\n"
            
            # Add fix suggestions
            report += "### 💡 Suggested Fixes\n\n"
            
            # Analyze errors and provide specific suggestions
            if any("syntax" in error.lower() for error in validation_results['errors']):
                report += "- **Syntax Errors**: Check HCL syntax, ensure balanced braces `{}` and brackets `[]`\n"
                report += "- **String Issues**: Verify all strings are properly quoted with double quotes `\"`\n"
            
            if any("account" in error.lower() for error in validation_results['errors']):
                report += "- **Account Configuration**: Ensure accounts block has valid 12-digit account ID and required fields\n"
            
            if any("region" in error.lower() for error in validation_results['errors']):
                report += "- **Region Issues**: Use valid AWS region names (e.g., us-east-1, eu-west-1)\n"
            
            if any("variable" in error.lower() for error in validation_results['errors']):
                report += "- **Missing Variables**: Add required variables for detected services\n"
            
            report += "\n"
        else:
            report += "### ✅ All Validations Passed\n\n"
            report += "Your configuration looks good! Proceeding to Terraform planning...\n\n"
        
        return report
    
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
        """Analyze tfvars file and extract deployment information from tfvars content"""
        try:
            # Extract all information from the tfvars file content
            account_info = self._extract_account_info_from_tfvars(tfvars_file)
            if not account_info:
                debug_print(f"Could not extract account info from {tfvars_file}")
                return None
            
            # Use tfvars filename as project name
            project = tfvars_file.stem
            
            return {
                'file': str(tfvars_file),
                'account_id': account_info['account_id'],
                'account_name': account_info['account_name'],
                'region': account_info['region'],
                'project': project,
                'deployment_dir': str(tfvars_file.parent),
                'environment': account_info['environment']
            }
                    
        except Exception as e:
            debug_print(f"Error analyzing {tfvars_file}: {e}")
        
        return None
    
    def _extract_account_info_from_tfvars(self, tfvars_file: Path) -> Optional[Dict]:
        """
        Extract account information directly from tfvars file content.
        Looks for accounts block with account_id, account_name, environment, regions
        """
        try:
            content = tfvars_file.read_text()
            
            # Extract from accounts block
            # Pattern: accounts = { "123456789012" = { account_name = "arj-wkld-a-prd", environment = "production", regions = ["us-east-1"] } }
            import re
            
            # Find the accounts block
            accounts_match = re.search(r'accounts\s*=\s*{([^}]+)}', content, re.DOTALL)
            if not accounts_match:
                debug_print(f"No accounts block found in {tfvars_file}")
                return None
            
            accounts_content = accounts_match.group(1)
            
            # Extract account ID (first key in accounts block)
            account_id_match = re.search(r'"([0-9]{12})"', accounts_content)
            if not account_id_match:
                debug_print(f"No account ID found in {tfvars_file}")
                return None
            
            account_id = account_id_match.group(1)
            
            # Extract account_name
            account_name_match = re.search(r'account_name\s*=\s*"([^"]+)"', accounts_content)
            account_name = account_name_match.group(1) if account_name_match else account_id
            
            # Extract environment
            env_match = re.search(r'environment\s*=\s*"([^"]+)"', accounts_content)
            environment = env_match.group(1) if env_match else 'poc'
            
            # Extract region (from regions list or default)
            regions_match = re.search(r'regions\s*=\s*\[([^\]]+)\]', accounts_content)
            if regions_match:
                # Extract first region from list
                region_list = regions_match.group(1)
                first_region_match = re.search(r'"([^"]+)"', region_list)
                region = first_region_match.group(1) if first_region_match else 'us-east-1'
            else:
                region = 'us-east-1'  # Default region
            
            return {
                'account_id': account_id,
                'account_name': account_name,
                'environment': environment,
                'region': region
            }
            
        except Exception as e:
            debug_print(f"Error extracting account info from {tfvars_file}: {e}")
            return None
    
    def _extract_terraform_outputs(self, terraform_output: str, action: str) -> Dict:
        """Extract detailed resource information from terraform output for enhanced PR comments"""
        outputs = {
            'resources_created': [],
            'resources_modified': [],
            'resources_destroyed': [],
            'resource_details': {},
            'error_details': []
        }
        
        try:
            lines = terraform_output.split('\n')
            
            for line in lines:
                line = line.strip()
                
                # Detect terraform plan/apply sections
                if 'will be created' in line:
                    resource_name = self._extract_resource_name_from_line(line)
                    if resource_name:
                        outputs['resources_created'].append(resource_name)
                elif 'will be updated' in line or 'will be modified' in line:
                    resource_name = self._extract_resource_name_from_line(line)
                    if resource_name:
                        outputs['resources_modified'].append(resource_name)
                elif 'will be destroyed' in line:
                    resource_name = self._extract_resource_name_from_line(line)
                    if resource_name:
                        outputs['resources_destroyed'].append(resource_name)
                
                # Extract resource details (ARNs, names, etc.) for apply action
                if action == 'apply':
                    self._extract_resource_details_from_line(line, outputs['resource_details'])
                
                # Extract error information
                if any(error_keyword in line.lower() for error_keyword in ['error', 'failed', 'invalid']):
                    if line not in outputs['error_details'] and len(line) > 10:
                        outputs['error_details'].append(line)
            
            debug_print(f"Extracted terraform outputs: {len(outputs['resources_created'])} created, {len(outputs['resources_modified'])} modified, {len(outputs['resources_destroyed'])} destroyed")
            return outputs
            
        except Exception as e:
            debug_print(f"Error extracting terraform outputs: {e}")
            return outputs
    
    def _extract_resource_name_from_line(self, line: str) -> Optional[str]:
        """Extract resource name from terraform output line"""
        # Pattern: # aws_s3_bucket.example will be created
        match = re.search(r'#\s+(\S+)\s+will be', line)
        if match:
            return match.group(1)
        
        # Alternative pattern for apply output
        match = re.search(r'(\w+\.\w+):', line)
        if match:
            return match.group(1)
            
        return None
    
    def _extract_resource_details_from_line(self, line: str, details: Dict):
        """Extract resource details like ARNs, names from terraform output"""
        try:
            # Extract ARNs
            arn_match = re.search(r'(arn:aws:[^:]+:[^:]*:[^:]*:[^"\s]+)', line)
            if arn_match:
                arn = arn_match.group(1)
                service = arn.split(':')[2] if ':' in arn else 'unknown'
                if service not in details:
                    details[service] = {'arns': [], 'names': [], 'ids': []}
                if arn not in details[service]['arns']:
                    details[service]['arns'].append(arn)
            
            # Extract resource names/IDs with improved patterns
            name_patterns = [
                (r'bucket["\s]*=\s*["\']([^"\']+)["\']', 's3'),
                (r'function_name["\s]*=\s*["\']([^"\']+)["\']', 'lambda'),
                (r'queue_url["\s]*=\s*["\']([^"\']+)["\']', 'sqs'),
                (r'topic_arn["\s]*=\s*["\']([^"\']+)["\']', 'sns'),
                (r'role_name["\s]*=\s*["\']([^"\']+)["\']', 'iam'),
                (r'policy_name["\s]*=\s*["\']([^"\']+)["\']', 'iam'),
                (r'key_id["\s]*=\s*["\']([^"\']+)["\']', 'kms'),
                (r'instance_id["\s]*=\s*["\']([^"\']+)["\']', 'ec2'),
                (r'id\s*=\s*["\']([^"\']+)["\']', 'general')
            ]
            
            for pattern, service in name_patterns:
                match = re.search(pattern, line)
                if match:
                    name = match.group(1)
                    if service not in details:
                        details[service] = {'arns': [], 'names': [], 'ids': []}
                    if name not in details[service]['names']:
                        details[service]['names'].append(name)
                        
        except Exception as e:
            debug_print(f"Error extracting resource details from line: {e}")
    
    def _generate_enhanced_pr_comment(self, deployment: Dict, result: Dict, services: List[str]) -> str:
        """Generate comprehensive PR comment with service details, outputs, and error reporting"""
        deployment_name = f"{deployment['account_name']}-{deployment['project']}"
        backend_key = result.get('backend_key', 'unknown')
        action = result.get('action', 'unknown').title()
        
        if not result['success']:
            # Enhanced error comment
            error_msg = result.get('error', 'Unknown error')
            output = result.get('output', 'No output available')
            
            comment = f"""### ❌ {deployment_name} - {action} Failed

**Services:** {', '.join(services) if services else 'None detected'}  
**Backend Key:** `{backend_key}`
**Error:** {error_msg}

<details><summary><strong>🚨 Error Details</strong></summary>

```
{output[:3000]}
```

</details>

**🔧 Next Steps:**
1. Review the error details above
2. Fix the configuration issues
3. Push changes to a new feature branch
4. The pipeline will automatically re-run

---
"""
            return comment
        
        # Success comment with enhanced details
        outputs = self._extract_terraform_outputs(result.get('output', ''), result.get('action', 'unknown'))
        has_changes = result.get('has_changes', True)
        
        status_emoji = "🔄" if has_changes else "➖"
        status_text = "Changes Applied" if has_changes else "No Changes"
        
        comment = f"""### {status_emoji} {deployment_name} - {action} {status_text}

**Services:** {', '.join(services) if services else 'None detected'}  
**Backend Key:** `{backend_key}`
**Action:** {action}

"""
        
        # Add resource summary
        total_resources = len(outputs['resources_created']) + len(outputs['resources_modified']) + len(outputs['resources_destroyed'])
        
        if total_resources > 0:
            comment += f"**📊 Resource Summary:**\n"
            
            if outputs['resources_created']:
                comment += f"- 📦 **Created:** {len(outputs['resources_created'])} resources\n"
                for resource in outputs['resources_created'][:5]:  # Show first 5
                    comment += f"  - `{resource}`\n"
                if len(outputs['resources_created']) > 5:
                    comment += f"  - ... and {len(outputs['resources_created']) - 5} more\n"
            
            if outputs['resources_modified']:
                comment += f"- 🔧 **Modified:** {len(outputs['resources_modified'])} resources\n"
                for resource in outputs['resources_modified'][:3]:
                    comment += f"  - `{resource}`\n"
                    
            if outputs['resources_destroyed']:
                comment += f"- 🗑️ **Destroyed:** {len(outputs['resources_destroyed'])} resources\n"
                for resource in outputs['resources_destroyed'][:3]:
                    comment += f"  - `{resource}`\n"
            
            comment += "\n"
        
        # Add service-specific details (ARNs, names)
        if outputs['resource_details']:
            comment += "**🎯 Service Details:**\n"
            for service, details in outputs['resource_details'].items():
                service_name = service.upper()
                comment += f"**{service_name}:**\n"
                
                # Show ARNs
                if details.get('arns'):
                    comment += f"  - ARNs:\n"
                    for arn in details['arns'][:3]:  # Limit to 3 ARNs
                        comment += f"    - `{arn}`\n"
                
                # Show resource names
                if details.get('names'):
                    comment += f"  - Names:\n"
                    for name in details['names'][:5]:  # Limit to 5 names
                        comment += f"    - `{name}`\n"
                        
                comment += "\n"
        
        # Add terraform output details in collapsible section
        if result.get('output'):
            comment += f"""<details><summary><strong>🔍 Full Terraform Output</strong></summary>

```terraform
{result['output'][:4000]}
```

</details>

"""
        
        comment += "**✅ Deployment completed successfully!**\n\n---\n"
        
        return comment
    
    def _matches_filters(self, deployment_info: Dict, filters: Optional[Dict]) -> bool:
        """Check if deployment matches provided filters"""
        if not filters:
            return True
            
        for key, value in filters.items():
            if key in deployment_info and deployment_info[key] != value:
                return False
        return True
    
    def execute_deployments(self, deployments: List[Dict], action: str = "plan") -> Dict:
        """Execute terraform deployments using Terraform - sequential processing like KMS"""
        results = {
            'successful': [],
            'failed': [],
            'summary': {}
        }
        
        print(f"🚀 Starting {action} for {len(deployments)} deployments")
        
        # Process deployments sequentially to avoid terraform.tfvars conflicts
        for i, deployment in enumerate(deployments, 1):
            print(f"🔄 [{i}/{len(deployments)}] Processing {deployment['account_name']}/{deployment['region']}/{deployment['project']}")
            
            try:
                result = self._process_deployment(deployment, action)
                
                # Extract services from the deployment and generate enhanced PR comment
                tfvars_source = Path(deployment['file'])
                if not tfvars_source.is_absolute():
                    tfvars_source = self.working_dir / tfvars_source
                detected_services = self._detect_services_from_tfvars(tfvars_source)
                
                # Generate enhanced PR comment with service details
                enhanced_comment = self._generate_enhanced_pr_comment(deployment, result, detected_services)
                result['pr_comment'] = enhanced_comment
                result['detected_services'] = detected_services
                
                if result['success']:
                    results['successful'].append(result)
                    print(f"✅ {deployment['account_name']}/{deployment['region']}: Success")
                else:
                    results['failed'].append(result)
                    print(f"❌ {deployment['account_name']}/{deployment['region']}: Failed")
                    if DEBUG:
                        print(f"🔍 Error details: {result.get('output', 'No output')[:500]}")
                        
            except Exception as e:
                # Generate basic error result with backend key
                try:
                    tfvars_source = Path(deployment['file'])
                    if not tfvars_source.is_absolute():
                        tfvars_source = self.working_dir / tfvars_source
                    detected_services = self._detect_services_from_tfvars(tfvars_source)
                except:
                    detected_services = []
                    
                error_result = {
                    'deployment': deployment,
                    'success': False,
                    'error': str(e),
                    'output': f"Exception during processing: {e}",
                    'backend_key': f"s3/{deployment['account_name']}/{deployment['region']}/{deployment['project']}/terraform.tfstate",
                    'action': action,
                    'terraform_outputs': {
                        'resources_created': [],
                        'resources_modified': [],
                        'resources_destroyed': [],
                        'resource_details': {}
                    },
                    'detected_services': detected_services
                }
                
                # Generate enhanced PR comment for the error
                enhanced_comment = self._generate_enhanced_pr_comment(deployment, error_result, detected_services)
                error_result['pr_comment'] = enhanced_comment
                
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
        
        # Print enhanced PR comments for debugging
        if DEBUG:
            print("\n🔗 Enhanced PR Comments Generated:")
            for result in results['successful'] + results['failed']:
                if result.get('pr_comment'):
                    deployment_name = f"{result['deployment']['account_name']}-{result['deployment']['project']}"
                    print(f"\n📝 {deployment_name}:")
                    print(result['pr_comment'][:500] + "..." if len(result['pr_comment']) > 500 else result['pr_comment'])
        
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
            
            # Account info is now extracted in _analyze_deployment_file
            # Use the account_name from deployment (which is already extracted from tfvars)
            real_account_name = deployment['account_name']
            debug_print(f"Using account name: {real_account_name}")
            
            # Detect services from tfvars and generate dynamic backend key
            detected_services = self._detect_services_from_tfvars(tfvars_source)
            state_key = self._generate_dynamic_backend_key(
                real_account_name, 
                deployment['region'], 
                deployment['project'], 
                detected_services,
                tfvars_source
            )
            debug_print(f"Dynamic state key: {state_key}")
            debug_print(f"Detected services: {detected_services}")
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
            
            # Extract terraform outputs for enhanced PR comments
            terraform_outputs = self._extract_terraform_outputs(result['output'], action)
            
            # Prepare result with plan file info if applicable
            result_data = {
                'deployment': deployment,
                'success': is_successful,
                'error': None if is_successful else error_details,
                'output': result['output'],
                'backend_key': state_key,
                'action': action,
                'terraform_outputs': terraform_outputs
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
            # Generate backend key even for failed deployments
            try:
                tfvars_source = Path(deployment['file'])
                if not tfvars_source.is_absolute():
                    tfvars_source = self.working_dir / tfvars_source
                # Account name is already extracted in _analyze_deployment_file
                real_account_name = deployment['account_name']
                detected_services = self._detect_services_from_tfvars(tfvars_source)
                state_key = self._generate_dynamic_backend_key(
                    real_account_name, 
                    deployment['region'], 
                    deployment['project'], 
                    detected_services,
                    tfvars_source
                )
            except:
                # Fallback to simple backend key if something goes wrong
                state_key = f"s3/{deployment['account_name']}/{deployment['region']}/{deployment['project']}/terraform.tfstate"
                detected_services = []
                
            return {
                'deployment': deployment,
                'success': False,
                'error': str(e),
                'output': f"Exception during {action}: {e}",
                'backend_key': state_key,
                'action': action,
                'terraform_outputs': {
                    'resources_created': [],
                    'resources_modified': [],
                    'resources_destroyed': [],
                    'resource_details': {}
                }
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
                debug_print(f"  Deployment dir: {deployment.get('deployment_dir', 'NOT SET')}")
                
                # Simple approach: Look in the deployment directory only
                # This matches our structure: Accounts/project/project.json
                deployment_dir = Path(deployment['deployment_dir'])
                if not deployment_dir.is_absolute():
                    deployment_dir = self.working_dir / deployment_dir
                
                source_file = deployment_dir / filename
                debug_print(f"  Looking for: {source_file}")
                
                if source_file.exists():
                    debug_print(f"✅ Found policy file in deployment dir: {source_file}")
                else:
                    debug_print(f"❌ Policy file not found: {source_file}")
                    continue
                
                # Destination preserves the tfvars path (what terraform expects)
                dest_file = dest_dir / json_file_path
                
                # Create destination directory if needed
                dest_file.parent.mkdir(parents=True, exist_ok=True)
                
                # Copy the policy file
                shutil.copy2(source_file, dest_file)
                print(f"✅ Copied policy file: {filename}")
                debug_print(f"   From: {source_file}")
                debug_print(f"   To:   {dest_file}")
                    
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
    parser.add_argument('action', choices=['discover', 'validate', 'plan', 'apply', 'destroy'], help='Action to perform')
    parser.add_argument("--account", help="Filter by account name")
    parser.add_argument("--region", help="Filter by region")
    parser.add_argument("--environment", help="Filter by environment")
    parser.add_argument("--changed-files", help="Space-separated changed files")
    parser.add_argument("--output-summary", help="JSON output file")
    parser.add_argument("--deployments-json", help="Load deployments from JSON")
    parser.add_argument("--state-bucket", help="S3 bucket for Terraform state")
    parser.add_argument("--working-dir", help="Working directory for deployment discovery")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be deployed without executing")
    parser.add_argument("--debug", action="store_true", help="Enable debug output")
    
    args = parser.parse_args()
    
    global DEBUG
    DEBUG = args.debug
    
    debug_print(f"Arguments: {vars(args)}")
    
    try:
        orchestrator = TerraformOrchestrator(working_dir=args.working_dir)
        
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
            deployments = orchestrator.find_deployments(changed_files, filters)
        
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
        
        elif args.action == 'validate':
            print(f"🔍 Running pre-deployment validation on {len(deployments)} deployments...")
            
            validation_results = []
            all_passed = True
            
            for deployment in deployments:
                print(f"\n📋 Validating: {deployment['project']} ({deployment['account_name']}/{deployment['region']})")
                
                # Run validation
                result = orchestrator.run_pre_deployment_validation(deployment)
                validation_results.append(result)
                
                # Display result summary
                if result['overall_status'] == 'passed':
                    print(f"   ✅ {result['summary']}")
                else:
                    print(f"   ❌ {result['summary']}")
                    all_passed = False
                    
                    # Show errors
                    if result['errors']:
                        print(f"   📋 Errors:")
                        for error in result['errors'][:3]:  # Show first 3 errors
                            print(f"      - {error}")
                        if len(result['errors']) > 3:
                            print(f"      - ... and {len(result['errors']) - 3} more")
            
            # Generate validation report
            if len(deployments) == 1:
                # Single deployment - generate detailed markdown report
                markdown_report = orchestrator.generate_validation_report_markdown(validation_results[0])
                
                # Save to validation-report.md
                report_file = Path("validation-report.md")
                report_file.write_text(markdown_report)
                print(f"\n📄 Detailed validation report saved to: {report_file}")
                
            # Summary
            passed_count = sum(1 for r in validation_results if r['overall_status'] == 'passed')
            failed_count = len(validation_results) - passed_count
            
            results = {
                'validation_results': validation_results,
                'total_deployments': len(deployments),
                'validations_passed': passed_count,
                'validations_failed': failed_count,
                'overall_status': 'passed' if all_passed else 'failed',
                'summary': f"{passed_count}/{len(deployments)} validations passed"
            }
            
            print(f"\n📊 Validation Summary: {results['summary']}")
            
            if not all_passed:
                print("❌ Some validations failed - fix issues before proceeding to terraform operations")
        
        elif args.action in ['plan', 'apply', 'destroy']:
            if args.dry_run:
                print("🔍 Dry run - no actions will be performed")
                return
                
            # Execute deployments
            deployment_results = orchestrator.execute_deployments(deployments, args.action)
            
            # Display enhanced PR comments
            orchestrator.print_pr_comments(deployment_results)
            
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

    def get_pr_comments(self, deployment_results: Dict) -> List[Dict]:
        """Extract enhanced PR comments from deployment results"""
        pr_comments = []
        
        for result in deployment_results['successful'] + deployment_results['failed']:
            if result.get('pr_comment'):
                deployment_info = result['deployment']
                pr_comments.append({
                    'deployment': f"{deployment_info['account_name']}-{deployment_info['project']}",
                    'account_name': deployment_info['account_name'],
                    'region': deployment_info['region'],
                    'project': deployment_info['project'],
                    'success': result['success'],
                    'action': result.get('action', 'unknown'),
                    'backend_key': result.get('backend_key', 'unknown'),
                    'detected_services': result.get('detected_services', []),
                    'comment': result['pr_comment']
                })
        
        return pr_comments
    
    def print_pr_comments(self, deployment_results: Dict):
        """Print all enhanced PR comments for easy viewing"""
        pr_comments = self.get_pr_comments(deployment_results)
        
        print("\n" + "="*80)
        print("📝 ENHANCED PR COMMENTS GENERATED")
        print("="*80)
        
        for comment_data in pr_comments:
            print(f"\n📌 {comment_data['deployment']} ({comment_data['action']})")
            print(f"   🎯 Services: {', '.join(comment_data['detected_services']) if comment_data['detected_services'] else 'None detected'}")
            print(f"   🔑 Backend: {comment_data['backend_key']}")
            print("-" * 80)
            print(comment_data['comment'])
            print("-" * 80)


if __name__ == "__main__":
    main()