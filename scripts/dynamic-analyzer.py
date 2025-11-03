#!/usr/bin/env python3
"""
Dynamic Multi-Tier Approval Analyzer
Intelligently routes deployments based on risk, cost, and team authorization
"""

import json
import sys
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum


class ApprovalTier(Enum):
    """Dynamic approval tiers"""
    AUTO_APPROVE = "tier0"
    TEAM_APPROVAL = "tier1" 
    PLATFORM_APPROVAL = "tier2"


@dataclass
class AnalysisResult:
    """Dynamic analysis results"""
    tier: ApprovalTier
    requirements: Dict[str, Any]
    reasoning: str
    cost_impact: float
    opa_status: str
    environment: str
    risk_factors: List[str]


class DynamicApprovalAnalyzer:
    """Intelligently analyzes deployment requirements"""
    
    def __init__(self, rules_path: str = "../deployment-rules.yaml"):
        self.rules_path = Path(rules_path)
        self.rules = self._load_rules()
    
    def _load_rules(self) -> Dict:
        """Load dynamic approval rules"""
        try:
            with open(self.rules_path, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            print(f"Warning: Could not load rules: {e}")
            return self._get_default_rules()
    
    def _get_default_rules(self) -> Dict:
        """Default rules if file not found"""
        return {
            "teams": {
                "default-team": {
                    "members": ["pragadeeswarpa"],
                    "permissions": {
                        "auto_approve_under": 50,
                        "environments": ["development", "staging"]
                    }
                }
            },
            "cost_centers": {
                "CC-1001": {
                    "approval_thresholds": {
                        "team_approval": 200,
                        "platform_approval": 500
                    }
                }
            }
        }
    
    def analyze_deployment(
        self, 
        tfvars_path: str, 
        pr_author: str, 
        environment: str = "development"
    ) -> AnalysisResult:
        """
        Main analysis function - determines approval tier dynamically
        """
        # 1. OPA Policy Check
        opa_status = self._check_opa_policies(tfvars_path)
        
        # 2. Cost Impact Analysis
        cost_impact = self._analyze_cost_impact(tfvars_path)
        
        # 3. Environment Risk Assessment
        env_risk = self._assess_environment_risk(environment)
        
        # 4. Team Authorization Check
        team_info = self._check_team_authorization(pr_author, tfvars_path)
        
        # 5. Service Analysis
        service_analysis = self._analyze_services(tfvars_path)
        
        # 6. Dynamic Decision Logic
        return self._make_approval_decision(
            opa_status, cost_impact, env_risk, team_info, service_analysis, environment
        )
    
    def _check_opa_policies(self, tfvars_path: str) -> str:
        """Check OPA policy compliance"""
        # Simulate OPA check - in real implementation, call OPA
        # For now, assume policies pass for demo
        return "PASS"  # or "FAIL"
    
    def _analyze_cost_impact(self, tfvars_path: str) -> float:
        """Analyze cost impact of changes"""
        # Simplified cost calculation
        # In real implementation, integrate with cloud cost APIs
        
        try:
            with open(tfvars_path, 'r') as f:
                content = f.read()
            
            # Simple heuristics for demo
            cost = 0
            if 's3_buckets' in content:
                cost += 10  # S3 buckets are cheap
            if 'rds_instances' in content:
                cost += 200  # RDS is expensive
            if 'ec2_instances' in content:
                cost += 100  # EC2 moderate cost
            if 'kms_keys' in content:
                cost += 5   # KMS keys are cheap
                
            return cost
            
        except Exception:
            return 0  # Default to no cost if can't analyze
    
    def _assess_environment_risk(self, environment: str) -> Dict[str, Any]:
        """Assess risk level based on environment"""
        risk_levels = {
            "production": {"level": "high", "security_sensitive": True},
            "staging": {"level": "medium", "security_sensitive": False},
            "development": {"level": "low", "security_sensitive": False}
        }
        
        return risk_levels.get(environment, {"level": "medium", "security_sensitive": False})
    
    def _check_team_authorization(self, pr_author: str, tfvars_path: str) -> Dict[str, Any]:
        """Check team authorization and cost center"""
        teams = self.rules.get("teams", {})
        
        for team_name, team_config in teams.items():
            members = team_config.get("members", [])
            if pr_author in members:
                return {
                    "authorized": True,
                    "team": team_name,
                    "config": team_config,
                    "cost_center": team_config.get("cost_center", "unknown")
                }
        
        return {"authorized": False, "team": None, "config": {}, "cost_center": "unknown"}
    
    def _analyze_services(self, tfvars_path: str) -> Dict[str, Any]:
        """Analyze what services are being deployed"""
        try:
            with open(tfvars_path, 'r') as f:
                content = f.read()
            
            services = []
            if 's3_buckets' in content:
                services.append('s3')
            if 'rds_instances' in content:
                services.append('rds')
            if 'kms_keys' in content:
                services.append('kms')
            if 'ec2_instances' in content:
                services.append('ec2')
                
            return {
                "services": services,
                "introduces_new_services": len(services) > 1,  # Simplified logic
                "security_sensitive": any(s in ['kms', 'iam', 'secrets'] for s in services)
            }
            
        except Exception:
            return {"services": [], "introduces_new_services": False, "security_sensitive": False}
    
    def _make_approval_decision(
        self, 
        opa_status: str, 
        cost_impact: float, 
        env_risk: Dict, 
        team_info: Dict, 
        service_analysis: Dict,
        environment: str
    ) -> AnalysisResult:
        """Dynamic decision logic"""
        
        risk_factors = []
        
        # Check OPA failures
        if opa_status == "FAIL":
            if env_risk["level"] == "high":
                return AnalysisResult(
                    tier=ApprovalTier.PLATFORM_APPROVAL,
                    requirements={"platform_override": True, "opa_failed": True},
                    reasoning="OPA policies failed in production environment",
                    cost_impact=cost_impact,
                    opa_status=opa_status,
                    environment=environment,
                    risk_factors=["opa_failure", "production"]
                )
            else:
                risk_factors.append("opa_failure_non_prod")
        
        # Auto-approve conditions (Tier 0)
        team_config = team_info.get("config", {})
        auto_approve_threshold = team_config.get("permissions", {}).get("auto_approve_under", 50)
        
        if (opa_status == "PASS" and 
            cost_impact < auto_approve_threshold and
            env_risk["level"] == "low" and
            team_info["authorized"] and
            not service_analysis["security_sensitive"]):
            
            return AnalysisResult(
                tier=ApprovalTier.AUTO_APPROVE,
                requirements={"auto_approve": True},
                reasoning=f"Low impact (${cost_impact}/month), OPA passed, non-production",
                cost_impact=cost_impact,
                opa_status=opa_status,
                environment=environment,
                risk_factors=[]
            )
        
        # Platform approval conditions (Tier 2)
        cost_center = team_info.get("cost_center", "unknown")
        cost_center_config = self.rules.get("cost_centers", {}).get(cost_center, {})
        platform_threshold = cost_center_config.get("approval_thresholds", {}).get("platform_approval", 500)
        
        if (env_risk["level"] == "high" or
            cost_impact > platform_threshold or
            service_analysis["security_sensitive"] or
            not team_info["authorized"]):
            
            if env_risk["level"] == "high":
                risk_factors.append("production_environment")
            if cost_impact > platform_threshold:
                risk_factors.append("high_cost_impact")
            if service_analysis["security_sensitive"]:
                risk_factors.append("security_sensitive_resources")
            if not team_info["authorized"]:
                risk_factors.append("unauthorized_user")
                
            return AnalysisResult(
                tier=ApprovalTier.PLATFORM_APPROVAL,
                requirements={"platform_approval": True, "approvals_needed": 2},
                reasoning=f"High impact deployment: {', '.join(risk_factors)}",
                cost_impact=cost_impact,
                opa_status=opa_status,
                environment=environment,
                risk_factors=risk_factors
            )
        
        # Default to team approval (Tier 1)
        team_threshold = cost_center_config.get("approval_thresholds", {}).get("team_approval", 200)
        
        if cost_impact > team_threshold:
            risk_factors.append("exceeds_team_budget")
        if service_analysis["introduces_new_services"]:
            risk_factors.append("new_services")
            
        return AnalysisResult(
            tier=ApprovalTier.TEAM_APPROVAL,
            requirements={"team_approval": True, "approvals_needed": 1},
            reasoning=f"Standard team approval: cost ${cost_impact}/month, {len(service_analysis['services'])} services",
            cost_impact=cost_impact,
            opa_status=opa_status,
            environment=environment,
            risk_factors=risk_factors
        )


def main():
    """CLI interface for dynamic analysis"""
    if len(sys.argv) < 4:
        print("Usage: dynamic-analyzer.py <tfvars_path> <pr_author> <environment>")
        sys.exit(1)
    
    tfvars_path = sys.argv[1]
    pr_author = sys.argv[2]
    environment = sys.argv[3]
    
    analyzer = DynamicApprovalAnalyzer()
    result = analyzer.analyze_deployment(tfvars_path, pr_author, environment)
    
    # Output for GitHub Actions
    print(f"::set-output name=tier::{result.tier.value}")
    print(f"::set-output name=requirements::{json.dumps(result.requirements)}")
    print(f"::set-output name=reasoning::{result.reasoning}")
    print(f"::set-output name=cost_impact::{result.cost_impact}")
    print(f"::set-output name=opa_status::{result.opa_status}")
    print(f"::set-output name=environment::{result.environment}")
    print(f"::set-output name=risk_factors::{json.dumps(result.risk_factors)}")
    
    # Human readable output
    print(f"\n📊 Dynamic Analysis Results:")
    print(f"🎯 Approval Tier: {result.tier.value}")
    print(f"💰 Cost Impact: ${result.cost_impact}/month")
    print(f"🔍 OPA Status: {result.opa_status}")
    print(f"🌍 Environment: {result.environment}")
    print(f"📝 Reasoning: {result.reasoning}")
    
    if result.risk_factors:
        print(f"⚠️ Risk Factors: {', '.join(result.risk_factors)}")


if __name__ == "__main__":
    main()