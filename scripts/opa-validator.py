#!/usr/bin/env python3
"""
OPA Terraform Plan Validator

This script validates Terraform plan JSON files using OPA policies.
It automatically discovers plans, runs validation, and generates reports.
"""

import os
import sys
import json
import subprocess
import argparse
import glob
from pathlib import Path
from typing import Dict, List, Any, Optional
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'
)
logger = logging.getLogger(__name__)

class OPAValidator:
    def __init__(self, opa_policies_dir: str, plans_dir: str, debug: bool = False):
        """
        Initialize OPA Validator
        
        Args:
            opa_policies_dir: Path to OPA policies directory
            plans_dir: Path to directory containing Terraform plan JSON files
            debug: Enable debug logging
        """
        self.opa_policies_dir = Path(opa_policies_dir)
        self.plans_dir = Path(plans_dir)
        self.debug = debug
        
        if debug:
            logger.setLevel(logging.DEBUG)
        
        # Validate directories exist
        if not self.opa_policies_dir.exists():
            raise FileNotFoundError(f"OPA policies directory not found: {opa_policies_dir}")
        
        if not self.plans_dir.exists():
            raise FileNotFoundError(f"Plans directory not found: {plans_dir}")
    
    def find_plan_files(self) -> List[Path]:
        """Find all JSON plan files in the plans directory"""
        patterns = ['*.json']
        plan_files = []
        
        for pattern in patterns:
            plan_files.extend(self.plans_dir.glob(pattern))
        
        logger.info(f"🔍 Found {len(plan_files)} plan files:")
        for plan_file in plan_files:
            logger.info(f"   📄 {plan_file.name}")
        
        return plan_files
    
    def analyze_plan(self, plan_file: Path) -> Dict[str, Any]:
        """Analyze a Terraform plan JSON file"""
        logger.info(f"\n📋 Analyzing plan: {plan_file.name}")
        
        try:
            with open(plan_file, 'r') as f:
                plan_data = json.load(f)
            
            # Basic plan analysis
            resource_changes = plan_data.get('resource_changes', [])
            plan_info = {
                'file_name': plan_file.name,
                'file_size': plan_file.stat().st_size,
                'total_resources': len(resource_changes),
                'resource_types': {},
                'actions': {}
            }
            
            # Count resource types and actions
            for resource in resource_changes:
                resource_type = resource.get('type', 'unknown')
                actions = resource.get('change', {}).get('actions', [])
                
                # Count resource types
                plan_info['resource_types'][resource_type] = plan_info['resource_types'].get(resource_type, 0) + 1
                
                # Count actions
                for action in actions:
                    plan_info['actions'][action] = plan_info['actions'].get(action, 0) + 1
            
            logger.info(f"   📊 File size: {plan_info['file_size']:,} bytes")
            logger.info(f"   📊 Total resources: {plan_info['total_resources']}")
            
            if self.debug:
                logger.debug(f"   🔍 Resource types: {plan_info['resource_types']}")
                logger.debug(f"   🔍 Actions: {plan_info['actions']}")
            
            return plan_info
            
        except Exception as e:
            logger.error(f"❌ Error analyzing plan {plan_file.name}: {e}")
            return {'file_name': plan_file.name, 'error': str(e)}
    
    def run_opa_command(self, command: List[str], input_file: Optional[Path] = None) -> Dict[str, Any]:
        """Run an OPA command and return the result"""
        try:
            cmd = ['opa'] + command
            if input_file:
                cmd.extend(['-i', str(input_file)])
            
            if self.debug:
                logger.debug(f"🔧 Running OPA command: {' '.join(cmd)}")
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=self.plans_dir.parent  # Run from parent directory
            )
            
            if result.returncode != 0:
                logger.warning(f"⚠️ OPA command failed (exit {result.returncode}): {result.stderr}")
                return {'success': False, 'error': result.stderr, 'stdout': result.stdout}
            
            # Try to parse JSON output
            try:
                data = json.loads(result.stdout)
                return {'success': True, 'data': data, 'stdout': result.stdout}
            except json.JSONDecodeError:
                return {'success': True, 'data': None, 'stdout': result.stdout}
                
        except Exception as e:
            logger.error(f"❌ Error running OPA command: {e}")
            return {'success': False, 'error': str(e)}
    
    def detect_services(self, plan_file: Path) -> List[str]:
        """Detect which services are in the Terraform plan"""
        logger.info(f"📦 Detecting services in {plan_file.name}...")
        
        command = [
            'eval',
            '-d', str(self.opa_policies_dir),
            'data.terraform.main.deployment_summary.services_detected',
            '--format', 'json'
        ]
        
        result = self.run_opa_command(command, plan_file)
        
        if result['success'] and result['data']:
            try:
                services = result['data']['result'][0]['expressions'][0]['value']
                if isinstance(services, list):
                    logger.info(f"   🎯 Services detected: {', '.join(services) if services else 'None'}")
                    return services
            except (KeyError, IndexError, TypeError):
                pass
        
        logger.info(f"   ℹ️ No specific services detected")
        return []
    
    def validate_plan(self, plan_file: Path) -> Dict[str, Any]:
        """Validate a single plan with OPA policies"""
        logger.info(f"🛡️ Validating {plan_file.name} with OPA policies...")
        
        # Run OPA validation
        command = [
            'eval',
            '-d', str(self.opa_policies_dir),
            'data.terraform.main.deny',
            '--format', 'json'
        ]
        
        result = self.run_opa_command(command, plan_file)
        
        if not result['success']:
            return {
                'file_name': plan_file.name,
                'success': False,
                'error': result['error'],
                'total_violations': 0,
                'violations_by_severity': {},
                'violations': []
            }
        
        # Parse violations
        violations = []
        violations_by_severity = {'critical': 0, 'high': 0, 'medium': 0, 'low': 0}
        
        try:
            violations_data = result['data']['result'][0]['expressions'][0]['value']
            
            if isinstance(violations_data, dict):
                for violation_key in violations_data.keys():
                    try:
                        violation = json.loads(violation_key)
                        if isinstance(violation, dict):
                            violations.append(violation)
                            severity = violation.get('severity', 'unknown')
                            if severity in violations_by_severity:
                                violations_by_severity[severity] += 1
                    except (json.JSONDecodeError, TypeError):
                        continue
        
        except (KeyError, IndexError, TypeError) as e:
            if self.debug:
                logger.debug(f"   🔍 Error parsing violations: {e}")
        
        total_violations = len(violations)
        
        # Log results
        if total_violations == 0:
            logger.info(f"   ✅ No violations found")
        else:
            logger.info(f"   ❌ Found {total_violations} violations:")
            for severity, count in violations_by_severity.items():
                if count > 0:
                    emoji = {'critical': '🔴', 'high': '🟠', 'medium': '🟡', 'low': '🟢'}.get(severity, '⚪')
                    logger.info(f"      {emoji} {severity.title()}: {count}")
        
        return {
            'file_name': plan_file.name,
            'success': True,
            'total_violations': total_violations,
            'violations_by_severity': violations_by_severity,
            'violations': violations
        }
    
    def generate_report(self, validation_results: List[Dict[str, Any]], 
                       services_results: List[List[str]]) -> Dict[str, Any]:
        """Generate a comprehensive validation report"""
        
        total_plans = len(validation_results)
        successful_validations = sum(1 for r in validation_results if r.get('success', False))
        total_violations = sum(r.get('total_violations', 0) for r in validation_results)
        
        # Aggregate violations by severity
        aggregate_violations = {'critical': 0, 'high': 0, 'medium': 0, 'low': 0}
        for result in validation_results:
            if result.get('success'):
                for severity, count in result.get('violations_by_severity', {}).items():
                    if severity in aggregate_violations:
                        aggregate_violations[severity] += count
        
        # Collect all detected services
        all_services = set()
        for services in services_results:
            all_services.update(services)
        
        report = {
            'summary': {
                'total_plans': total_plans,
                'successful_validations': successful_validations,
                'failed_validations': total_plans - successful_validations,
                'total_violations': total_violations,
                'violations_by_severity': aggregate_violations,
                'services_detected': sorted(list(all_services)),
                'validation_status': 'passed' if total_violations == 0 else 'failed'
            },
            'plan_results': validation_results
        }
        
        return report
    
    def save_report(self, report: Dict[str, Any], output_file: str):
        """Save the validation report to a JSON file"""
        try:
            with open(output_file, 'w') as f:
                json.dump(report, f, indent=2)
            logger.info(f"📄 Report saved to: {output_file}")
        except Exception as e:
            logger.error(f"❌ Error saving report: {e}")
    
    def print_summary(self, report: Dict[str, Any]):
        """Print a summary of the validation results"""
        summary = report['summary']
        
        logger.info("\n" + "="*60)
        logger.info("📊 OPA VALIDATION SUMMARY")
        logger.info("="*60)
        logger.info(f"Plans validated: {summary['total_plans']}")
        logger.info(f"Successful validations: {summary['successful_validations']}")
        logger.info(f"Failed validations: {summary['failed_validations']}")
        logger.info(f"Total violations: {summary['total_violations']}")
        
        if summary['violations_by_severity']:
            logger.info("\nViolations by severity:")
            for severity, count in summary['violations_by_severity'].items():
                if count > 0:
                    emoji = {'critical': '🔴', 'high': '🟠', 'medium': '🟡', 'low': '🟢'}.get(severity, '⚪')
                    logger.info(f"  {emoji} {severity.title()}: {count}")
        
        if summary['services_detected']:
            logger.info(f"\nServices detected: {', '.join(summary['services_detected'])}")
        
        status_emoji = "✅" if summary['validation_status'] == 'passed' else "❌"
        logger.info(f"\nValidation Status: {status_emoji} {summary['validation_status'].upper()}")
        logger.info("="*60)
    
    def validate_all(self, output_file: Optional[str] = None) -> Dict[str, Any]:
        """Run validation on all plan files"""
        logger.info("🛡️ Starting OPA validation for all plans...")
        
        # Find all plan files
        plan_files = self.find_plan_files()
        
        if not plan_files:
            logger.warning("⚠️ No plan files found")
            return {'summary': {'validation_status': 'skipped', 'total_plans': 0}}
        
        # Validate each plan
        validation_results = []
        services_results = []
        
        for plan_file in plan_files:
            # Analyze plan
            plan_info = self.analyze_plan(plan_file)
            
            # Detect services
            services = self.detect_services(plan_file)
            services_results.append(services)
            
            # Validate with OPA
            validation_result = self.validate_plan(plan_file)
            validation_results.append(validation_result)
        
        # Generate report
        report = self.generate_report(validation_results, services_results)
        
        # Save report if requested
        if output_file:
            self.save_report(report, output_file)
        
        # Print summary
        self.print_summary(report)
        
        return report

def main():
    parser = argparse.ArgumentParser(description='OPA Terraform Plan Validator')
    parser.add_argument('--opa-policies', required=True, 
                       help='Path to OPA policies directory')
    parser.add_argument('--plans-dir', required=True,
                       help='Path to directory containing Terraform plan JSON files')
    parser.add_argument('--output', 
                       help='Output file for JSON report')
    parser.add_argument('--debug', action='store_true',
                       help='Enable debug logging')
    
    args = parser.parse_args()
    
    try:
        # Initialize validator
        validator = OPAValidator(
            opa_policies_dir=args.opa_policies,
            plans_dir=args.plans_dir,
            debug=args.debug
        )
        
        # Run validation
        report = validator.validate_all(output_file=args.output)
        
        # Set exit code based on validation status
        if report['summary']['validation_status'] == 'failed':
            sys.exit(1)
        elif report['summary']['validation_status'] == 'skipped':
            sys.exit(2)
        else:
            sys.exit(0)
            
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        if args.debug:
            import traceback
            traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    main()