#!/usr/bin/env python3
"""
Terraform State Migration Script
=================================
Migrate from granular single-resource states to multi-resource combined state.

Features:
- Automatic state backup before migration
- Multi-source state consolidation (S3 + IAM + KMS -> Multi)
- State validation before and after migration
- Rollback capability using backups
- Dry-run mode for testing

Usage:
    # Dry run (no changes)
    python migrate-terraform-state.py \\
        --project test-poc-3 \\
        --account arj-wkld-a-prd \\
        --region us-east-1 \\
        --services s3 iam kms \\
        --bucket my-terraform-state-bucket \\
        --dry-run

    # Actual migration
    python migrate-terraform-state.py \\
        --project test-poc-3 \\
        --account arj-wkld-a-prd \\
        --region us-east-1 \\
        --services s3 iam \\
        --bucket my-terraform-state-bucket

    # Rollback to backup
    python migrate-terraform-state.py \\
        --rollback \\
        --backup-key "backups/2025-12-12_14-30-00_migration/s3/arj-wkld-a-prd/us-east-1/test-poc-3-s3/terraform.tfstate" \\
        --bucket my-terraform-state-bucket

Version: 1.0
"""

import argparse
import json
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional

def run_command(cmd: List[str], check: bool = True) -> Tuple[bool, str, str]:
    """Run shell command and return (success, stdout, stderr)"""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=check)
        return True, result.stdout, result.stderr
    except subprocess.CalledProcessError as e:
        return False, e.stdout, e.stderr

def backup_state(bucket: str, state_key: str, reason: str = "migration") -> Tuple[bool, str]:
    """Backup state file to backups/ prefix with timestamp"""
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    backup_key = f"backups/{timestamp}_{reason}/{state_key}"
    
    print(f"\n📦 Backing up state...")
    print(f"   Source: s3://{bucket}/{state_key}")
    print(f"   Backup: s3://{bucket}/{backup_key}")
    
    success, stdout, stderr = run_command([
        "aws", "s3", "cp",
        f"s3://{bucket}/{state_key}",
        f"s3://{bucket}/{backup_key}"
    ])
    
    if success:
        print(f"✅ Backup created: {backup_key}")
        return True, backup_key
    else:
        print(f"❌ Backup failed: {stderr}")
        return False, ""

def download_state(bucket: str, state_key: str, local_path: Path) -> bool:
    """Download state file from S3"""
    print(f"\n⬇️  Downloading state: {state_key}")
    
    success, stdout, stderr = run_command([
        "aws", "s3", "cp",
        f"s3://{bucket}/{state_key}",
        str(local_path)
    ], check=False)
    
    if success:
        print(f"✅ Downloaded to: {local_path}")
        return True
    else:
        print(f"⚠️  State not found (may be new resource): {state_key}")
        return False

def upload_state(bucket: str, state_key: str, local_path: Path) -> bool:
    """Upload state file to S3"""
    print(f"\n⬆️  Uploading state: {state_key}")
    
    success, stdout, stderr = run_command([
        "aws", "s3", "cp",
        str(local_path),
        f"s3://{bucket}/{state_key}"
    ])
    
    if success:
        print(f"✅ Uploaded to: s3://{bucket}/{state_key}")
        return True
    else:
        print(f"❌ Upload failed: {stderr}")
        return False

def merge_state_files(state_files: List[Path], output_path: Path) -> bool:
    """Merge multiple state files into one combined state"""
    print(f"\n🔀 Merging {len(state_files)} state files...")
    
    try:
        # Load all state files
        states = []
        for state_file in state_files:
            if state_file.exists():
                with open(state_file, 'r') as f:
                    state = json.load(f)
                    states.append(state)
                    print(f"   ✓ Loaded: {state_file.name} ({len(state.get('resources', []))} resources)")
        
        if not states:
            print("❌ No valid state files to merge")
            return False
        
        # Use first state as base
        merged_state = states[0].copy()
        
        # Merge resources from other states
        for state in states[1:]:
            merged_state['resources'].extend(state.get('resources', []))
        
        # Update metadata
        merged_state['lineage'] = states[0].get('lineage', 'merged')
        merged_state['serial'] = max(s.get('serial', 1) for s in states)
        
        # Write merged state
        with open(output_path, 'w') as f:
            json.dump(merged_state, f, indent=2)
        
        total_resources = len(merged_state.get('resources', []))
        print(f"✅ Merged state created: {total_resources} total resources")
        return True
        
    except Exception as e:
        print(f"❌ Failed to merge states: {e}")
        return False

def validate_state(state_path: Path) -> Tuple[bool, Dict]:
    """Validate state file structure and extract info"""
    try:
        with open(state_path, 'r') as f:
            state = json.load(f)
        
        resources = state.get('resources', [])
        version = state.get('version', 'unknown')
        terraform_version = state.get('terraform_version', 'unknown')
        
        info = {
            'version': version,
            'terraform_version': terraform_version,
            'resource_count': len(resources),
            'resource_types': list(set(r.get('type', 'unknown') for r in resources))
        }
        
        print(f"   Version: {version}")
        print(f"   Terraform: {terraform_version}")
        print(f"   Resources: {len(resources)}")
        print(f"   Types: {', '.join(info['resource_types'][:5])}")
        
        return True, info
        
    except Exception as e:
        print(f"❌ Invalid state file: {e}")
        return False, {}

def migrate_states(
    project: str,
    account: str,
    region: str,
    services: List[str],
    bucket: str,
    dry_run: bool = False
) -> bool:
    """Migrate granular states to multi-resource state"""
    
    print("=" * 70)
    print("TERRAFORM STATE MIGRATION")
    print("=" * 70)
    print(f"\nProject:  {project}")
    print(f"Account:  {account}")
    print(f"Region:   {region}")
    print(f"Services: {', '.join(services)}")
    print(f"Bucket:   {bucket}")
    print(f"Mode:     {'DRY RUN' if dry_run else 'LIVE MIGRATION'}")
    print("=" * 70)
    
    if dry_run:
        print("\n⚠️  DRY RUN MODE - No changes will be made\n")
    
    # Generate state keys
    source_keys = []
    for service in services:
        key = f"{service}/{account}/{region}/{project}-{service}/terraform.tfstate"
        source_keys.append((service, key))
    
    target_key = f"multi/{account}/{region}/{project}/terraform.tfstate"
    
    print("\n📋 Migration Plan:")
    print(f"\n   Sources:")
    for service, key in source_keys:
        print(f"     • {service}: {key}")
    print(f"\n   Target:")
    print(f"     • multi: {target_key}")
    
    if dry_run:
        print("\n✅ Dry run completed - no changes made")
        return True
    
    # Confirm migration
    print("\n⚠️  This will:")
    print("   1. Backup all source states")
    print("   2. Download and merge states")
    print("   3. Upload merged state to multi/ path")
    print("   4. Validate merged state")
    
    response = input("\nProceed with migration? (yes/no): ")
    if response.lower() != 'yes':
        print("❌ Migration cancelled")
        return False
    
    # Create temp directory
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        
        # Step 1: Backup all source states
        print("\n" + "=" * 70)
        print("STEP 1: BACKUP SOURCE STATES")
        print("=" * 70)
        
        backups = []
        for service, key in source_keys:
            success, backup_key = backup_state(bucket, key, f"migration_{service}")
            if success:
                backups.append((service, key, backup_key))
            else:
                print(f"⚠️  Could not backup {service} state (may not exist yet)")
        
        if not backups:
            print("\n⚠️  No existing states found - nothing to migrate")
            return False
        
        # Step 2: Download source states
        print("\n" + "=" * 70)
        print("STEP 2: DOWNLOAD SOURCE STATES")
        print("=" * 70)
        
        downloaded_states = []
        for service, key, backup_key in backups:
            local_path = tmppath / f"{service}.tfstate"
            if download_state(bucket, key, local_path):
                downloaded_states.append(local_path)
        
        if not downloaded_states:
            print("❌ No states downloaded - migration failed")
            return False
        
        # Step 3: Validate source states
        print("\n" + "=" * 70)
        print("STEP 3: VALIDATE SOURCE STATES")
        print("=" * 70)
        
        for state_file in downloaded_states:
            print(f"\n📊 Validating: {state_file.name}")
            valid, info = validate_state(state_file)
            if not valid:
                print(f"❌ Invalid state: {state_file.name}")
                return False
        
        # Step 4: Merge states
        print("\n" + "=" * 70)
        print("STEP 4: MERGE STATES")
        print("=" * 70)
        
        merged_path = tmppath / "merged.tfstate"
        if not merge_state_files(downloaded_states, merged_path):
            print("❌ Failed to merge states")
            return False
        
        # Step 5: Validate merged state
        print("\n" + "=" * 70)
        print("STEP 5: VALIDATE MERGED STATE")
        print("=" * 70)
        
        print(f"\n📊 Validating merged state:")
        valid, info = validate_state(merged_path)
        if not valid:
            print("❌ Merged state is invalid")
            return False
        
        # Step 6: Upload merged state
        print("\n" + "=" * 70)
        print("STEP 6: UPLOAD MERGED STATE")
        print("=" * 70)
        
        if not upload_state(bucket, target_key, merged_path):
            print("❌ Failed to upload merged state")
            return False
        
        # Step 7: Summary
        print("\n" + "=" * 70)
        print("MIGRATION COMPLETED SUCCESSFULLY")
        print("=" * 70)
        
        print(f"\n✅ Migrated from {len(backups)} granular states to 1 multi-resource state")
        print(f"\n📍 New state location:")
        print(f"   s3://{bucket}/{target_key}")
        
        print(f"\n📦 Backups available:")
        for service, key, backup_key in backups:
            print(f"   • {service}: s3://{bucket}/{backup_key}")
        
        print(f"\n⚠️  IMPORTANT NEXT STEPS:")
        print(f"   1. Update your tfvars to use project name: '{project}' (remove -service suffix)")
        print(f"   2. Run 'terraform plan' to verify 0 changes")
        print(f"   3. If plan shows recreates, use backups to rollback")
        print(f"   4. Delete old granular states after verification")
        
        return True

def rollback_migration(bucket: str, backup_key: str, target_key: Optional[str] = None) -> bool:
    """Rollback migration by restoring from backup"""
    
    print("=" * 70)
    print("TERRAFORM STATE ROLLBACK")
    print("=" * 70)
    
    # Extract target key from backup key if not provided
    if not target_key:
        # backup_key format: backups/{timestamp}_{reason}/{original_path}
        parts = backup_key.split('/', 2)
        if len(parts) < 3:
            print("❌ Invalid backup key format")
            return False
        target_key = parts[2]
    
    print(f"\nBackup:  s3://{bucket}/{backup_key}")
    print(f"Restore: s3://{bucket}/{target_key}")
    
    response = input("\nProceed with rollback? (yes/no): ")
    if response.lower() != 'yes':
        print("❌ Rollback cancelled")
        return False
    
    # Copy backup to original location
    success, stdout, stderr = run_command([
        "aws", "s3", "cp",
        f"s3://{bucket}/{backup_key}",
        f"s3://{bucket}/{target_key}"
    ])
    
    if success:
        print(f"✅ State restored from backup")
        return True
    else:
        print(f"❌ Rollback failed: {stderr}")
        return False

def main():
    parser = argparse.ArgumentParser(
        description="Migrate Terraform states from granular to multi-resource",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    # Migration arguments
    parser.add_argument('--project', help='Project name (e.g., test-poc-3)')
    parser.add_argument('--account', help='Account name (e.g., arj-wkld-a-prd)')
    parser.add_argument('--region', default='us-east-1', help='AWS region')
    parser.add_argument('--services', nargs='+', help='Services to migrate (e.g., s3 iam kms)')
    parser.add_argument('--bucket', required=True, help='S3 bucket for state files')
    parser.add_argument('--dry-run', action='store_true', help='Show plan without making changes')
    
    # Rollback arguments
    parser.add_argument('--rollback', action='store_true', help='Rollback to backup')
    parser.add_argument('--backup-key', help='Backup key to restore from')
    parser.add_argument('--target-key', help='Target key to restore to (optional)')
    
    args = parser.parse_args()
    
    # Validate arguments
    if args.rollback:
        if not args.backup_key:
            parser.error("--backup-key required for rollback")
        success = rollback_migration(args.bucket, args.backup_key, args.target_key)
    else:
        if not all([args.project, args.account, args.services]):
            parser.error("--project, --account, and --services required for migration")
        success = migrate_states(
            args.project,
            args.account,
            args.region,
            args.services,
            args.bucket,
            args.dry_run
        )
    
    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()
