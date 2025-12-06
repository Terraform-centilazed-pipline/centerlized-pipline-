# AWS DevOps Agent Integration - Implementation Plan

**Version:** 1.0  
**Date:** December 6, 2025  
**Status:** Planning Phase  
**Estimated Timeline:** 2-3 weeks  

---

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Phase 1: Infrastructure Setup](#phase-1-infrastructure-setup)
4. [Phase 2: Lambda Development](#phase-2-lambda-development)
5. [Phase 3: EventBridge Configuration](#phase-3-eventbridge-configuration)
6. [Phase 4: Workflow Integration](#phase-4-workflow-integration)
7. [Phase 5: Testing & Validation](#phase-5-testing-validation)
8. [Phase 6: Production Rollout](#phase-6-production-rollout)
9. [Rollback Plan](#rollback-plan)
10. [Success Criteria](#success-criteria)

---

## Overview

### Objective

Implement autonomous drift detection and automated remediation for Terraform-managed AWS infrastructure using AWS DevOps Agent integration.

### Approach

**Non-Disruptive Implementation:** All existing workflows remain untouched. New components will be added separately and tested in isolation before integration.

### Key Principles

- ✅ **Zero disruption** to existing deployment pipeline
- ✅ **Parallel development** - new workflow alongside existing ones
- ✅ **Opt-in approach** - resources must be tagged to enable drift detection
- ✅ **Progressive rollout** - test in dev → staging → production
- ✅ **Complete rollback capability** at every phase

---

## Prerequisites

### 1. AWS Account Requirements

**Access Needed:**
- [ ] AWS CLI configured with appropriate credentials
- [ ] IAM permissions to create:
  - DynamoDB tables
  - Lambda functions
  - EventBridge rules
  - SNS topics
  - IAM roles and policies
  - SSM parameters
- [ ] Access to AWS DevOps Agent preview (contact AWS Support if needed)

**Verification:**
```bash
# Test AWS CLI access
aws sts get-caller-identity

# Check available services
aws dynamodb list-tables
aws lambda list-functions
aws events list-rules
```

### 2. GitHub Requirements

**Setup Needed:**
- [ ] GitHub Personal Access Token (PAT) with `repo` scope
- [ ] GitHub Actions enabled on repository
- [ ] Permissions to create workflows
- [ ] Permissions to configure repository secrets

**Verification:**
```bash
# Test GitHub CLI access
gh auth status

# List existing workflows
gh workflow list
```

### 3. Development Tools

**Required:**
- [ ] Terraform 1.11.0 or higher
- [ ] Python 3.11 or higher
- [ ] AWS CLI v2
- [ ] GitHub CLI (`gh`)
- [ ] OPA CLI 0.60.0 or higher
- [ ] jq (JSON processor)

**Installation Check:**
```bash
terraform version
python3 --version
aws --version
gh --version
opa version
jq --version
```

### 4. Knowledge Requirements

**Team Skills:**
- [ ] Understanding of Terraform state management
- [ ] AWS Lambda development (Python)
- [ ] GitHub Actions workflow syntax
- [ ] EventBridge event patterns
- [ ] DynamoDB data modeling
- [ ] OPA policy language (Rego)

---

## Phase 1: Infrastructure Setup

**Duration:** 3-4 days  
**Goal:** Create all AWS infrastructure components

### Step 1.1: Create DynamoDB Tables

**Priority:** P0 (Critical)

**Tables to Create:**

1. **terraform-deployment-metadata**
   - Purpose: Store deployment information for drift correlation
   - Partition Key: `deployment_id` (String)
   - Sort Key: `deployed_at` (String)
   - GSI: `resource-arn-index` on `resource_arn`
   - Billing: PAY_PER_REQUEST

2. **terraform-state-locks**
   - Purpose: Prevent concurrent drift operations
   - Partition Key: `lock_id` (String)
   - TTL: Enabled on `ttl` attribute (5 min auto-expire)
   - Billing: PAY_PER_REQUEST

3. **drift-history**
   - Purpose: Audit trail of drift events
   - Partition Key: `drift_event_id` (String)
   - Sort Key: `timestamp` (String)
   - GSI: `severity-timestamp-index` on `severity` + `timestamp`
   - TTL: Enabled on `ttl` attribute (90 days auto-expire)
   - Billing: PAY_PER_REQUEST

4. **policy-versions**
   - Purpose: Track OPA policy evolution
   - Partition Key: `policy_id` (String)
   - Sort Key: `version` (String)
   - Billing: PAY_PER_REQUEST

**Action Items:**
```bash
# Create script: scripts/setup/create-dynamodb-tables.sh
# This script will create all 4 tables with proper configuration

# Test the script in a dev account first
./scripts/setup/create-dynamodb-tables.sh --environment dev

# Verify tables created
aws dynamodb list-tables | grep terraform
aws dynamodb describe-table --table-name terraform-deployment-metadata
```

**Validation:**
- [ ] All 4 tables created successfully
- [ ] GSI indexes active on required tables
- [ ] TTL configuration enabled where needed
- [ ] Tables accessible with test read/write operations

### Step 1.2: Create IAM Roles

**Priority:** P0 (Critical)

**Roles to Create:**

1. **lambda-drift-orchestrator-role**
   - Service: lambda.amazonaws.com
   - Policies:
     - DynamoDB read/write on all 4 tables
     - SSM GetParameter on `/github/*`
     - EventBridge PutEvents
     - CloudWatch Logs write

2. **lambda-drift-callback-role**
   - Service: lambda.amazonaws.com
   - Policies:
     - DynamoDB read/write on `drift-history`
     - CloudWatch PutMetricData
     - CloudWatch Logs write

3. **github-actions-drift-role** (if separate from existing)
   - Trusted entity: GitHub OIDC provider
   - Policies:
     - DynamoDB read/write on `terraform-deployment-metadata`
     - DynamoDB write on `drift-history`
     - Lambda Invoke on callback function
     - Terraform state bucket access
     - Required AWS service permissions (S3, KMS, etc.)

**Action Items:**
```bash
# Create script: scripts/setup/create-iam-roles.sh

# Create roles
./scripts/setup/create-iam-roles.sh

# Verify role creation
aws iam get-role --role-name lambda-drift-orchestrator-role
aws iam list-attached-role-policies --role-name lambda-drift-orchestrator-role
```

**Validation:**
- [ ] All IAM roles created with proper trust policies
- [ ] Policies attached and verified
- [ ] Least-privilege principle followed
- [ ] Roles can be assumed by intended services

### Step 1.3: Create SNS Topic and Subscriptions

**Priority:** P1 (High)

**Topics to Create:**

1. **drift-detected-events**
   - Purpose: Fan-out drift events to multiple subscribers
   - Subscriptions:
     - Lambda: `drift-workflow-orchestrator`
     - Email: ops-team@company.com (optional)
     - Slack: via AWS Chatbot (optional)

**Action Items:**
```bash
# Create SNS topic
aws sns create-topic --name drift-detected-events

# Get topic ARN
TOPIC_ARN=$(aws sns list-topics | jq -r '.Topics[] | select(.TopicArn | contains("drift-detected-events")) | .TopicArn')

# Subscribe email (optional)
aws sns subscribe \
  --topic-arn $TOPIC_ARN \
  --protocol email \
  --notification-endpoint ops-team@company.com
```

**Validation:**
- [ ] SNS topic created successfully
- [ ] Topic ARN documented
- [ ] Test message can be published
- [ ] Email subscription confirmed (if configured)

### Step 1.4: Store Secrets in SSM Parameter Store

**Priority:** P0 (Critical)

**Parameters to Create:**

1. **`/github/pat-token`**
   - Type: SecureString
   - Value: GitHub Personal Access Token with `repo` scope
   - Description: Used by Lambda to trigger GitHub workflows

2. **`/slack/webhook-url`** (optional)
   - Type: SecureString
   - Value: Slack webhook URL for notifications
   - Description: Drift alert notifications

**Action Items:**
```bash
# Store GitHub PAT (replace with actual token)
aws ssm put-parameter \
  --name /github/pat-token \
  --value "ghp_XXXXXXXXXXXXXXXXXXXXX" \
  --type SecureString \
  --description "GitHub PAT for triggering drift remediation workflows"

# Verify parameter stored
aws ssm get-parameter --name /github/pat-token --with-decryption
```

**Validation:**
- [ ] Parameters stored successfully
- [ ] Parameters encrypted with KMS
- [ ] Lambda IAM role has permission to read parameters
- [ ] Test retrieval from Lambda (use test event)

**Phase 1 Completion Checklist:**
- [ ] All DynamoDB tables created and tested
- [ ] All IAM roles created with proper policies
- [ ] SNS topic created and configured
- [ ] SSM parameters stored securely
- [ ] Documentation updated with ARNs and names

---

## Phase 2: Lambda Development

**Duration:** 4-5 days  
**Goal:** Develop, test, and deploy Lambda functions

### Step 2.1: Setup Lambda Development Environment

**Priority:** P0 (Critical)

**Directory Structure:**
```
lambda/
├── workflow-orchestrator/
│   ├── lambda_function.py       # Main handler
│   ├── requirements.txt          # Dependencies
│   ├── config.py                 # Configuration
│   ├── utils.py                  # Helper functions
│   └── tests/
│       ├── test_lambda.py
│       └── test_events.json
├── agent-callback/
│   ├── lambda_function.py
│   ├── requirements.txt
│   └── tests/
│       ├── test_callback.py
│       └── test_events.json
└── shared/
    └── dynamo_helpers.py         # Shared DynamoDB utilities
```

**Action Items:**
```bash
# Create directory structure
mkdir -p lambda/{workflow-orchestrator,agent-callback,shared}/{tests,}

# Create virtual environment for development
cd lambda/workflow-orchestrator
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install boto3 requests pytest moto
pip freeze > requirements.txt
```

**Validation:**
- [ ] Directory structure created
- [ ] Virtual environment set up
- [ ] Dependencies installed
- [ ] Test framework configured

### Step 2.2: Develop workflow-orchestrator Lambda

**Priority:** P0 (Critical)

**Function Specifications:**
- Runtime: Python 3.11
- Memory: 512 MB
- Timeout: 60 seconds
- Environment Variables:
  - `METADATA_TABLE`: terraform-deployment-metadata
  - `LOCKS_TABLE`: terraform-state-locks
  - `DRIFT_TABLE`: drift-history
  - `POLICY_TABLE`: policy-versions
  - `GITHUB_OWNER`: Terraform-centilazed-pipline
  - `GITHUB_REPO`: tf-module

**Core Functions:**
1. `lambda_handler()` - Main entry point
2. `get_deployment_metadata()` - Query DynamoDB for deployment info
3. `acquire_state_lock()` - Lock management
4. `check_policy_compatibility()` - Version validation
5. `calculate_severity()` - Risk assessment
6. `trigger_github_workflow()` - API call to GitHub
7. `record_drift_event()` - Audit logging

**Action Items:**
```bash
# Copy reference implementation from documentation
cp docs/AWS-DEVOPS-AGENT-INTEGRATION-v2.0.md lambda/workflow-orchestrator/REFERENCE.md

# Implement lambda_function.py (use documentation as reference)
# Implementation should match the code in Section 3.1 of architecture doc

# Create unit tests
cat > lambda/workflow-orchestrator/tests/test_lambda.py << 'EOF'
# Test cases for workflow orchestrator
import pytest
from lambda_function import (
    calculate_severity,
    calculate_priority,
    check_policy_compatibility
)

def test_calculate_severity_critical():
    # Test critical severity detection
    pass

def test_calculate_priority():
    # Test priority calculation
    pass
EOF

# Run tests locally
pytest lambda/workflow-orchestrator/tests/
```

**Validation:**
- [ ] All functions implemented
- [ ] Unit tests passing (>80% coverage)
- [ ] Error handling implemented
- [ ] Logging configured
- [ ] Local testing with moto (AWS mocking) successful

### Step 2.3: Develop agent-callback Lambda

**Priority:** P1 (High)

**Function Specifications:**
- Runtime: Python 3.11
- Memory: 256 MB
- Timeout: 30 seconds
- Environment Variables:
  - `DRIFT_TABLE`: drift-history

**Core Functions:**
1. `lambda_handler()` - Main entry point
2. `update_drift_history()` - Update remediation status
3. `publish_metrics()` - CloudWatch metrics

**Action Items:**
```bash
# Implement agent-callback
# Reference: Section 3.2 of architecture doc

# Create unit tests
pytest lambda/agent-callback/tests/

# Test CloudWatch metric publishing
```

**Validation:**
- [ ] Function implemented
- [ ] Unit tests passing
- [ ] CloudWatch metrics tested
- [ ] Error handling verified

### Step 2.4: Package and Deploy Lambda Functions

**Priority:** P0 (Critical)

**Packaging Process:**
```bash
# Package workflow-orchestrator
cd lambda/workflow-orchestrator
pip install -r requirements.txt -t .
zip -r ../../orchestrator.zip . -x "*.pyc" -x "*__pycache__*" -x "tests/*" -x "venv/*"

# Package agent-callback
cd ../agent-callback
pip install -r requirements.txt -t .
zip -r ../../callback.zip . -x "*.pyc" -x "*__pycache__*" -x "tests/*" -x "venv/*"
```

**Deployment:**
```bash
# Deploy to dev environment first
aws lambda create-function \
  --function-name drift-workflow-orchestrator-dev \
  --runtime python3.11 \
  --role arn:aws:iam::ACCOUNT_ID:role/lambda-drift-orchestrator-role \
  --handler lambda_function.lambda_handler \
  --zip-file fileb://orchestrator.zip \
  --timeout 60 \
  --memory-size 512 \
  --environment "Variables={
    METADATA_TABLE=terraform-deployment-metadata,
    LOCKS_TABLE=terraform-state-locks,
    DRIFT_TABLE=drift-history,
    POLICY_TABLE=policy-versions,
    GITHUB_OWNER=Terraform-centilazed-pipline,
    GITHUB_REPO=tf-module
  }"

# Deploy callback function
aws lambda create-function \
  --function-name drift-agent-callback-dev \
  --runtime python3.11 \
  --role arn:aws:iam::ACCOUNT_ID:role/lambda-drift-callback-role \
  --handler lambda_function.lambda_handler \
  --zip-file fileb://callback.zip \
  --timeout 30 \
  --memory-size 256 \
  --environment "Variables={DRIFT_TABLE=drift-history}"
```

**Validation:**
- [ ] Functions deployed successfully
- [ ] Environment variables configured
- [ ] IAM roles attached correctly
- [ ] Functions can be invoked manually
- [ ] CloudWatch log groups created

### Step 2.5: Test Lambda Functions with Mock Events

**Priority:** P0 (Critical)

**Test Scenarios:**

1. **Test workflow-orchestrator with mock drift event:**
```bash
# Create test event
cat > lambda/workflow-orchestrator/tests/mock-drift-event.json << 'EOF'
{
  "Records": [
    {
      "Sns": {
        "Message": "{\"version\":\"0\",\"id\":\"test-drift-001\",\"detail-type\":\"AWS DevOps Agent - Drift Detected\",\"source\":\"aws.devops-agent\",\"time\":\"2025-12-06T10:00:00Z\",\"region\":\"us-east-1\",\"resources\":[\"arn:aws:s3:::test-bucket\"],\"detail\":{\"driftType\":\"configuration_change\",\"resourceType\":\"AWS::S3::Bucket\",\"resourceArn\":\"arn:aws:s3:::test-bucket\",\"changedProperties\":[\"ServerSideEncryptionConfiguration\"],\"detectedBy\":\"cloudtrail_analysis\",\"changeAuthor\":\"test-user@example.com\",\"changeTime\":\"2025-12-06T09:55:00Z\",\"severity\":\"HIGH\",\"tags\":{\"ManagedBy\":\"terraform\",\"AutoRevert\":\"true\",\"Environment\":\"dev\"}}}"
      }
    }
  ]
}
EOF

# Invoke Lambda with test event
aws lambda invoke \
  --function-name drift-workflow-orchestrator-dev \
  --payload file://lambda/workflow-orchestrator/tests/mock-drift-event.json \
  --cli-binary-format raw-in-base64-out \
  response.json

# Check response
cat response.json
```

2. **Test agent-callback:**
```bash
# Create test event
cat > lambda/agent-callback/tests/mock-callback-event.json << 'EOF'
{
  "drift_event_id": "test-drift-001",
  "remediation_status": "success",
  "mttr_seconds": 120
}
EOF

# Invoke callback
aws lambda invoke \
  --function-name drift-agent-callback-dev \
  --payload file://lambda/agent-callback/tests/mock-callback-event.json \
  --cli-binary-format raw-in-base64-out \
  response.json
```

**Validation:**
- [ ] workflow-orchestrator processes drift events correctly
- [ ] DynamoDB tables updated with test data
- [ ] State locks acquired and released properly
- [ ] agent-callback updates drift history
- [ ] CloudWatch metrics published
- [ ] No errors in CloudWatch logs

**Phase 2 Completion Checklist:**
- [ ] Both Lambda functions developed and tested
- [ ] Unit tests passing with good coverage
- [ ] Functions deployed to dev environment
- [ ] Manual testing successful with mock events
- [ ] CloudWatch logging verified
- [ ] Error handling tested

---

## Phase 3: EventBridge Configuration

**Duration:** 2 days  
**Goal:** Configure event routing from DevOps Agent to Lambda

### Step 3.1: Subscribe Lambda to SNS Topic

**Priority:** P0 (Critical)

**Action Items:**
```bash
# Get SNS topic ARN
TOPIC_ARN=$(aws sns list-topics | jq -r '.Topics[] | select(.TopicArn | contains("drift-detected-events")) | .TopicArn')

# Get Lambda function ARN
LAMBDA_ARN=$(aws lambda get-function --function-name drift-workflow-orchestrator-dev | jq -r '.Configuration.FunctionArn')

# Add Lambda permission to be invoked by SNS
aws lambda add-permission \
  --function-name drift-workflow-orchestrator-dev \
  --statement-id AllowSNSInvoke \
  --action lambda:InvokeFunction \
  --principal sns.amazonaws.com \
  --source-arn $TOPIC_ARN

# Subscribe Lambda to SNS
aws sns subscribe \
  --topic-arn $TOPIC_ARN \
  --protocol lambda \
  --notification-endpoint $LAMBDA_ARN
```

**Validation:**
- [ ] Lambda subscription confirmed
- [ ] Test message published to SNS triggers Lambda
- [ ] CloudWatch logs show Lambda invocation

### Step 3.2: Create EventBridge Rule

**Priority:** P0 (Critical)

**Event Pattern:**
```json
{
  "source": ["aws.devops-agent"],
  "detail-type": ["AWS DevOps Agent - Drift Detected"],
  "detail": {
    "tags": {
      "ManagedBy": ["terraform"],
      "AutoRevert": ["true"]
    }
  }
}
```

**Action Items:**
```bash
# Create EventBridge rule
aws events put-rule \
  --name devops-agent-drift-detection-dev \
  --description "Route DevOps Agent drift events to SNS" \
  --event-pattern '{
    "source": ["aws.devops-agent"],
    "detail-type": ["AWS DevOps Agent - Drift Detected"],
    "detail": {
      "tags": {
        "ManagedBy": ["terraform"],
        "AutoRevert": ["true"]
      }
    }
  }' \
  --state ENABLED

# Add SNS as target
aws events put-targets \
  --rule devops-agent-drift-detection-dev \
  --targets "Id"="1","Arn"="$TOPIC_ARN"

# Grant EventBridge permission to publish to SNS
aws sns set-topic-attributes \
  --topic-arn $TOPIC_ARN \
  --attribute-name Policy \
  --attribute-value '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Principal": {"Service": "events.amazonaws.com"},
      "Action": "sns:Publish",
      "Resource": "'$TOPIC_ARN'"
    }]
  }'
```

**Validation:**
- [ ] EventBridge rule created successfully
- [ ] Rule is in ENABLED state
- [ ] Target configured correctly
- [ ] SNS permissions set

### Step 3.3: Test End-to-End Event Flow

**Priority:** P0 (Critical)

**Test Method:**
```bash
# Send test event to EventBridge
aws events put-events \
  --entries '[
    {
      "Source": "aws.devops-agent",
      "DetailType": "AWS DevOps Agent - Drift Detected",
      "Detail": "{\"driftType\":\"configuration_change\",\"resourceType\":\"AWS::S3::Bucket\",\"resourceArn\":\"arn:aws:s3:::test-bucket-end-to-end\",\"changedProperties\":[\"ServerSideEncryptionConfiguration\"],\"detectedBy\":\"cloudtrail_analysis\",\"changeAuthor\":\"test@example.com\",\"changeTime\":\"2025-12-06T10:00:00Z\",\"severity\":\"HIGH\",\"tags\":{\"ManagedBy\":\"terraform\",\"AutoRevert\":\"true\",\"Environment\":\"dev\"}}",
      "Resources": ["arn:aws:s3:::test-bucket-end-to-end"]
    }
  ]'

# Monitor Lambda execution
aws logs tail /aws/lambda/drift-workflow-orchestrator-dev --follow
```

**Expected Flow:**
1. ✅ Test event published to EventBridge
2. ✅ EventBridge rule matches the event
3. ✅ Event routed to SNS topic
4. ✅ SNS triggers Lambda function
5. ✅ Lambda processes event (even if it fails to find metadata - expected for test)
6. ✅ Logs visible in CloudWatch

**Validation:**
- [ ] Complete event flow works end-to-end
- [ ] Lambda receives proper event structure
- [ ] No permission errors
- [ ] Timing is acceptable (<5 seconds from EventBridge to Lambda)

**Phase 3 Completion Checklist:**
- [ ] SNS subscription configured
- [ ] EventBridge rule created and enabled
- [ ] Permissions configured correctly
- [ ] End-to-end test successful
- [ ] Event flow documented

---

## Phase 4: Workflow Integration

**Duration:** 5-6 days  
**Goal:** Create new GitHub Actions workflow without modifying existing ones

### Step 4.1: Design New Workflow File

**Priority:** P0 (Critical)

**Workflow Name:** `terraform-drift-controller.yml`

**Key Design Decisions:**
- ✅ Separate file from existing workflows
- ✅ Triggered ONLY by `repository_dispatch` event type `drift-detected`
- ✅ Can also be triggered manually via `workflow_dispatch` for testing
- ✅ Checks out specific commit SHA from drift event
- ✅ Auto-approves applies (since it's reverting to known-good state)
- ✅ Runs full OPA validation before applying

**Workflow Structure:**
```yaml
name: Terraform Drift Controller (AWS DevOps Agent)

on:
  # Triggered by Lambda orchestrator
  repository_dispatch:
    types: [drift-detected]
  
  # Manual testing only
  workflow_dispatch:
    inputs:
      drift_event_id:
        description: 'Drift Event ID'
        required: true
      git_commit_sha:
        description: 'Original deployment commit SHA'
        required: true
      tfvars_path:
        description: 'Path to tfvars file'
        required: true
      deployment_id:
        description: 'Deployment ID'
        required: true

# ... rest of workflow
```

**Action Items:**
```bash
# Create new workflow file (do NOT modify existing workflows)
touch .github/workflows/terraform-drift-controller.yml

# Document the workflow purpose in README
cat >> docs/DRIFT-WORKFLOW-GUIDE.md << 'EOF'
# Drift Controller Workflow

This workflow is ONLY for AWS DevOps Agent drift remediation.
It does NOT affect normal deployments which use `centralized-controller.yml`.

Trigger: repository_dispatch event with type "drift-detected"
Purpose: Revert unauthorized infrastructure changes
EOF
```

**Validation:**
- [ ] Workflow file created in correct location
- [ ] No conflicts with existing workflow files
- [ ] Workflow documented separately

### Step 4.2: Implement Workflow Jobs

**Priority:** P0 (Critical)

**Jobs to Implement:**

1. **parse-drift-event**
   - Extract payload from `repository_dispatch`
   - Set outputs for subsequent jobs
   - Validate required fields present

2. **terraform-revert**
   - Checkout specific commit SHA
   - Setup Terraform
   - Configure AWS credentials (OIDC)
   - Terraform init
   - Terraform plan with original tfvars
   - Run OPA validation
   - Terraform apply with auto-approve
   - Calculate MTTR

3. **record-metadata** (if success)
   - Update DynamoDB drift-history table
   - Invoke callback Lambda
   - Post Slack notification (optional)

4. **handle-failure** (if failure)
   - Log failure details
   - Create GitHub issue for manual review
   - Alert on-call team

**Action Items:**
```bash
# Create workflow implementation
# Reference Section 5 of architecture doc for complete YAML

# Key configurations to add:
# - AWS OIDC authentication
# - Terraform version pinning
# - OPA policy validation step
# - Metadata recording step
# - Error handling and notifications
```

**Validation:**
- [ ] All jobs implemented
- [ ] Proper error handling in each job
- [ ] Dependencies between jobs correct
- [ ] Outputs passed between jobs properly

### Step 4.3: Configure GitHub Repository Secrets

**Priority:** P0 (Critical)

**Secrets Needed:**

1. **AWS_ROLE_ARN** (for drift workflow)
   - Value: ARN of `github-actions-drift-role`
   - Description: IAM role for drift remediation workflow

2. **SLACK_WEBHOOK_URL** (optional)
   - Value: Slack webhook for notifications
   - Description: Alert channel for drift events

**Action Items:**
```bash
# Add secrets via GitHub CLI
gh secret set AWS_DRIFT_ROLE_ARN --body "arn:aws:iam::ACCOUNT_ID:role/github-actions-drift-role"

# Or add via GitHub web UI:
# Settings → Secrets and variables → Actions → New repository secret
```

**Validation:**
- [ ] Secrets added to repository
- [ ] Secrets accessible in workflows (test with workflow run)
- [ ] No secret values exposed in logs

### Step 4.4: Create Deployment Metadata Recording Script

**Priority:** P1 (High)

**Purpose:** Record deployment metadata to DynamoDB after successful Terraform applies

**Script Location:** `scripts/record-deployment-metadata.py`

**Functionality:**
- Parse Terraform state file
- Extract resource ARNs
- Record deployment details to DynamoDB
- Tag resources with deployment ID

**Action Items:**
```bash
# Create script
cat > scripts/record-deployment-metadata.py << 'EOF'
#!/usr/bin/env python3
"""
Record Terraform deployment metadata to DynamoDB.
Called after successful terraform apply.
"""
import boto3
import json
import sys
from datetime import datetime

def record_metadata(deployment_id, git_sha, tfvars_path):
    # Implementation
    pass

if __name__ == "__main__":
    # Parse command-line arguments
    # Call record_metadata()
    pass
EOF

chmod +x scripts/record-deployment-metadata.py

# Test the script
python3 scripts/record-deployment-metadata.py --help
```

**Validation:**
- [ ] Script created and executable
- [ ] Can parse Terraform state
- [ ] Successfully writes to DynamoDB
- [ ] Handles errors gracefully

### Step 4.5: Test Workflow with Mock Dispatch Event

**Priority:** P0 (Critical)

**Test Method:**
```bash
# Trigger workflow manually with test payload
gh workflow run terraform-drift-controller.yml \
  -f drift_event_id="test-drift-manual-001" \
  -f git_commit_sha="$(git rev-parse HEAD)" \
  -f tfvars_path="Accounts/dev-account/dev-s3.tfvars" \
  -f deployment_id="dep-test-001"

# Monitor workflow execution
gh run watch

# Check workflow logs
gh run view --log
```

**Test Cases:**
1. ✅ Workflow triggers successfully
2. ✅ Correct commit SHA checked out
3. ✅ Terraform init succeeds
4. ✅ Terraform plan generates
5. ✅ OPA validation runs
6. ✅ Terraform apply executes (with test resources)
7. ✅ Metadata recorded to DynamoDB
8. ✅ Callback Lambda invoked

**Validation:**
- [ ] Workflow runs without errors
- [ ] All jobs complete successfully
- [ ] DynamoDB tables updated correctly
- [ ] CloudWatch metrics published
- [ ] Workflow logs are clear and informative

**Phase 4 Completion Checklist:**
- [ ] New workflow file created (not modifying existing)
- [ ] All workflow jobs implemented
- [ ] GitHub secrets configured
- [ ] Metadata recording script created
- [ ] Manual workflow test successful
- [ ] Documentation updated

---

## Phase 5: Testing & Validation

**Duration:** 4-5 days  
**Goal:** Comprehensive testing of entire system

### Step 5.1: Dev Environment Testing

**Priority:** P0 (Critical)

**Test Infrastructure Setup:**
```bash
# Create test S3 bucket with drift detection tags
terraform apply -var-file="test/drift-test.tfvars" << 'EOF'
s3_buckets = {
  "drift-test-bucket" = {
    bucket = "drift-test-bucket-dev-12345"
    versioning = { enabled = true }
    encryption = {
      sse_algorithm = "aws:kms"
      kms_master_key_id = "alias/s3"
    }
    tags = {
      ManagedBy = "terraform"
      AutoRevert = "true"
      Environment = "dev"
      TestCase = "drift-detection"
    }
  }
}
EOF

# Record deployment metadata (this should happen automatically)
python3 scripts/record-deployment-metadata.py \
  --deployment-id "test-dep-001" \
  --git-sha "$(git rev-parse HEAD)" \
  --tfvars-path "test/drift-test.tfvars"
```

**Test Scenarios:**

**Scenario 1: Manual Drift Simulation**
```bash
# Step 1: Disable encryption (simulate drift)
aws s3api delete-bucket-encryption --bucket drift-test-bucket-dev-12345

# Step 2: Manually trigger EventBridge test event
aws events put-events --entries '[{
  "Source": "aws.devops-agent",
  "DetailType": "AWS DevOps Agent - Drift Detected",
  "Detail": "{\"driftType\":\"configuration_change\",\"resourceType\":\"AWS::S3::Bucket\",\"resourceArn\":\"arn:aws:s3:::drift-test-bucket-dev-12345\",\"changedProperties\":[\"ServerSideEncryptionConfiguration\"],\"detectedBy\":\"manual_test\",\"changeAuthor\":\"test-user\",\"changeTime\":\"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'\",\"severity\":\"CRITICAL\",\"tags\":{\"ManagedBy\":\"terraform\",\"AutoRevert\":\"true\",\"Environment\":\"dev\"}}"
}]'

# Step 3: Monitor workflow execution
gh run watch

# Step 4: Verify encryption restored
aws s3api get-bucket-encryption --bucket drift-test-bucket-dev-12345

# Step 5: Check drift history
aws dynamodb get-item \
  --table-name drift-history \
  --key '{"drift_event_id": {"S": "drift-event-from-logs"}}'
```

**Expected Results:**
- ✅ Lambda orchestrator invoked within 5 seconds
- ✅ GitHub workflow triggered within 10 seconds
- ✅ Terraform plan shows encryption will be restored
- ✅ OPA validation passes
- ✅ Terraform apply succeeds
- ✅ Bucket encryption restored to original state
- ✅ MTTR recorded in DynamoDB (<2 minutes target)
- ✅ No errors in CloudWatch logs

**Scenario 2: Policy Version Conflict**
```bash
# Update OPA policy version
aws dynamodb put-item \
  --table-name policy-versions \
  --item '{
    "policy_id": {"S": "current"},
    "version": {"S": "v3.0.0"},
    "released_at": {"S": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'"},
    "changes": {"L": [{"S": "Breaking change: new encryption requirements"}]},
    "breaking_changes": {"BOOL": true}
  }'

# Trigger drift event
# ... (same as Scenario 1)

# Expected: Lambda detects version conflict, flags for manual review
```

**Scenario 3: State Lock Conflict**
```bash
# Manually acquire lock
aws dynamodb put-item \
  --table-name terraform-state-locks \
  --item '{
    "lock_id": {"S": "test-dep-001"},
    "locked_at": {"S": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'"},
    "locked_by": {"S": "manual-test"},
    "ttl": {"N": "'$(($(date +%s) + 300))'"}
  }'

# Trigger drift event
# Expected: Lambda detects lock, schedules retry
```

**Validation Checklist:**
- [ ] Scenario 1: End-to-end drift remediation successful
- [ ] Scenario 2: Policy conflict detected and handled
- [ ] Scenario 3: State lock prevents concurrent operations
- [ ] All CloudWatch metrics published correctly
- [ ] DynamoDB tables updated properly
- [ ] No permission errors
- [ ] MTTR within target (<2 minutes)

### Step 5.2: OPA Policy Testing

**Priority:** P1 (High)

**Test OPA Policies:**
```bash
# Test Vault validation policy
opa test policies/vault/ -v

# Test IAM validation policy
opa test policies/iam/ -v

# Test SCP compliance policy
opa test policies/scp/ -v

# Test KMS policy validation
opa test policies/kms/ -v
```

**Integration Testing:**
```bash
# Generate Terraform plan
terraform plan -var-file="test/drift-test.tfvars" -out=test.tfplan

# Convert to JSON
terraform show -json test.tfplan > test.tfplan.json

# Run all OPA policies
opa eval \
  --data policies/ \
  --input test.tfplan.json \
  --format pretty \
  'data.terraform.deny'

# Expected: No violations (empty result set)
```

**Validation:**
- [ ] All OPA policy tests passing
- [ ] Policies detect violations correctly
- [ ] False positives investigated and fixed
- [ ] Integration with workflow tested

### Step 5.3: Load Testing

**Priority:** P2 (Medium)

**Test Concurrent Drift Events:**
```bash
# Simulate 10 drift events within 1 minute
for i in {1..10}; do
  aws events put-events --entries "[{
    \"Source\": \"aws.devops-agent\",
    \"DetailType\": \"AWS DevOps Agent - Drift Detected\",
    \"Detail\": \"{\\\"resourceArn\\\":\\\"arn:aws:s3:::test-bucket-$i\\\"}\"
  }]" &
done
wait

# Monitor Lambda concurrency
aws lambda get-function-concurrency-config \
  --function-name drift-workflow-orchestrator-dev

# Check for throttling errors
aws logs filter-pattern --log-group-name /aws/lambda/drift-workflow-orchestrator-dev \
  --filter-pattern "Throttling"
```

**Validation:**
- [ ] Lambda handles concurrent events
- [ ] No throttling errors
- [ ] State locks prevent conflicts
- [ ] DynamoDB handles load
- [ ] GitHub workflow queue managed properly

### Step 5.4: Failure Scenario Testing

**Priority:** P1 (High)

**Test Cases:**

1. **GitHub API Failure:**
   - Remove GitHub PAT from SSM temporarily
   - Trigger drift event
   - Expected: Lambda fails gracefully, retries scheduled

2. **DynamoDB Unavailability:**
   - Temporarily remove DynamoDB permissions from Lambda role
   - Trigger drift event
   - Expected: Error logged, event dead-lettered

3. **Terraform Apply Failure:**
   - Create resource that will fail to apply
   - Trigger drift event
   - Expected: Workflow fails, issue created, on-call alerted

4. **OPA Validation Failure:**
   - Create policy violation in Terraform plan
   - Trigger drift event
   - Expected: Workflow stops before apply, issue created

**Validation:**
- [ ] All failure scenarios handled gracefully
- [ ] Appropriate alerts sent
- [ ] Error messages are clear
- [ ] No cascading failures
- [ ] System recovers automatically where possible

**Phase 5 Completion Checklist:**
- [ ] All test scenarios executed successfully
- [ ] OPA policies validated
- [ ] Load testing completed
- [ ] Failure scenarios handled properly
- [ ] Test results documented
- [ ] Issues identified and tracked

---

## Phase 6: Production Rollout

**Duration:** 3-4 days  
**Goal:** Progressive rollout to production

### Step 6.1: Create Rollout Plan

**Priority:** P0 (Critical)

**Rollout Stages:**

1. **Stage 1: Dev Environment** (Already completed in Phase 5)
   - Resources: Test S3 buckets only
   - Duration: 2 weeks
   - Success Criteria: 95% MTTR < 2 minutes

2. **Stage 2: Staging Environment**
   - Resources: Staging S3 buckets (opt-in via tags)
   - Duration: 1 week
   - Success Criteria: 98% MTTR < 2 minutes, no false positives

3. **Stage 3: Production (Limited)**
   - Resources: Non-critical production S3 buckets (opt-in)
   - Duration: 2 weeks
   - Success Criteria: 99% MTTR < 2 minutes, no incidents

4. **Stage 4: Production (Full)**
   - Resources: All production resources (opt-in recommended)
   - Duration: Ongoing
   - Success Criteria: Continuous monitoring, < 1 incident per month

**Action Items:**
```bash
# Document rollout stages
cat > docs/ROLLOUT-PLAN.md << 'EOF'
# Production Rollout Plan

## Current Stage: [To be filled]
## Last Updated: [Date]

### Stage Progress
- [x] Stage 1: Dev - Completed
- [ ] Stage 2: Staging - In Progress
- [ ] Stage 3: Production Limited
- [ ] Stage 4: Production Full

### Rollout Criteria
Each stage must meet success criteria before proceeding.
See below for details.
EOF
```

**Validation:**
- [ ] Rollout plan documented and approved
- [ ] Success criteria defined for each stage
- [ ] Rollback procedures documented
- [ ] Stakeholders informed

### Step 6.2: Deploy to Staging Environment

**Priority:** P0 (Critical)

**Pre-Deployment Checklist:**
- [ ] Lambda functions tested in dev
- [ ] DynamoDB tables exist in staging
- [ ] IAM roles created in staging
- [ ] EventBridge rules configured in staging
- [ ] GitHub workflow tested
- [ ] OPA policies validated

**Deployment Steps:**
```bash
# Switch to staging account
export AWS_PROFILE=staging

# Deploy Lambda functions
aws lambda create-function \
  --function-name drift-workflow-orchestrator \
  --runtime python3.11 \
  --role arn:aws:iam::STAGING_ACCOUNT:role/lambda-drift-orchestrator-role \
  --handler lambda_function.lambda_handler \
  --zip-file fileb://orchestrator.zip \
  --environment "Variables={METADATA_TABLE=terraform-deployment-metadata,...}"

# Configure EventBridge
aws events put-rule \
  --name devops-agent-drift-detection \
  --event-pattern '{...}'

# ... repeat for all components
```

**Initial Testing:**
```bash
# Enable drift detection on 1-2 staging buckets
terraform apply -var-file="Accounts/staging/staging-s3.tfvars"

# Add tags to enable drift detection
aws s3api put-bucket-tagging \
  --bucket staging-bucket-001 \
  --tagging 'TagSet=[{Key=ManagedBy,Value=terraform},{Key=AutoRevert,Value=true}]'

# Simulate drift
aws s3api delete-bucket-encryption --bucket staging-bucket-001

# Wait for remediation
# Monitor logs and verify restoration
```

**Validation:**
- [ ] All components deployed to staging
- [ ] Test drift event processed successfully
- [ ] No errors in logs
- [ ] Metrics show healthy operation
- [ ] MTTR within target

### Step 6.3: Enable for Non-Critical Production Resources

**Priority:** P1 (High)

**Resource Selection Criteria:**
- Start with non-critical S3 buckets (dev data, logs, archives)
- Resources with easy recovery paths
- Resources with minimal downstream dependencies
- Resources owned by teams who are early adopters

**Opt-In Process:**
```bash
# Tag resources to enable drift detection
# Teams must explicitly opt-in by adding tags

# Example: Enable for logging buckets
terraform apply << 'EOF'
resource "aws_s3_bucket" "logs" {
  bucket = "app-logs-prod"
  
  tags = {
    ManagedBy  = "terraform"
    AutoRevert = "true"        # OPT-IN to drift detection
    Environment = "production"
    CriticalityLevel = "low"
  }
}
EOF
```

**Monitoring During Rollout:**
```bash
# Create CloudWatch dashboard
aws cloudwatch put-dashboard \
  --dashboard-name DriftDetectionMetrics \
  --dashboard-body '{
    "widgets": [
      {
        "type": "metric",
        "properties": {
          "metrics": [
            ["TerraformPipeline/Drift", "MTTR"],
            [".", "RemediationSuccess"],
            [".", "DriftEventsDetected"]
          ],
          "period": 300,
          "stat": "Average",
          "region": "us-east-1",
          "title": "Drift Detection Metrics"
        }
      }
    ]
  }'

# Set up alerts for anomalies
aws cloudwatch put-metric-alarm \
  --alarm-name drift-remediation-failures \
  --metric-name RemediationSuccess \
  --namespace TerraformPipeline/Drift \
  --statistic Sum \
  --period 3600 \
  --threshold 1 \
  --comparison-operator LessThanThreshold \
  --evaluation-periods 1
```

**Validation:**
- [ ] 5-10 production resources opted in
- [ ] All drift events remediated successfully
- [ ] No false positives
- [ ] No negative impact on applications
- [ ] Monitoring dashboard shows green status

### Step 6.4: Communication and Training

**Priority:** P1 (High)

**Stakeholder Communication:**

1. **DevOps Team:**
   - Present architecture overview
   - Walkthrough of workflows and Lambda functions
   - Runbooks for troubleshooting
   - On-call procedures

2. **Development Teams:**
   - How to opt-in to drift detection
   - What to expect when drift occurs
   - How to view drift history
   - When to disable drift detection (maintenance windows)

3. **Management:**
   - Business value and ROI
   - Risk mitigation
   - Compliance benefits
   - Cost analysis

**Documentation to Create:**
```bash
# Create quick-start guide
cat > docs/DRIFT-DETECTION-QUICKSTART.md << 'EOF'
# AWS DevOps Agent Drift Detection - Quick Start

## For Development Teams

### How to Enable Drift Detection on Your Resources

1. Add tags to your Terraform resources:
   ```
   tags = {
     ManagedBy  = "terraform"
     AutoRevert = "true"
   }
   ```

2. Apply your Terraform configuration
3. Drift detection is now active!

### What Happens When Drift Occurs?

- Drift detected within seconds
- Automatic remediation triggered
- Slack notification sent to #drift-alerts
- No action required from your team

### When to Disable Drift Detection

- Planned maintenance windows
- Manual configuration testing
- Emergency hotfixes

See full documentation: docs/AWS-DEVOPS-AGENT-INTEGRATION-v2.0.md
EOF
```

**Validation:**
- [ ] All stakeholders briefed
- [ ] Training sessions completed
- [ ] Documentation published
- [ ] Feedback collected and addressed
- [ ] Support channels established

### Step 6.5: Gradual Expansion

**Priority:** P2 (Medium)

**Expansion Strategy:**
- Week 1-2: 10 non-critical production resources
- Week 3-4: 50 non-critical production resources
- Week 5-6: 100 resources including some critical ones
- Week 7+: Open to all teams (opt-in)

**Criteria for Expansion:**
- Zero critical incidents in previous period
- MTTR consistently < 2 minutes
- < 5% false positive rate
- Positive feedback from teams
- No unplanned outages related to drift detection

**Validation:**
- [ ] Expansion milestones defined
- [ ] Success metrics tracked
- [ ] Regular review meetings scheduled
- [ ] Feedback loop established

**Phase 6 Completion Checklist:**
- [ ] Rollout plan created and approved
- [ ] Staging deployment successful
- [ ] Limited production rollout completed
- [ ] Communication and training delivered
- [ ] Monitoring and alerting in place
- [ ] Ready for gradual expansion

---

## Rollback Plan

**Priority:** P0 (Critical)

### Rollback Triggers

Execute rollback if ANY of the following occur:
- ❌ More than 2 false positive drift detections in 24 hours
- ❌ MTTR exceeds 5 minutes consistently
- ❌ Any production outage caused by drift remediation
- ❌ More than 10% failure rate in remediation
- ❌ Critical security incident related to drift detection

### Rollback Procedure

**Level 1: Disable Event Processing (Immediate)**
```bash
# Disable EventBridge rule (stops new drift events)
aws events disable-rule --name devops-agent-drift-detection

# Verify rule disabled
aws events describe-rule --name devops-agent-drift-detection
```
**Impact:** No new drift events processed. Existing remediations continue.  
**Time:** < 1 minute

**Level 2: Stop Lambda Processing**
```bash
# Update Lambda to return early (no processing)
aws lambda update-function-configuration \
  --function-name drift-workflow-orchestrator \
  --environment "Variables={DISABLE_PROCESSING=true,...}"

# Or delete SNS subscription
SUBSCRIPTION_ARN=$(aws sns list-subscriptions-by-topic \
  --topic-arn arn:aws:sns:REGION:ACCOUNT:drift-detected-events \
  | jq -r '.Subscriptions[] | select(.Protocol=="lambda") | .SubscriptionArn')

aws sns unsubscribe --subscription-arn $SUBSCRIPTION_ARN
```
**Impact:** Lambda stops processing drift events.  
**Time:** < 5 minutes

**Level 3: Remove Resource Tags**
```bash
# Script to remove AutoRevert tags from all resources
cat > scripts/disable-drift-detection.sh << 'EOF'
#!/bin/bash
# Remove AutoRevert tags from all S3 buckets

for bucket in $(aws s3api list-buckets --query 'Buckets[].Name' --output text); do
  # Get current tags
  tags=$(aws s3api get-bucket-tagging --bucket $bucket 2>/dev/null)
  
  if echo "$tags" | grep -q "AutoRevert"; then
    echo "Removing AutoRevert tag from $bucket"
    # Remove AutoRevert tag (keep other tags)
    # Implementation here
  fi
done
EOF

chmod +x scripts/disable-drift-detection.sh
./scripts/disable-drift-detection.sh
```
**Impact:** Resources no longer monitored for drift.  
**Time:** 10-30 minutes depending on number of resources

**Level 4: Delete Infrastructure**
```bash
# Delete Lambda functions
aws lambda delete-function --function-name drift-workflow-orchestrator
aws lambda delete-function --function-name drift-agent-callback

# Delete EventBridge rule
aws events remove-targets --rule devops-agent-drift-detection --ids 1
aws events delete-rule --name devops-agent-drift-detection

# Delete SNS topic
aws sns delete-topic --topic-arn arn:aws:sns:REGION:ACCOUNT:drift-detected-events

# Keep DynamoDB tables for historical data (or delete if needed)
```
**Impact:** All drift detection infrastructure removed.  
**Time:** 15-30 minutes

### Rollback Validation

After rollback, verify:
- [ ] No new drift events being processed
- [ ] Lambda functions disabled or deleted
- [ ] EventBridge rule disabled or deleted
- [ ] No active remediations in progress
- [ ] Resources stable and operational
- [ ] Teams notified of rollback

### Root Cause Analysis

After rollback:
1. Collect all logs from 24 hours before incident
2. Review all drift events processed
3. Analyze failure patterns
4. Document root cause
5. Create remediation plan
6. Present findings to stakeholders

---

## Success Criteria

### Phase-Specific Criteria

**Phase 1: Infrastructure Setup**
- ✅ All DynamoDB tables created and accessible
- ✅ All IAM roles created with correct permissions
- ✅ SNS topic created and working
- ✅ SSM parameters stored securely

**Phase 2: Lambda Development**
- ✅ Both Lambda functions deployed
- ✅ Unit tests passing with >80% coverage
- ✅ Manual testing successful
- ✅ Error handling tested

**Phase 3: EventBridge Configuration**
- ✅ EventBridge rule created and enabled
- ✅ End-to-end event flow working
- ✅ No permission errors
- ✅ Timing acceptable (<5 seconds)

**Phase 4: Workflow Integration**
- ✅ New workflow file created (existing workflows untouched)
- ✅ Manual workflow test successful
- ✅ Metadata recording working
- ✅ GitHub secrets configured

**Phase 5: Testing & Validation**
- ✅ All test scenarios passed
- ✅ OPA policies validated
- ✅ Load testing successful
- ✅ Failure scenarios handled

**Phase 6: Production Rollout**
- ✅ Staging deployment successful
- ✅ Limited production rollout completed
- ✅ Training delivered
- ✅ Monitoring in place

### Overall Success Criteria

**Technical Metrics:**
- ✅ MTTR < 2 minutes for 95% of drift events
- ✅ Remediation success rate > 95%
- ✅ False positive rate < 5%
- ✅ Zero unplanned outages caused by drift detection
- ✅ Lambda cold start < 3 seconds
- ✅ End-to-end latency < 60 seconds

**Operational Metrics:**
- ✅ 90% reduction in manual drift investigation time
- ✅ 100% audit trail of all drift events
- ✅ Zero security incidents due to drift detection
- ✅ < 1 hour per week operational overhead

**Business Metrics:**
- ✅ Improved compliance posture (measurable via audits)
- ✅ Reduced risk of unauthorized changes
- ✅ Faster incident response
- ✅ Positive feedback from development teams

---

## Appendix

### A. Timeline Summary

| Phase | Duration | Dependencies |
|-------|----------|--------------|
| Phase 1: Infrastructure Setup | 3-4 days | AWS access, IAM permissions |
| Phase 2: Lambda Development | 4-5 days | Phase 1 complete |
| Phase 3: EventBridge Config | 2 days | Phase 1, 2 complete |
| Phase 4: Workflow Integration | 5-6 days | Phase 3 complete |
| Phase 5: Testing & Validation | 4-5 days | Phase 4 complete |
| Phase 6: Production Rollout | 3-4 days | Phase 5 complete |
| **Total** | **21-28 days** | Sequential execution |

### B. Resource Requirements

**AWS Resources:**
- 4 DynamoDB tables (PAY_PER_REQUEST billing)
- 2 Lambda functions (512MB + 256MB)
- 1 EventBridge rule
- 1 SNS topic
- 3 IAM roles
- 2 SSM parameters (SecureString)

**Estimated Monthly Cost:**
- DynamoDB: $5-10 (low traffic)
- Lambda: $2-5 (based on invocations)
- EventBridge: $0 (within free tier)
- SNS: $0 (within free tier)
- **Total: $7-15/month**

**Team Resources:**
- 1 DevOps Engineer (full-time, 3-4 weeks)
- 1 Cloud Architect (part-time, review/guidance)
- 1 Security Engineer (part-time, policy review)

### C. Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| False positive drift detection | Medium | Medium | Extensive testing, opt-in approach |
| Lambda throttling under load | Low | Medium | Reserved concurrency, retries |
| GitHub API rate limits | Low | Low | Token rotation, backoff strategy |
| DynamoDB throttling | Low | Low | On-demand billing mode |
| Policy version conflicts | Medium | Low | Version compatibility checks |
| Security incident (leaked tokens) | Low | High | SSM SecureString, IAM policies |
| Unintended resource deletion | Low | Critical | Read-only drift detection first |

### D. Key Contacts

**Technical Leads:**
- DevOps Lead: [Name] - [Email] - [Slack]
- Cloud Architect: [Name] - [Email] - [Slack]
- Security Lead: [Name] - [Email] - [Slack]

**Escalation Path:**
1. DevOps Team (#devops-team Slack channel)
2. DevOps Lead (PagerDuty)
3. Engineering Manager
4. VP Engineering

**Support Channels:**
- Slack: #drift-detection-support
- Email: devops-team@company.com
- Documentation: docs/AWS-DEVOPS-AGENT-INTEGRATION-v2.0.md

### E. References

- [Architecture Documentation](docs/AWS-DEVOPS-AGENT-INTEGRATION-v2.0.md)
- [AWS DevOps Agent Announcement](https://aws.amazon.com/blogs/aws/preview-amazon-q-developer-agent-for-devops/)
- [Terraform AWS Provider Docs](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)
- [GitHub Actions - repository_dispatch](https://docs.github.com/en/actions/using-workflows/events-that-trigger-workflows#repository_dispatch)
- [OPA Policy Language](https://www.openpolicyagent.org/docs/latest/policy-language/)

---

**END OF IMPLEMENTATION PLAN**
