#!/usr/bin/env python3
"""
ArgoCD Terraform Generator
Converts Terraform configurations to Kubernetes Job manifests for ArgoCD
"""
import json
import yaml
import os
import sys
from pathlib import Path

class ArgoCDTerraformGenerator:
    def __init__(self, deployments_file, output_dir):
        self.deployments_file = deployments_file
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
    def generate_terraform_jobs(self):
        """Generate Kubernetes Job manifests for Terraform deployments"""
        
        with open(self.deployments_file, 'r') as f:
            deployments = json.load(f)
        
        manifests = []
        
        for deployment in deployments.get('deployments', []):
            # Generate plan job
            plan_job = self.create_terraform_job(
                deployment, 
                operation='plan',
                job_type='plan'
            )
            manifests.append(plan_job)
            
            # Generate apply job (depends on plan)
            apply_job = self.create_terraform_job(
                deployment,
                operation='apply', 
                job_type='apply',
                depends_on=f"terraform-plan-{deployment['account']}"
            )
            manifests.append(apply_job)
        
        # Write manifests to files
        for i, manifest in enumerate(manifests):
            filename = f"{manifest['metadata']['name']}.yaml"
            with open(self.output_dir / filename, 'w') as f:
                yaml.dump(manifest, f, default_flow_style=False)
        
        print(f"✅ Generated {len(manifests)} Terraform job manifests")
        return manifests
    
    def create_terraform_job(self, deployment, operation, job_type, depends_on=None):
        """Create a Kubernetes Job for Terraform operation"""
        
        job_name = f"terraform-{job_type}-{deployment['account']}"
        
        job_manifest = {
            'apiVersion': 'batch/v1',
            'kind': 'Job',
            'metadata': {
                'name': job_name,
                'namespace': 'terraform-deployments',
                'labels': {
                    'app': 'terraform-controller',
                    'account': deployment['account'],
                    'operation': operation,
                    'managed-by': 'argocd'
                },
                'annotations': {
                    'argocd.argoproj.io/hook': 'Sync',
                    'argocd.argoproj.io/hook-delete-policy': 'BeforeHookCreation'
                }
            },
            'spec': {
                'template': {
                    'metadata': {
                        'labels': {
                            'app': 'terraform-controller',
                            'account': deployment['account'],
                            'operation': operation
                        }
                    },
                    'spec': {
                        'serviceAccountName': 'terraform-controller',
                        'containers': [{
                            'name': 'terraform',
                            'image': 'terraform-enterprise:latest',
                            'command': ['/opt/terraform-scripts/terraform-executor.sh'],
                            'args': [
                                '--operation', operation,
                                '--account', deployment['account'],
                                '--tfvars-file', deployment['tfvars_file'],
                                '--deployment-id', deployment['deployment_id']
                            ],
                            'env': [
                                {'name': 'AWS_REGION', 'value': 'us-east-1'},
                                {'name': 'TERRAFORM_VERSION', 'value': '1.11.0'},
                                {'name': 'OPA_VERSION', 'value': '0.59.0'},
                                {
                                    'name': 'AWS_ROLE_ARN',
                                    'valueFrom': {
                                        'secretKeyRef': {
                                            'name': 'terraform-secrets',
                                            'key': 'aws-role-arn'
                                        }
                                    }
                                },
                                {
                                    'name': 'GITHUB_TOKEN',
                                    'valueFrom': {
                                        'secretKeyRef': {
                                            'name': 'terraform-secrets', 
                                            'key': 'github-token'
                                        }
                                    }
                                }
                            ],
                            'resources': {
                                'requests': {
                                    'cpu': '500m',
                                    'memory': '1Gi'
                                },
                                'limits': {
                                    'cpu': '2',
                                    'memory': '4Gi'
                                }
                            },
                            'volumeMounts': [
                                {
                                    'name': 'terraform-config',
                                    'mountPath': '/opt/terraform-config'
                                },
                                {
                                    'name': 'terraform-state',
                                    'mountPath': '/opt/terraform-state'
                                }
                            ]
                        }],
                        'volumes': [
                            {
                                'name': 'terraform-config',
                                'configMap': {
                                    'name': 'terraform-controller-config'
                                }
                            },
                            {
                                'name': 'terraform-state',
                                'persistentVolumeClaim': {
                                    'claimName': 'terraform-state-pvc'
                                }
                            }
                        ],
                        'restartPolicy': 'Never'
                    }
                },
                'backoffLimit': 3,
                'ttlSecondsAfterFinished': 86400  # 24 hours
            }
        }
        
        # Add dependency annotation for apply jobs
        if depends_on:
            job_manifest['metadata']['annotations']['argocd.argoproj.io/sync-wave'] = '1'
        
        return job_manifest

    def create_opa_validation_job(self, deployment):
        """Create OPA validation job"""
        
        return {
            'apiVersion': 'batch/v1',
            'kind': 'Job',
            'metadata': {
                'name': f"opa-validation-{deployment['account']}",
                'namespace': 'terraform-deployments',
                'annotations': {
                    'argocd.argoproj.io/hook': 'PreSync',
                    'argocd.argoproj.io/hook-delete-policy': 'BeforeHookCreation'
                }
            },
            'spec': {
                'template': {
                    'spec': {
                        'containers': [{
                            'name': 'opa-validator',
                            'image': 'openpolicyagent/opa:0.59.0-envoy',
                            'command': ['/bin/sh'],
                            'args': ['-c', '''
                                echo "🛡️ Running OPA validation for {account}..."
                                
                                # Download policies
                                git clone https://github.com/Terraform-centilazed-pipline/OPA-Policies.git /opa-policies
                                
                                # Run validation
                                opa eval -d /opa-policies/terraform/ \\
                                  -i /terraform-plan/plan.json \\
                                  "data.terraform.main.deny" \\
                                  --format pretty
                                
                                # Check for violations
                                violations=$(opa eval -d /opa-policies/terraform/ \\
                                  -i /terraform-plan/plan.json \\
                                  "data.terraform.main.deny" \\
                                  --format json | jq '.result[0].expressions[0].value | length')
                                
                                if [ "$violations" -gt 0 ]; then
                                  echo "❌ OPA validation failed: $violations violations found"
                                  exit 1
                                else
                                  echo "✅ OPA validation passed"
                                fi
                            '''.format(account=deployment['account'])],
                            'volumeMounts': [
                                {
                                    'name': 'terraform-plan',
                                    'mountPath': '/terraform-plan'
                                }
                            ]
                        }],
                        'volumes': [
                            {
                                'name': 'terraform-plan',
                                'emptyDir': {}
                            }
                        ],
                        'restartPolicy': 'Never'
                    }
                }
            }
        }

def main():
    if len(sys.argv) != 3:
        print("Usage: python3 argocd-terraform-generator.py <deployments.json> <output-dir>")
        sys.exit(1)
    
    deployments_file = sys.argv[1]
    output_dir = sys.argv[2]
    
    generator = ArgoCDTerraformGenerator(deployments_file, output_dir)
    generator.generate_terraform_jobs()

if __name__ == "__main__":
    main()