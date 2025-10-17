#!/usr/bin/env python3
"""
KMS Repository Integration Script
This script handles cloning/updating KMS repository with JSON configurations
"""

import os
import json
import subprocess
import sys
from datetime import datetime
from typing import Dict, Any
import tempfile
import shutil

class KMSRepositoryManager:
    def __init__(self, kms_repo_url: str, github_token: str = ""):
        self.kms_repo_url = kms_repo_url
        self.github_token = github_token
        self.temp_dir = None
        
    def clone_or_update_repo(self) -> str:
        """Clone or update KMS repository"""
        self.temp_dir = tempfile.mkdtemp(prefix="kms_repo_")
        
        try:
            # Clone the repository
            if self.github_token:
                auth_url = self.kms_repo_url.replace("https://", f"https://{self.github_token}@")
                clone_cmd = ["git", "clone", auth_url, self.temp_dir]
            else:
                clone_cmd = ["git", "clone", self.kms_repo_url, self.temp_dir]
            
            result = subprocess.run(clone_cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise Exception(f"Failed to clone repository: {result.stderr}")
            
            print(f"✅ Successfully cloned KMS repository to {self.temp_dir}")
            return self.temp_dir
            
        except Exception as e:
            if self.temp_dir and os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
            raise e
    
    def update_kms_configuration(self, config_data: Dict[str, Any], file_path: str = "kms-config.json"):
        """Update KMS configuration in the repository"""
        if not self.temp_dir:
            raise Exception("Repository not cloned. Call clone_or_update_repo first.")
        
        config_file_path = os.path.join(self.temp_dir, file_path)
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(config_file_path), exist_ok=True)
        
        # Read existing configuration if it exists
        existing_config = {}
        if os.path.exists(config_file_path):
            with open(config_file_path, 'r') as f:
                existing_config = json.load(f)
        
        # Merge configurations
        updated_config = {**existing_config, **config_data}
        updated_config['last_updated'] = datetime.now().isoformat()
        
        # Write updated configuration
        with open(config_file_path, 'w') as f:
            json.dump(updated_config, f, indent=2)
        
        print(f"✅ Updated KMS configuration in {file_path}")
        
    def create_iam_role_policy(self, role_name: str, kms_key_id: str, s3_bucket_arns: list):
        """Create IAM role policy for KMS and S3 access"""
        policy_document = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "KMSAccess",
                    "Effect": "Allow",
                    "Action": [
                        "kms:Decrypt",
                        "kms:GenerateDataKey",
                        "kms:CreateGrant",
                        "kms:DescribeKey",
                        "kms:ReEncrypt*"
                    ],
                    "Resource": f"arn:aws:kms:*:*:key/{kms_key_id}"
                },
                {
                    "Sid": "S3Access",
                    "Effect": "Allow",
                    "Action": [
                        "s3:GetObject",
                        "s3:PutObject",
                        "s3:DeleteObject",
                        "s3:ListBucket",
                        "s3:GetObjectVersion",
                        "s3:PutObjectAcl",
                        "s3:GetObjectAcl"
                    ],
                    "Resource": s3_bucket_arns + [f"{arn}/*" for arn in s3_bucket_arns]
                }
            ]
        }
        
        # Create IAM policies directory
        iam_dir = os.path.join(self.temp_dir, "iam", "policies")
        os.makedirs(iam_dir, exist_ok=True)
        
        # Write policy file
        policy_file = os.path.join(iam_dir, f"{role_name}-kms-s3-policy.json")
        with open(policy_file, 'w') as f:
            json.dump(policy_document, f, indent=2)
        
        print(f"✅ Created IAM policy: {policy_file}")
        return policy_file
    
    def create_kms_key_policy_update(self, kms_key_id: str, iam_role_arn: str, account_id: str):
        """Create KMS key policy update configuration"""
        kms_dir = os.path.join(self.temp_dir, "kms", "policies")
        os.makedirs(kms_dir, exist_ok=True)
        
        policy_update = {
            "key_id": kms_key_id,
            "policy_document": {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Sid": "Enable IAM User Permissions",
                        "Effect": "Allow",
                        "Principal": {
                            "AWS": f"arn:aws:iam::{account_id}:root"
                        },
                        "Action": "kms:*",
                        "Resource": "*"
                    },
                    {
                        "Sid": "Allow S3 Service",
                        "Effect": "Allow",
                        "Principal": {
                            "Service": "s3.amazonaws.com"
                        },
                        "Action": [
                            "kms:Decrypt",
                            "kms:GenerateDataKey"
                        ],
                        "Resource": "*"
                    },
                    {
                        "Sid": "Allow application role",
                        "Effect": "Allow",
                        "Principal": {
                            "AWS": iam_role_arn
                        },
                        "Action": [
                            "kms:Decrypt",
                            "kms:GenerateDataKey",
                            "kms:CreateGrant",
                            "kms:DescribeKey",
                            "kms:ReEncrypt*"
                        ],
                        "Resource": "*"
                    }
                ]
            },
            "created_at": datetime.now().isoformat(),
            "created_for": "s3-deployment-integration"
        }
        
        policy_file = os.path.join(kms_dir, f"{kms_key_id}-s3-policy.json")
        with open(policy_file, 'w') as f:
            json.dump(policy_update, f, indent=2)
        
        print(f"✅ Created KMS policy update: {policy_file}")
        return policy_file
    
    def commit_and_push_changes(self, commit_message: str, branch_name: str = "main"):
        """Commit and push changes to repository"""
        if not self.temp_dir:
            raise Exception("Repository not cloned. Call clone_or_update_repo first.")
        
        os.chdir(self.temp_dir)
        
        try:
            # Configure git user (if not already configured)
            subprocess.run(["git", "config", "user.name", "Terraform Automation"], 
                         capture_output=True, text=True)
            subprocess.run(["git", "config", "user.email", "terraform@automation.com"], 
                         capture_output=True, text=True)
            
            # Add all changes
            subprocess.run(["git", "add", "."], check=True)
            
            # Check if there are changes to commit
            result = subprocess.run(["git", "diff", "--cached", "--quiet"], capture_output=True)
            if result.returncode == 0:
                print("ℹ️  No changes to commit")
                return
            
            # Commit changes
            subprocess.run(["git", "commit", "-m", commit_message], check=True)
            
            # Push changes
            if self.github_token:
                # Set up authentication for push
                auth_url = self.kms_repo_url.replace("https://", f"https://{self.github_token}@")
                subprocess.run(["git", "remote", "set-url", "origin", auth_url], check=True)
            
            subprocess.run(["git", "push", "origin", branch_name], check=True)
            
            print(f"✅ Successfully pushed changes to {branch_name}")
            
        except subprocess.CalledProcessError as e:
            print(f"❌ Error during git operations: {e}")
            raise
    
    def dispatch_repository_event(self, event_type: str = "kms-config-updated", payload: Dict[str, Any] = None):
        """Dispatch repository event (GitHub Actions trigger)"""
        if not self.github_token:
            print("⚠️  No GitHub token provided, skipping repository dispatch")
            return
        
        # Extract owner and repo from URL
        repo_parts = self.kms_repo_url.replace("https://github.com/", "").replace(".git", "").split("/")
        if len(repo_parts) != 2:
            print("❌ Invalid repository URL format")
            return
        
        owner, repo = repo_parts
        
        # Prepare dispatch payload
        dispatch_data = {
            "event_type": event_type,
            "client_payload": payload or {
                "timestamp": datetime.now().isoformat(),
                "triggered_by": "s3-deployment-automation"
            }
        }
        
        # Make API call to trigger repository dispatch
        import urllib.request
        import urllib.parse
        
        url = f"https://api.github.com/repos/{owner}/{repo}/dispatches"
        headers = {
            "Authorization": f"token {self.github_token}",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json"
        }
        
        try:
            data = json.dumps(dispatch_data).encode('utf-8')
            request = urllib.request.Request(url, data=data, headers=headers, method='POST')
            
            with urllib.request.urlopen(request) as response:
                if response.status == 204:
                    print(f"✅ Successfully dispatched {event_type} event")
                else:
                    print(f"⚠️  Dispatch response: {response.status}")
                    
        except Exception as e:
            print(f"❌ Error dispatching repository event: {e}")
    
    def cleanup(self):
        """Clean up temporary directory"""
        if self.temp_dir and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
            print(f"🧹 Cleaned up temporary directory: {self.temp_dir}")

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='KMS Repository Integration Manager')
    parser.add_argument('--kms-repo-url', required=True, help='KMS repository URL')
    parser.add_argument('--github-token', help='GitHub token for authentication')
    parser.add_argument('--kms-key-id', required=True, help='KMS key ID')
    parser.add_argument('--iam-role-name', required=True, help='IAM role name')
    parser.add_argument('--iam-role-arn', required=True, help='IAM role ARN')
    parser.add_argument('--account-id', required=True, help='AWS account ID')
    parser.add_argument('--s3-buckets', required=True, help='Comma-separated S3 bucket ARNs')
    parser.add_argument('--commit-message', default='Update KMS configuration for S3 deployment', 
                       help='Git commit message')
    parser.add_argument('--dispatch-event', action='store_true', 
                       help='Dispatch repository event after update')
    
    args = parser.parse_args()
    
    # Parse S3 bucket ARNs
    s3_bucket_arns = [arn.strip() for arn in args.s3_buckets.split(',')]
    
    # Initialize KMS repository manager
    kms_manager = KMSRepositoryManager(
        kms_repo_url=args.kms_repo_url,
        github_token=args.github_token or os.environ.get('GITHUB_TOKEN', '')
    )
    
    try:
        # Clone/update repository
        repo_path = kms_manager.clone_or_update_repo()
        
        # Update KMS configuration
        config_data = {
            "kms_key_id": args.kms_key_id,
            "iam_role_name": args.iam_role_name,
            "iam_role_arn": args.iam_role_arn,
            "account_id": args.account_id,
            "s3_buckets": s3_bucket_arns,
            "integration_type": "s3-deployment"
        }
        
        kms_manager.update_kms_configuration(config_data)
        
        # Create IAM role policy
        kms_manager.create_iam_role_policy(
            role_name=args.iam_role_name,
            kms_key_id=args.kms_key_id,
            s3_bucket_arns=s3_bucket_arns
        )
        
        # Create KMS key policy update
        kms_manager.create_kms_key_policy_update(
            kms_key_id=args.kms_key_id,
            iam_role_arn=args.iam_role_arn,
            account_id=args.account_id
        )
        
        # Commit and push changes
        kms_manager.commit_and_push_changes(args.commit_message)
        
        # Dispatch event if requested
        if args.dispatch_event:
            kms_manager.dispatch_repository_event(
                event_type="kms-config-updated",
                payload={
                    "kms_key_id": args.kms_key_id,
                    "iam_role_name": args.iam_role_name,
                    "s3_bucket_count": len(s3_bucket_arns)
                }
            )
        
        print("🚀 KMS repository integration completed successfully!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)
    finally:
        kms_manager.cleanup()

if __name__ == "__main__":
    main()