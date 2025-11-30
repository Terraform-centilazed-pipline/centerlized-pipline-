#!/usr/bin/env python3
"""
Handle PR approval and merge with OPA validation
Supports special approver override for OPA failures
"""

import os
import sys
import json
import yaml
from github import Github
from datetime import datetime

def load_special_approvers():
    """Load special approvers from config file"""
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'special-approvers.yaml')
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
            return config.get('special_approvers', ['pragadeeswarpa'])
    except Exception as e:
        print(f"⚠️ Could not load special approvers config: {e}")
        print("Using default: ['pragadeeswarpa']")
        return ['pragadeeswarpa']

# Configuration
SPECIAL_APPROVERS = load_special_approvers()

def get_pr_approvals(repo, pr_number):
    """Get list of approvers for a PR"""
    pr = repo.get_pull(pr_number)
    reviews = pr.get_reviews()
    
    approved_by = []
    for review in reviews:
        if review.state == 'APPROVED':
            approved_by.append(review.user.login)
    
    return list(set(approved_by))  # Remove duplicates

def build_commit_message(pr, approver, workflow_url):
    """Build dynamic commit message with audit trail"""
    files_changed = list(pr.get_files())
    file_list = '\n'.join([f"  - {f.filename}" for f in files_changed[:10]])
    more_files = f"\n  ... and {len(files_changed) - 10} more files" if len(files_changed) > 10 else ""
    
    message = f"""Merged after approval and OPA validation

PR #{pr.number}: {pr.title}
Author: {pr.user.login}
Approved-by: {approver}
Branch: {pr.head.ref} to {pr.base.ref}

Files changed ({len(files_changed)}):
{file_list}{more_files}

OPA: PASSED
Workflow: {workflow_url}
PR Link: {pr.html_url}
Merged at: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"""
    
    return message

def handle_opa_passed(repo, pr_number, workflow_url):
    """Handle PR when OPA validation passed"""
    pr = repo.get_pull(pr_number)
    
    # Check for approval
    approvers = get_pr_approvals(repo, pr_number)
    
    if not approvers:
        print("⏳ No approval yet - waiting")
        pr.create_issue_comment(
            "✅ **OPA Passed** - Waiting for PR approval before merge.\n\n"
            "Please review and approve this PR to trigger automatic merge."
        )
        return {"merged": False, "reason": "awaiting_approval"}
    
    approver = approvers[0]  # Use first approver
    print(f"✅ Approved by: {approver} - proceeding with merge")
    
    # Add labels
    pr.add_to_labels('opa-passed', 'ready-to-merge')
    
    # Build commit message
    commit_msg = build_commit_message(pr, approver, workflow_url)
    commit_title = f"[Terraform] {pr.title}"
    
    # Merge PR
    merge_result = pr.merge(
        commit_title=commit_title,
        commit_message=commit_msg,
        merge_method='squash'
    )
    
    if merge_result.merged:
        print(f"✅ PR merged successfully - SHA: {merge_result.sha}")
        
        # Success comment
        pr.create_issue_comment(
            f"✅ **PR Auto-Merged!**\n\n"
            f"🛡️ OPA validation passed - all security policies compliant\n"
            f"👤 Approved by: @{approver}\n"
            f"🔀 Changes merged to `{pr.base.ref}`\n"
            f"🚀 Terraform apply will begin automatically...\n\n"
            f"**Merge SHA**: `{merge_result.sha}`"
        )
        
        return {
            "merged": True,
            "sha": merge_result.sha,
            "approver": approver
        }
    else:
        print(f"❌ Merge failed: {merge_result.message}")
        return {"merged": False, "reason": merge_result.message}

def handle_opa_failed(repo, pr_number, workflow_url):
    """Handle PR when OPA validation failed - block unless special approver overrides"""
    pr = repo.get_pull(pr_number)
    
    # Check for special approver
    approvers = get_pr_approvals(repo, pr_number)
    special_approver = None
    
    for approver in approvers:
        if approver in SPECIAL_APPROVERS:
            special_approver = approver
            break
    
    if not special_approver:
        print("🚫 OPA failed - blocking all merges (no special approver)")
        
        # Add blocking labels
        pr.add_to_labels('opa-failed', 'blocked', 'requires-special-approval')
        
        # Block comment
        pr.create_issue_comment(
            "🚫 **OPA Validation FAILED - PR Blocked**\n\n"
            "❌ Critical security policy violations detected\n"
            "🔒 This PR cannot be merged (auto or manual) until:\n\n"
            "**Option 1 (Recommended)**: Fix the violations and push changes\n"
            "**Option 2**: Request special approval from: " + ", ".join([f"`@{a}`" for a in SPECIAL_APPROVERS]) + "\n\n"
            "⚠️ Only special approvers can override OPA failures with proper justification."
        )
        
        return {"merged": False, "blocked": True, "reason": "opa_failed_no_override"}
    
    # Special approver override
    print(f"⚠️ OPA failed but special approver @{special_approver} approved - checking for justification")
    
    # Check if override comment exists
    comments = pr.get_issue_comments()
    has_justification = False
    
    for comment in comments:
        if comment.user.login == special_approver and 'override' in comment.body.lower():
            has_justification = True
            break
    
    if not has_justification:
        pr.create_issue_comment(
            f"⚠️ **Special Approval Detected**\n\n"
            f"@{special_approver}, you have special approval privileges.\n\n"
            f"To override OPA failure, please comment with:\n"
            f"- Justification for override\n"
            f"- Risk assessment\n"
            f"- Include the word 'OVERRIDE' in your comment\n\n"
            f"Example:\n"
            f"```\n"
            f"OVERRIDE: Emergency production fix required.\n"
            f"Risk: Low - temporary workaround, will fix in next sprint.\n"
            f"```"
        )
        return {"merged": False, "reason": "awaiting_override_justification"}
    
    # Override approved - proceed with merge
    print(f"✅ Override justified by @{special_approver} - proceeding with merge")
    
    pr.add_to_labels('opa-override', 'special-approval')
    
    commit_msg = build_commit_message(pr, special_approver, workflow_url)
    commit_msg += f"\n\n⚠️ OPA OVERRIDE by @{special_approver}"
    commit_title = f"[Terraform][OVERRIDE] {pr.title}"
    
    merge_result = pr.merge(
        commit_title=commit_title,
        commit_message=commit_msg,
        merge_method='squash'
    )
    
    if merge_result.merged:
        pr.create_issue_comment(
            f"⚠️ **PR Merged with OPA Override**\n\n"
            f"👤 Special approval by: @{special_approver}\n"
            f"🔀 Changes merged to `{pr.base.ref}`\n"
            f"**Merge SHA**: `{merge_result.sha}`\n\n"
            f"🚨 This merge bypassed OPA validation - ensure compliance review."
        )
        
        return {
            "merged": True,
            "sha": merge_result.sha,
            "override": True,
            "approver": special_approver
        }
    
    return {"merged": False, "reason": merge_result.message}

def get_opa_status_from_pr(repo, pr_number):
    """Get OPA validation status from PR labels"""
    pr = repo.get_pull(pr_number)
    labels = [label.name for label in pr.labels]
    
    print(f"PR Labels: {', '.join(labels)}")
    
    if 'opa-passed' in labels:
        return 'passed'
    elif 'opa-failed' in labels:
        return 'failed'
    else:
        return 'unknown'

def main():
    # Get inputs from environment
    github_token = os.environ.get('GITHUB_TOKEN')
    source_owner = os.environ.get('SOURCE_OWNER')
    source_repo = os.environ.get('SOURCE_REPO')
    pr_number = int(os.environ.get('PR_NUMBER'))
    workflow_url = os.environ.get('WORKFLOW_URL')
    github_output = os.environ.get('GITHUB_OUTPUT')
    approver = os.environ.get('APPROVER')
    
    if not all([github_token, source_owner, source_repo, pr_number]):
        print("❌ Missing required environment variables")
        sys.exit(1)
    
    # Initialize GitHub client
    g = Github(github_token)
    repo = g.get_repo(f"{source_owner}/{source_repo}")
    
    print(f"Processing PR #{pr_number} from approval by @{approver}")
    
    # Get OPA status from PR labels (set during validation run)
    validation_status = get_opa_status_from_pr(repo, pr_number)
    print(f"OPA Status (from labels): {validation_status}")
    
    if validation_status == 'unknown':
        print("❌ OPA validation status not found - PR may not have been validated yet")
        pr = repo.get_pull(pr_number)
        pr.create_issue_comment(
            "❌ **Cannot merge**: OPA validation status not found.\n\n"
            "Please wait for OPA validation to complete first."
        )
        sys.exit(1)
    
    # Route based on OPA status
    if validation_status == 'passed':
        result = handle_opa_passed(repo, pr_number, workflow_url)
    elif validation_status == 'failed':
        result = handle_opa_failed(repo, pr_number, workflow_url)
    else:
        print(f"❌ Unknown validation status: {validation_status}")
        sys.exit(1)
    
    # Output results for GitHub Actions using new format
    if github_output:
        with open(github_output, 'a') as f:
            f.write(f"result={json.dumps(result)}\n")
            if result.get('merged'):
                f.write(f"merged=true\n")
                f.write(f"merge_sha={result['sha']}\n")
            else:
                f.write(f"merged=false\n")
    
    # Also print for logging
    print(f"\n✅ Result: {json.dumps(result, indent=2)}")
    if result.get('merged'):
        print(f"✅ Merged: true")
        print(f"✅ Merge SHA: {result['sha']}")
    else:
        print(f"❌ Merged: false")

if __name__ == '__main__':
    main()
