# =============================================================================
# MULTI-SERVICE TERRAFORM OPA POLICY - MAIN ENTRY POINT
# =============================================================================
# This is the main policy that routes Terraform plans to service-specific
# validation policies based on resource types detected in the plan.
#
# SUPPORTED SERVICES:
# - S3 (Simple Storage Service)
# - IAM (Identity and Access Management)
# - KMS (Key Management Service)
# - Lambda (Serverless Functions)
# - VPC (Virtual Private Cloud)
# - EC2 (Elastic Compute Cloud)
# - RDS (Relational Database Service)
#
# USAGE:
#   opa eval --data terraform/ --input plan.json "data.terraform.main.deny"
#
# OUTPUT:
#   Violations from all applicable service-specific policies
# =============================================================================

package terraform.main

import rego.v1

# Import service-specific policies
import data.terraform.s3
import data.terraform.iam
import data.terraform.kms
import data.terraform.lambda
import data.terraform.vpc
import data.terraform.ec2
import data.terraform.rds

# =============================================================================
# RESOURCE TYPE DETECTION
# =============================================================================

# Detect which AWS services are being deployed
has_s3_resources if {
    some resource in input.resource_changes
    startswith(resource.type, "aws_s3")
}

has_iam_resources if {
    some resource in input.resource_changes
    resource.type in ["aws_iam_role", "aws_iam_policy", "aws_iam_user", "aws_iam_group", "aws_iam_role_policy_attachment"]
}

has_kms_resources if {
    some resource in input.resource_changes
    startswith(resource.type, "aws_kms")
}

has_lambda_resources if {
    some resource in input.resource_changes
    startswith(resource.type, "aws_lambda")
}

has_vpc_resources if {
    some resource in input.resource_changes
    resource.type in ["aws_vpc", "aws_subnet", "aws_security_group", "aws_route_table", "aws_nat_gateway"]
}

has_ec2_resources if {
    some resource in input.resource_changes
    resource.type in ["aws_instance", "aws_ebs_volume", "aws_ami"]
}

has_rds_resources if {
    some resource in input.resource_changes
    startswith(resource.type, "aws_db")
}

# =============================================================================
# AGGREGATE VIOLATIONS FROM ALL SERVICES
# =============================================================================

# Collect all violations from applicable service policies
deny := all_violations

# Aggregate violations from all services
all_violations := s3_violations

# S3 violations if S3 resources detected
s3_violations := s3.deny if {
    has_s3_resources
} else := {}

# IAM violations if IAM resources detected  
iam_violations := iam.deny if {
    has_iam_resources
} else := {}

# KMS violations if KMS resources detected
kms_violations := kms.deny if {
    has_kms_resources
} else := {}

# Lambda violations if Lambda resources detected
lambda_violations := lambda.deny if {
    has_lambda_resources
} else := {}

# VPC violations if VPC resources detected
vpc_violations := vpc.deny if {
    has_vpc_resources
} else := {}

# EC2 violations if EC2 resources detected
ec2_violations := ec2.deny if {
    has_ec2_resources
} else := {}

# RDS violations if RDS resources detected
rds_violations := rds.deny if {
    has_rds_resources
} else := {}

# =============================================================================
# DEPLOYMENT SUMMARY
# =============================================================================

# Provide deployment summary
deployment_summary := {
    "services_detected": services_detected,
    "total_resources": count(input.resource_changes),
    "resources_by_action": resources_by_action,
    "policy_version": "1.0.0"
}

services_detected contains "S3" if has_s3_resources
services_detected contains "IAM" if has_iam_resources
services_detected contains "KMS" if has_kms_resources
services_detected contains "Lambda" if has_lambda_resources
services_detected contains "VPC" if has_vpc_resources
services_detected contains "EC2" if has_ec2_resources
services_detected contains "RDS" if has_rds_resources

resources_by_action := {action: count([r | some r in input.resource_changes; r.change.actions[_] == action]) |
    some action in ["create", "update", "delete", "no-op"]
}

# =============================================================================
# PIPELINE INTEGRATION - VALIDATE_PLAN FUNCTION
# =============================================================================

# Main validation function called by the centralized pipeline
validate_plan := {
    "total_violations": total_violations,
    "critical_violations": critical_violations,
    "high_violations": high_violations,
    "medium_violations": medium_violations,
    "low_violations": low_violations,
    "violations": all_violations,
    "deployment_summary": deployment_summary
}

# Count violations by severity (get violation objects from keys)
total_violations := count(all_violations)

# Get all violation objects directly from object.keys()
violation_objects := object.keys(all_violations)

critical_violations := count([v | 
    v := violation_objects[_]
    v.severity == "critical"
])
high_violations := count([v | 
    v := violation_objects[_]
    v.severity == "high"
])
medium_violations := count([v | 
    v := violation_objects[_]
    v.severity == "medium"
])
low_violations := count([v | 
    v := violation_objects[_]
    v.severity == "low"
])
