#!/usr/bin/env python3
"""
Terrateam-Style Deployment Manager
Handles cost estimation, approval thresholds, and team-based access control
"""

import json
import sys
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum


class ApprovalTier(Enum):
    """Approval tiers based on cost and impact"""
    AUTO_APPROVE = "auto_approve"
    TIER1 = "tier1_approval"
    TIER2 = "tier2_approval"
    TIER3 = "tier3_approval"


@dataclass
class CostEstimate:
    """Cost estimation results"""
    monthly_cost: float
    hourly_cost: float
    cost_diff: float
    cost_diff_percent: float
    breakdown_by_service: Dict[str, float]


@dataclass
class ResourceChanges:
    """Resource change counts from terraform plan"""
    to_create: int
    to_change: int
    to_destroy: int
    total: int


@dataclass
class DeploymentDecision:
    """Final deployment decision"""
    approved: bool
    approval_tier: ApprovalTier
    required_approvals: int
    reason: str
    cost_estimate: Optional[CostEstimate]
    resource_changes: ResourceChanges
    team_authorized: bool
    security_passed: bool


class TerrateamStyleManager:
    """Manages Terrateam-style deployment controls"""
    
    def __init__(self, rules_file: str = "deployment-rules.yaml"):
        """Initialize with deployment rules"""
        self.rules_path = Path(rules_file)
        self.rules = self._load_rules()
        
    def _load_rules(self) -> dict:
        """Load deployment rules configuration"""
        if not self.rules_path.exists():
            raise FileNotFoundError(f"Deployment rules not found: {self.rules_path}")
        
        with open(self.rules_path) as f:
            return yaml.safe_load(f)
    
    def check_team_authorization(
        self,
        pr_author: str,
        account: str,
        environment: str,
        service: str
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Check if PR author is authorized to deploy to this account/environment/service
        
        Returns:
            (authorized, team_name, reason)
        """
        teams = self.rules.get("teams", {})
        
        for team_name, team_config in teams.items():
            members = team_config.get("members", [])
            
            # Check if user is in this team
            if pr_author not in members:
                continue
            
            permissions = team_config.get("permissions", {})
            
            # Check if team has full access
            if isinstance(permissions, list):
                if "all_accounts" in permissions:
                    return True, team_name, f"Member of {team_config['name']} with full access"
            
            # Check specific permissions
            allowed_accounts = permissions.get("allowed_accounts", [])
            allowed_environments = permissions.get("allowed_environments", [])
            allowed_services = permissions.get("allowed_services", [])
            
            # Validate account access
            if allowed_accounts and account not in allowed_accounts:
                continue
            
            # Validate environment access
            if allowed_environments and environment not in allowed_environments:
                continue
            
            # Validate service access
            if allowed_services and service not in allowed_services and "all" not in allowed_services:
                continue
            
            return True, team_name, f"Authorized via {team_config['name']}"
        
        return False, None, f"User {pr_author} not authorized for {account}/{environment}/{service}"
    
    def estimate_costs_from_plan(self, plan_json_path: str) -> CostEstimate:
        """
        Cost estimation placeholder - will be implemented via MCP server later
        
        TODO: Implement with Infracost MCP server for accurate cost analysis
        """
        # Return zero costs for now - MCP server will handle this later
        return CostEstimate(
            monthly_cost=0.0,
            hourly_cost=0.0,
            cost_diff=0.0,
            cost_diff_percent=0.0,
            breakdown_by_service={}
        )
    
    def parse_resource_changes(self, plan_json_path: str) -> ResourceChanges:
        """Parse resource change counts from plan"""
        with open(plan_json_path) as f:
            plan = json.load(f)
        
        to_create = 0
        to_change = 0
        to_destroy = 0
        
        for change in plan.get("resource_changes", []):
            actions = change.get("change", {}).get("actions", [])
            
            if "create" in actions:
                to_create += 1
            elif "delete" in actions:
                to_destroy += 1
            elif "update" in actions or "replace" in actions:
                to_change += 1
        
        return ResourceChanges(
            to_create=to_create,
            to_change=to_change,
            to_destroy=to_destroy,
            total=to_create + to_change + to_destroy
        )
    
    def determine_approval_tier(
        self,
        cost_estimate: CostEstimate,
        resource_changes: ResourceChanges,
        environment: str
    ) -> Tuple[ApprovalTier, int]:
        """
        Determine approval tier based on resource changes and environment
        Cost-based approval will be added later via MCP server
        
        Returns:
            (tier, required_approvals)
        """
        resource_thresholds = self.rules.get("resource_thresholds", {})
        env_config = self.rules.get("environments", {}).get(environment, {})
        
        # Production always requires approval
        if environment == "production" and not env_config.get("auto_approve_enabled", False):
            return ApprovalTier.TIER2, env_config.get("min_required_approvals", 2)
        
        # Check resource-based tiers (cost checking removed - will be added via MCP later)
        
        # Auto-approve tier - based on resource count only
        auto_threshold = resource_thresholds.get("auto_approve", {})
        if (resource_changes.to_create <= auto_threshold.get("max_resources_created", 5) and
            resource_changes.to_destroy <= auto_threshold.get("max_resources_destroyed", 3)):
            return ApprovalTier.AUTO_APPROVE, 0
        
        # Tier 1 - moderate resource changes
        tier1_threshold = resource_thresholds.get("tier1_approval", {})
        if resource_changes.to_create <= tier1_threshold.get("max_resources_created", 20):
            return ApprovalTier.TIER1, tier1_threshold.get("required_approvals", 1)
        
        # Tier 2 - high resource changes
        tier2_threshold = self.rules.get("cost_thresholds", {}).get("tier2_approval", {})
        return ApprovalTier.TIER2, tier2_threshold.get("required_approvals", 2)
    
    def detect_services_from_tfvars(self, tfvars_path: str) -> List[str]:
        """
        Detect services from variable names in tfvars file
        """
        service_map = {
            's3_buckets': 's3',
            'kms_keys': 'kms',
            'rds_instances': 'rds',
            'lambda_functions': 'lambda',
            'vpc_config': 'vpc',
            'iam_roles': 'iam',
            'ec2_instances': 'ec2',
            'dynamodb_tables': 'dynamodb',
            'efs_file_systems': 'efs',
            'cloudwatch_alarms': 'cloudwatch',
            'sns_topics': 'sns',
            'sqs_queues': 'sqs'
        }
        
        detected_services = []
        
        try:
            with open(tfvars_path, 'r') as f:
                content = f.read()
                
                for variable, service in service_map.items():
                    if f'{variable} =' in content:
                        detected_services.append(service)
                        
        except FileNotFoundError:
            print(f"Warning: tfvars file not found: {tfvars_path}")
            
        return detected_services
    
    def extract_project_from_path(self, tfvars_path: str) -> str:
        """
        Extract project name from tfvars file path
        Example: Accounts/test-4-poc-1/test-4-poc-1.tfvars -> test-4-poc-1
        """
        path = Path(tfvars_path)
        
        # Try to get project from directory name
        if len(path.parts) >= 2:
            project = path.parts[-2]  # Directory containing the tfvars file
        else:
            # Fall back to filename without extension
            project = path.stem
            
        return project
    
    def get_account_short_name(self, account_id: str) -> str:
        """
        Convert account name to short name for backend paths
        arj-wkld-a-prd -> a-prd
        arj-wkld-a-nonprd -> a-nonprd
        """
        # Load accounts config
        accounts_config_path = Path(__file__).parent.parent / "accounts.yaml"
        
        try:
            with open(accounts_config_path) as f:
                accounts_config = yaml.safe_load(f)
                
            account_name = accounts_config.get("accounts", {}).get(account_id, {}).get("account_name", "")
            
            # Convert arj-wkld-a-prd to a-prd
            if account_name.startswith("arj-wkld-"):
                return account_name.replace("arj-wkld-", "")
            else:
                return account_name
                
        except Exception as e:
            print(f"Warning: Could not resolve account short name for {account_id}: {e}")
            return account_id
    
    def generate_backend_key(self, tfvars_path: str, account_id: str) -> str:
        """
        Generate dynamic backend key based on services detected in tfvars
        
        Single service: terraform/{account_short}/{project}/{service}/terraform.tfstate
        Multi service:  terraform/{account_short}/{project}/combined/terraform.tfstate
        """
        services = self.detect_services_from_tfvars(tfvars_path)
        project = self.extract_project_from_path(tfvars_path)
        account_short = self.get_account_short_name(account_id)
        
        if len(services) == 0:
            # No services detected, use generic path
            backend_key = f"terraform/{account_short}/{project}/generic/terraform.tfstate"
        elif len(services) == 1:
            # Single service deployment
            service = services[0]
            backend_key = f"terraform/{account_short}/{project}/{service}/terraform.tfstate"
        else:
            # Multi-service deployment - use combined state
            backend_key = f"terraform/{account_short}/{project}/combined/terraform.tfstate"
        
        return backend_key
    
    def generate_backend_config(self, tfvars_path: str, account_id: str, region: str = "us-east-1") -> Dict[str, str]:
        """
        Generate complete backend configuration for terraform
        """
        backend_key = self.generate_backend_key(tfvars_path, account_id)
        
        # Assume S3 backend configuration
        backend_config = {
            "backend": "s3",
            "bucket": f"terraform-state-{account_id}-{region}",
            "key": backend_key,
            "region": region,
            "encrypt": "true",
            "dynamodb_table": f"terraform-locks-{account_id}",
            "workspace_key_prefix": "workspaces"
        }
        
        return backend_config

    def make_deployment_decision(
        self,
        pr_author: str,
        account: str,
        environment: str,
        service: str,
        plan_json_path: str,
        opa_passed: bool,
        critical_violations: int
    ) -> DeploymentDecision:
        """
        Make final deployment decision based on all factors
        """
        # Check team authorization
        team_authorized, team_name, auth_reason = self.check_team_authorization(
            pr_author, account, environment, service
        )
        
        # Parse plan changes
        resource_changes = self.parse_resource_changes(plan_json_path)
        
        # Estimate costs
        try:
            cost_estimate = self.estimate_costs_from_plan(plan_json_path)
        except Exception as e:
            print(f"⚠️ Cost estimation failed: {e}", file=sys.stderr)
            cost_estimate = CostEstimate(0.0, 0.0, 0.0, 0.0, {})
        
        # Determine approval tier
        approval_tier, required_approvals = self.determine_approval_tier(
            cost_estimate, resource_changes, environment
        )
        
        # Check security
        security_passed = opa_passed and critical_violations == 0
        
        # Make decision
        if not team_authorized:
            return DeploymentDecision(
                approved=False,
                approval_tier=approval_tier,
                required_approvals=required_approvals,
                reason=f"❌ {auth_reason}",
                cost_estimate=cost_estimate,
                resource_changes=resource_changes,
                team_authorized=False,
                security_passed=security_passed
            )
        
        if not security_passed:
            return DeploymentDecision(
                approved=False,
                approval_tier=approval_tier,
                required_approvals=required_approvals,
                reason=f"❌ Security validation failed: {critical_violations} critical violations",
                cost_estimate=cost_estimate,
                resource_changes=resource_changes,
                team_authorized=True,
                security_passed=False
            )
        
        # Auto-approve if tier allows
        if approval_tier == ApprovalTier.AUTO_APPROVE:
            return DeploymentDecision(
                approved=True,
                approval_tier=approval_tier,
                required_approvals=0,
                reason=f"✅ Auto-approved: Low resource impact ({resource_changes.total} resources)",
                cost_estimate=cost_estimate,
                resource_changes=resource_changes,
                team_authorized=True,
                security_passed=True
            )
        
        # Requires approval
        return DeploymentDecision(
            approved=False,
            approval_tier=approval_tier,
            required_approvals=required_approvals,
            reason=f"⏳ Approval required: {required_approvals} approver(s) needed ({resource_changes.total} resources)",
            cost_estimate=cost_estimate,
            resource_changes=resource_changes,
            team_authorized=True,
            security_passed=True
        )
    
    def generate_pr_comment(self, decision: DeploymentDecision, pr_author: str, team_name: str = None) -> str:
        """Generate Terrateam-style PR comment"""
        
        # Header
        if decision.approved:
            header = "✅ **Deployment Approved - Auto-Merge Enabled**"
            status_emoji = "🟢"
        elif not decision.team_authorized:
            header = "❌ **Deployment Blocked - Unauthorized**"
            status_emoji = "🔴"
        elif not decision.security_passed:
            header = "❌ **Deployment Blocked - Security Violations**"
            status_emoji = "🔴"
        else:
            header = "⏳ **Approval Required**"
            status_emoji = "🟡"
        
        comment = f"## {header}\n\n"
        
        # Author and team info
        comment += f"**👤 Author:** @{pr_author}\n"
        if team_name:
            comment += f"**👥 Team:** {team_name}\n"
        comment += f"**🎯 Approval Tier:** `{decision.approval_tier.value}`\n"
        
        if decision.required_approvals > 0:
            comment += f"**✋ Required Approvals:** {decision.required_approvals}\n"
        
        comment += "\n---\n\n"
        
        # Resource changes
        comment += "### 📦 Resource Changes\n\n"
        comment += f"| Action | Count |\n"
        comment += f"|--------|-------|\n"
        comment += f"| {status_emoji} **To Create** | `{decision.resource_changes.to_create}` |\n"
        comment += f"| 🔄 **To Change** | `{decision.resource_changes.to_change}` |\n"
        comment += f"| 🗑️ **To Destroy** | `{decision.resource_changes.to_destroy}` |\n"
        comment += f"| **Total** | **`{decision.resource_changes.total}`** |\n\n"
        
        # Cost estimation - only show if we have actual cost data
        if decision.cost_estimate and decision.cost_estimate.monthly_cost > 0:
            comment += "### 💰 Cost Estimation\n\n"
            comment += f"**Monthly Cost:** `${decision.cost_estimate.monthly_cost:.2f} USD/month`\n\n"
            
            if decision.cost_estimate.breakdown_by_service:
                comment += "**Breakdown by Service:**\n\n"
                for service, cost in sorted(decision.cost_estimate.breakdown_by_service.items(), key=lambda x: x[1], reverse=True):
                    comment += f"- **{service.upper()}**: ${cost:.2f}/month\n"
                comment += "\n"
        else:
            comment += "### 💰 Cost Estimation\n\n"
            comment += "💡 Cost analysis will be available via MCP server integration\n\n"
        
        # Security status
        comment += "### 🛡️ Security Validation\n\n"
        if decision.security_passed:
            comment += "✅ All security policies passed\n\n"
        else:
            comment += "❌ Security policy violations detected - see details above\n\n"
        
        # Authorization status
        comment += "### 🔐 Authorization\n\n"
        if decision.team_authorized:
            comment += f"✅ {pr_author} is authorized for this deployment\n\n"
        else:
            comment += f"❌ {pr_author} is not authorized for this deployment\n\n"
        
        # Final decision
        comment += "---\n\n"
        comment += f"### 🎯 Decision: {decision.reason}\n\n"
        
        if decision.approved:
            comment += "🚀 **Next Steps:**\n"
            comment += "- Deployment will proceed automatically\n"
            comment += "- PR will be merged to main branch\n"
            comment += "- Terraform apply will execute\n"
        elif not decision.team_authorized or not decision.security_passed:
            comment += "🛑 **This deployment is blocked.**\n"
            comment += "Please address the issues above and create a new PR.\n"
        else:
            comment += f"⏳ **Waiting for {decision.required_approvals} approval(s)**\n\n"
            comment += "**Approvers must:**\n"
            comment += f"1. Review the plan and cost estimation\n"
            comment += f"2. Approve this PR\n"
            comment += f"3. System will auto-merge once approvals are met\n"
        
        comment += "\n---\n"
        comment += "*Powered by Centralized Terraform Controller | [View Rules](../deployment-rules.yaml)*"
        
        return comment


def main():
    """Main entry point"""
    if len(sys.argv) < 9:
        print("Usage: terrateam-manager.py <pr_author> <account> <environment> <service> <plan_json> <opa_passed> <critical_violations> <tfvars_file> [region]")
        sys.exit(1)
    
    pr_author = sys.argv[1]
    account = sys.argv[2]
    environment = sys.argv[3]
    service = sys.argv[4]
    plan_json_path = sys.argv[5]
    opa_passed = sys.argv[6].lower() == "true"
    critical_violations = int(sys.argv[7])
    tfvars_file = sys.argv[8]
    region = sys.argv[9] if len(sys.argv) > 9 else "us-east-1"
    
    try:
        manager = TerrateamStyleManager("controller/deployment-rules.yaml")
        
        decision = manager.make_deployment_decision(
            pr_author=pr_author,
            account=account,
            environment=environment,
            service=service,
            plan_json_path=plan_json_path,
            opa_passed=opa_passed,
            critical_violations=critical_violations
        )
        
        # Generate backend configuration
        backend_config = manager.generate_backend_config(tfvars_file, account, region)
        
        # Output backend configuration
        backend_output = {
            "backend_type": backend_config["backend"],
            "backend_bucket": backend_config["bucket"],
            "backend_key": backend_config["key"],
            "detected_services": manager.detect_services_from_tfvars(tfvars_file),
            "project_name": manager.extract_project_from_path(tfvars_file),
            "account_short_name": manager.get_account_short_name(account)
        }
        
        # Also save backend config to file
        with open("backend-config.json", "w") as f:
            json.dump(backend_config, f, indent=2)
            
        with open("backend-info.json", "w") as f:
            json.dump(backend_output, f, indent=2)
        
        # Output decision as JSON
        output = {
            "approved": decision.approved,
            "approval_tier": decision.approval_tier.value,
            "required_approvals": decision.required_approvals,
            "reason": decision.reason,
            "team_authorized": decision.team_authorized,
            "security_passed": decision.security_passed,
            "monthly_cost": decision.cost_estimate.monthly_cost if decision.cost_estimate else 0.0,
            "resources_created": decision.resource_changes.to_create,
            "resources_changed": decision.resource_changes.to_change,
            "resources_destroyed": decision.resource_changes.to_destroy,
        }
        
        print(json.dumps(output, indent=2))
        
        # Also save PR comment to file
        team_auth, team_name, _ = manager.check_team_authorization(pr_author, account, environment, service)
        pr_comment = manager.generate_pr_comment(decision, pr_author, team_name if team_auth else None)
        
        with open("pr-comment.md", "w") as f:
            f.write(pr_comment)
        
        sys.exit(0 if decision.approved else 1)
        
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(2)


if __name__ == "__main__":
    main()
