"""
Custom Checkov Policy: Ensure all resources have required tags
"""
from checkov.common.models.enums import TrueResult, FalseResult
from checkov.terraform.checks.resource.base_resource_check import BaseResourceCheck

class RequiredTags(BaseResourceCheck):
    def __init__(self):
        name = "Ensure all resources have required company tags"
        id = "CKV_COMPANY_002"
        supported_resources = ['aws_instance', 'aws_s3_bucket', 'aws_db_instance', 
                              'aws_lambda_function', 'aws_ecs_service', 'aws_vpc',
                              'aws_subnet', 'aws_security_group', 'aws_lb']
        categories = ['TAGGING']
        super().__init__(name=name, id=id, categories=categories, supported_resources=supported_resources)

    def scan_resource_conf(self, conf):
        """
        Checks if resource has all required tags
        Required tags: Environment, Application, Owner, CostCenter
        """
        
        # Required tags for company compliance
        required_tags = [
            'Environment',  # dev, test, stage, prod
            'Application',  # Application name
            'Owner',       # Team or person responsible
            'CostCenter'   # Billing/cost allocation
        ]
        
        # Get tags from configuration
        tags = conf.get('tags')
        if not tags:
            return FalseResult
            
        # Tags can be a list or dict, handle both cases
        if isinstance(tags, list):
            if len(tags) > 0:
                tags = tags[0]
            else:
                return FalseResult
                
        if not isinstance(tags, dict):
            return FalseResult
            
        # Check if all required tags are present
        for required_tag in required_tags:
            if required_tag not in tags:
                return FalseResult
                
        # Additional validation for Environment tag values
        env_tag = tags.get('Environment', '')
        valid_environments = ['dev', 'test', 'stage', 'prod', 'development', 'testing', 'staging', 'production']
        
        if isinstance(env_tag, list):
            env_tag = env_tag[0] if len(env_tag) > 0 else ''
            
        if str(env_tag).lower() not in valid_environments:
            return FalseResult
            
        return TrueResult

check = RequiredTags()