"""
Custom Checkov Policy: Ensure Terraform Resources Follow Company Naming Convention
"""
from checkov.common.models.enums import TrueResult, FalseResult
from checkov.terraform.checks.resource.base_resource_check import BaseResourceCheck
import re

class CompanyNamingConvention(BaseResourceCheck):
    def __init__(self):
        name = "Ensure resources follow company naming convention"
        id = "CKV_COMPANY_001"
        supported_resources = ['aws_instance', 'aws_s3_bucket', 'aws_db_instance', 
                              'aws_lambda_function', 'aws_ecs_service']
        categories = ['CONVENTION']
        super().__init__(name=name, id=id, categories=categories, supported_resources=supported_resources)

    def scan_resource_conf(self, conf):
        """
        Looks for naming convention in resource names
        Expected format: {environment}-{application}-{component}-{identifier}
        Example: prod-web-api-01, dev-db-primary, test-lambda-processor
        """
        
        # Get resource name from different possible configurations
        resource_name = None
        
        # Try to get name from various common attributes
        if 'name' in conf:
            resource_name = conf['name'][0] if isinstance(conf['name'], list) else conf['name']
        elif 'function_name' in conf:  # For Lambda
            resource_name = conf['function_name'][0] if isinstance(conf['function_name'], list) else conf['function_name']
        elif 'bucket' in conf:  # For S3
            resource_name = conf['bucket'][0] if isinstance(conf['bucket'], list) else conf['bucket']
        elif 'db_name' in conf:  # For RDS
            resource_name = conf['db_name'][0] if isinstance(conf['db_name'], list) else conf['db_name']
        
        if not resource_name:
            return FalseResult
        
        # Skip if resource name is a variable reference
        if str(resource_name).startswith('${') or str(resource_name).startswith('var.'):
            return TrueResult  # Skip variable references
            
        # Define naming convention pattern
        # Format: {env}-{app}-{component}-{id}
        # env: dev, test, stage, prod
        # app: 3-10 lowercase letters
        # component: 2-15 lowercase letters/numbers
        # id: 1-10 alphanumeric
        pattern = r'^(dev|test|stage|prod)-[a-z]{3,10}-[a-z0-9]{2,15}-[a-z0-9]{1,10}$'
        
        if re.match(pattern, str(resource_name).lower()):
            return TrueResult
        else:
            return FalseResult

check = CompanyNamingConvention()