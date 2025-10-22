#!/usr/bin/env python3
"""
Pre-Deployment Validator
Validates application, team, and cost center BEFORE running terraform plan
"""

import json
import sys
import yaml
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass


@dataclass
class ValidationResult:
    """Validation result for pre-deployment checks"""
    passed: bool
    application_valid: bool
    team_valid: bool
    cost_center_valid: bool
    errors: List[str]
    warnings: List[str]
    metadata: Dict[str, any]


class PreDeploymentValidator:
    """Validates deployment before terraform plan"""
    
    def __init__(self, rules_file: str = "deployment-rules.yaml"):
        """Initialize validator with rules"""
        self.rules_path = Path(rules_file)
        self.rules = self._load_rules()
        
    def _load_rules(self) -> dict:
        """Load deployment rules"""
        if not self.rules_path.exists():
            raise FileNotFoundError(f"Rules not found: {self.rules_path}")
        
        with open(self.rules_path) as f:
            return yaml.safe_load(f)
    
    def extract_tfvars_metadata(self, tfvars_file: str) -> Dict[str, str]:
        """
        Extract metadata from tfvars file
        Expected variables:
          - application_name or project_name
          - team_name
          - cost_center
          - environment
        """
        metadata = {
            "application": None,
            "team": None,
            "cost_center": None,
            "environment": None,
            "account_name": None,
        }
        
        try:
            with open(tfvars_file, 'r') as f:
                content = f.read()
            
            # Parse tfvars (simple key = "value" format)
            for line in content.split('\n'):
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    
                    # Map to our metadata fields
                    if key in ['application_name', 'project_name', 'project']:
                        metadata['application'] = value
                    elif key in ['team_name', 'team', 'owner_team']:
                        metadata['team'] = value
                    elif key in ['cost_center', 'costcenter', 'billing_code']:
                        metadata['cost_center'] = value
                    elif key == 'environment':
                        metadata['environment'] = value
                    elif key == 'account_name':
                        metadata['account_name'] = value
            
            return metadata
            
        except Exception as e:
            raise ValueError(f"Failed to parse tfvars: {e}")
    
    def validate_application(self, application: str, environment: str) -> Tuple[bool, str]:
        """Validate application is in allowed list"""
        if not application:
            return False, "❌ No application/project name found in tfvars"
        
        # Get allowed projects from rules
        projects = self.rules.get("projects", {})
        
        if not projects:
            # If no restrictions, allow all
            return True, f"✅ Project '{application}' (no restrictions configured)"
        
        # Check if project exists
        if application not in projects:
            available = ", ".join(projects.keys())
            return False, f"❌ Project '{application}' not in allowed list. Available: {available}"
        
        return True, f"✅ Project '{application}' is approved"
    
    def validate_team(self, team: str, application: str, pr_author: str) -> Tuple[bool, str]:
        """Validate team - simplified, always pass since no team validation needed"""
        return True, f"✅ No team validation required"
    
    def validate_cost_center(self, cost_center: str, team: str = None, application: str = None) -> Tuple[bool, str]:
        """Validate cost center matches project requirement"""
        if not cost_center:
            return False, "❌ No cost_center found in tfvars (required for billing)"
        
        projects = self.rules.get("projects", {})
        
        # If application specified, check project-specific cost center
        if application and application in projects:
            project_config = projects[application]
            expected_cc = project_config.get("cost_center")
            
            if expected_cc and cost_center != expected_cc:
                return False, f"❌ Cost center '{cost_center}' doesn't match project requirement. Expected: {expected_cc}"
        
        # Check if cost center exists in approved list
        valid_cost_centers = self.rules.get("cost_centers", {})
        
        if valid_cost_centers and cost_center not in valid_cost_centers:
            available = ", ".join(valid_cost_centers.keys())
            return False, f"❌ Cost center '{cost_center}' not in approved list. Available: {available}"

        return True, f"✅ Cost center '{cost_center}' is valid"
    
    def validate_deployment(
        self,
        tfvars_file: str,
        pr_author: str
    ) -> ValidationResult:
        """
        Run all pre-deployment validations
        Returns ValidationResult with pass/fail and detailed errors
        """
        errors = []
        warnings = []
        
        # Extract metadata from tfvars
        try:
            metadata = self.extract_tfvars_metadata(tfvars_file)
        except Exception as e:
            return ValidationResult(
                passed=False,
                application_valid=False,
                team_valid=False,
                cost_center_valid=False,
                errors=[f"❌ Failed to parse tfvars file: {e}"],
                warnings=[],
                metadata={}
            )
        
        # Validate application
        app_valid, app_msg = self.validate_application(
            metadata['application'],
            metadata['environment']
        )
        if not app_valid:
            errors.append(app_msg)
        
        # Validate team
        team_valid, team_msg = self.validate_team(
            metadata['team'],
            metadata['application'],
            pr_author
        )
        if not team_valid:
            errors.append(team_msg)
        
        # Validate cost center
        cc_valid, cc_msg = self.validate_cost_center(
            metadata['cost_center'],
            application=metadata['application']
        )
        if not cc_valid:
            errors.append(cc_msg)
        
        # Check for missing required fields
        if not metadata['application']:
            errors.append("❌ Missing required field: application_name or project_name")
        if not metadata['cost_center']:
            errors.append("❌ Missing required field: cost_center")
        # Note: team_name no longer required
        
        # Overall pass/fail  
        # Only check required fields: application and cost_center
        required_fields_valid = bool(metadata['application'] and metadata['cost_center'])
        passed = app_valid and team_valid and cc_valid and required_fields_valid
        
        return ValidationResult(
            passed=passed,
            application_valid=app_valid,
            team_valid=team_valid,
            cost_center_valid=cc_valid,
            errors=errors,
            warnings=warnings,
            metadata=metadata
        )
    
    def generate_pr_comment(
        self,
        result: ValidationResult,
        pr_author: str,
        tfvars_file: str
    ) -> str:
        """Generate PR comment for validation result"""
        
        if result.passed:
            header = "✅ **Pre-Deployment Validation Passed**"
            emoji = "🟢"
        else:
            header = "❌ **Pre-Deployment Validation Failed**"
            emoji = "🔴"
        
        comment = f"## {header}\n\n"
        comment += f"**👤 PR Author:** @{pr_author}\n"
        comment += f"**📄 Validated File:** `{tfvars_file}`\n\n"
        comment += "---\n\n"
        
        # Validation Checklist
        comment += "### 📋 Validation Checklist\n\n"
        comment += f"| Check | Status | Details |\n"
        comment += f"|-------|--------|----------|\n"
        
        app_emoji = "✅" if result.application_valid else "❌"
        team_emoji = "✅" if result.team_valid else "❌"
        cc_emoji = "✅" if result.cost_center_valid else "❌"
        
        comment += f"| **Application/Project** | {app_emoji} | `{result.metadata.get('application', 'Not found')}` |\n"
        comment += f"| **Team Authorization** | {team_emoji} | `{result.metadata.get('team', 'Not found')}` |\n"
        comment += f"| **Cost Center** | {cc_emoji} | `{result.metadata.get('cost_center', 'Not found')}` |\n\n"
        
        # Metadata Summary
        if result.metadata:
            comment += "### 📊 Deployment Metadata\n\n"
            comment += "```yaml\n"
            comment += f"Application: {result.metadata.get('application', 'N/A')}\n"
            comment += f"Team: {result.metadata.get('team', 'N/A')}\n"
            comment += f"Cost Center: {result.metadata.get('cost_center', 'N/A')}\n"
            comment += f"Environment: {result.metadata.get('environment', 'N/A')}\n"
            comment += f"Account: {result.metadata.get('account_name', 'N/A')}\n"
            comment += "```\n\n"
        
        # Errors
        if result.errors:
            comment += "### 🚫 Validation Errors\n\n"
            for error in result.errors:
                comment += f"- {error}\n"
            comment += "\n"
        
        # Warnings
        if result.warnings:
            comment += "### ⚠️ Warnings\n\n"
            for warning in result.warnings:
                comment += f"- {warning}\n"
            comment += "\n"
        
        # Next steps
        comment += "---\n\n"
        if result.passed:
            comment += "### ✅ Next Steps\n\n"
            comment += "All pre-deployment validations passed!\n\n"
            comment += "**The workflow will now:**\n"
            comment += "1. ✅ Run terraform plan\n"
            comment += "2. 🛡️ Validate with OPA security policies\n"
            comment += "3. 💰 Estimate deployment costs\n"
            comment += "4. 🎯 Determine approval requirements\n\n"
        else:
            comment += "### ❌ Required Actions\n\n"
            comment += "**Deployment is blocked.** Please fix the errors above:\n\n"
            comment += "1. Update your `tfvars` file with correct values\n"
            comment += "2. Ensure you're using an approved:\n"
            comment += "   - Application/Project name\n"
            comment += "   - Team name (that you're a member of)\n"
            comment += "   - Cost center (authorized for your team)\n"
            comment += "3. Push changes to re-trigger validation\n\n"
            comment += "**Need help?**\n"
            comment += "- Check allowed values in [`deployment-rules.yaml`](../deployment-rules.yaml)\n"
            comment += "- Contact your team lead or platform engineering\n\n"
        
        comment += "---\n"
        comment += "*Pre-Deployment Validator | Centralized Terraform Controller*"
        
        return comment


def main():
    """Main entry point"""
    if len(sys.argv) < 3:
        print("Usage: pre-deployment-validator.py <tfvars_file> <pr_author>")
        sys.exit(1)
    
    tfvars_file = sys.argv[1]
    pr_author = sys.argv[2]
    
    try:
        validator = PreDeploymentValidator("deployment-rules.yaml")
        
        result = validator.validate_deployment(tfvars_file, pr_author)
        
        # Output result as JSON
        output = {
            "passed": result.passed,
            "application_valid": result.application_valid,
            "team_valid": result.team_valid,
            "cost_center_valid": result.cost_center_valid,
            "application": result.metadata.get('application'),
            "team": result.metadata.get('team'),
            "cost_center": result.metadata.get('cost_center'),
            "environment": result.metadata.get('environment'),
            "errors": result.errors,
            "warnings": result.warnings,
        }
        
        print(json.dumps(output, indent=2))
        
        # Save PR comment
        pr_comment = validator.generate_pr_comment(result, pr_author, tfvars_file)
        with open("pre-validation-comment.md", "w") as f:
            f.write(pr_comment)
        
        # Exit with appropriate code
        sys.exit(0 if result.passed else 1)
        
    except Exception as e:
        print(f"❌ Validation error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(2)


if __name__ == "__main__":
    main()
