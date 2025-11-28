#!/usr/bin/env python3
"""
Test script for the enhanced terraform deployment orchestrator
Tests service detection and dynamic backend key generation
"""
import sys
import json
from pathlib import Path

# Add the scripts directory to Python path
script_dir = Path(__file__).parent.absolute()
sys.path.insert(0, str(script_dir))

from terraform_deployment_orchestrator_copy import TerraformOrchestrator

def test_service_detection():
    """Test service detection from tfvars files"""
    print("🧪 Testing Service Detection")
    print("="*50)
    
    # Create test orchestrator
    orchestrator = TerraformOrchestrator(Path.cwd())
    
    # Test cases for service detection
    test_cases = [
        {
            "name": "Lambda function",
            "content": '''
project = "my-lambda-app"
lambda_function_name = "test-function"
lambda_runtime = "python3.9"
''',
            "expected_services": ["lambda"]
        },
        {
            "name": "SQS and SNS",
            "content": '''
project = "messaging-system"
sqs_queue_name = "processing-queue"
sns_topic_name = "notifications"
''',
            "expected_services": ["sqs", "sns"]
        },
        {
            "name": "Multi-service with EC2 and S3",
            "content": '''
project = "web-application"
ec2_instance_type = "t3.micro"
s3_bucket_name = "my-app-storage"
iam_role_name = "web-app-role"
''',
            "expected_services": ["ec2", "s3", "iam"]
        },
        {
            "name": "No recognized services",
            "content": '''
project = "basic-config"
environment = "dev"
region = "us-east-1"
''',
            "expected_services": []
        }
    ]
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n📝 Test {i}: {test_case['name']}")
        
        # Create temporary tfvars file
        test_file = script_dir / f"test-{i}.tfvars"
        test_file.write_text(test_case['content'])
        
        try:
            # Test service detection
            detected_services = orchestrator._detect_services_from_tfvars(test_file)
            
            print(f"   Expected: {test_case['expected_services']}")
            print(f"   Detected: {detected_services}")
            
            # Check if detection is correct
            if set(detected_services) == set(test_case['expected_services']):
                print("   ✅ PASS")
            else:
                print("   ❌ FAIL")
            
            # Test backend key generation
            backend_key = orchestrator._generate_dynamic_backend_key(
                account_name="test-account",
                region="us-east-1", 
                project="test-project",
                services=detected_services
            )
            print(f"   Backend Key: {backend_key}")
            
        finally:
            # Clean up test file
            if test_file.exists():
                test_file.unlink()
    
    print("\n" + "="*50)

def test_output_extraction():
    """Test terraform output extraction"""
    print("\n🔍 Testing Output Extraction")
    print("="*50)
    
    orchestrator = TerraformOrchestrator(Path.cwd())
    
    # Mock terraform output
    mock_output = '''
Plan: 3 to add, 1 to change, 0 to destroy.

Terraform will perform the following actions:

  # aws_lambda_function.main will be created
  + resource "aws_lambda_function" "main" {
      + arn                            = (known after apply)
      + function_name                  = "my-lambda-function"
    }

  # aws_s3_bucket.storage will be created
  + resource "aws_s3_bucket" "storage" {
      + arn                         = (known after apply)
      + bucket                      = "my-app-storage-bucket"
    }

  # aws_iam_role.lambda_role will be updated in-place
  ~ resource "aws_iam_role" "lambda_role" {
      + name                        = "my-lambda-role"
    }

Changes to Outputs:
  + lambda_arn = "arn:aws:lambda:us-east-1:123456789012:function:my-lambda-function"
  + s3_bucket_name = "my-app-storage-bucket"
'''
    
    # Test output extraction
    outputs = orchestrator._extract_terraform_outputs(mock_output)
    
    print("📊 Extracted Resources:")
    print(f"  Created: {outputs['resources_created']}")
    print(f"  Modified: {outputs['resources_modified']}")
    print(f"  Destroyed: {outputs['resources_destroyed']}")
    
    print("📋 Resource Details:")
    for service, details in outputs['resource_details'].items():
        print(f"  {service.upper()}:")
        if details['arns']:
            print(f"    ARNs: {details['arns']}")
        if details['names']:
            print(f"    Names: {details['names']}")
        if details['ids']:
            print(f"    IDs: {details['ids']}")

def test_pr_comment_generation():
    """Test enhanced PR comment generation"""
    print("\n💬 Testing PR Comment Generation")
    print("="*50)
    
    orchestrator = TerraformOrchestrator(Path.cwd())
    
    # Mock deployment and result data
    mock_deployment = {
        'account_name': 'test-account',
        'region': 'us-east-1',
        'project': 'lambda-app'
    }
    
    mock_result = {
        'success': True,
        'output': '''Plan: 2 to add, 0 to change, 0 to destroy.
        
aws_lambda_function.main will be created
+ resource "aws_lambda_function" "main" {
  + function_name = "my-test-function"
  + arn = (known after apply)
}

aws_s3_bucket.storage will be created
+ resource "aws_s3_bucket" "storage" {
  + bucket = "my-test-storage"
}
''',
        'backend_key': 's3/test-account/us-east-1/lambda-app/lambda/terraform.tfstate',
        'action': 'plan',
        'terraform_outputs': {
            'resources_created': ['aws_lambda_function.main', 'aws_s3_bucket.storage'],
            'resources_modified': [],
            'resources_destroyed': [],
            'resource_details': {
                'lambda': {
                    'names': ['my-test-function'],
                    'arns': ['arn:aws:lambda:us-east-1:123456:function:my-test-function'],
                    'ids': []
                },
                's3': {
                    'names': ['my-test-storage'],
                    'arns': ['arn:aws:s3:::my-test-storage'],
                    'ids': []
                }
            }
        }
    }
    
    services = ['lambda', 's3']
    
    # Generate PR comment
    pr_comment = orchestrator._generate_enhanced_pr_comment(
        mock_deployment, mock_result, services
    )
    
    print("📝 Generated PR Comment:")
    print("-" * 50)
    print(pr_comment)
    print("-" * 50)

if __name__ == "__main__":
    print("🚀 Enhanced Terraform Orchestrator Test Suite")
    print("=" * 60)
    
    test_service_detection()
    test_output_extraction()
    test_pr_comment_generation()
    
    print("\n✅ Test suite completed!")