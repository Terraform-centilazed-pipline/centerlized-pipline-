#!/usr/bin/env python3
"""
Simple Module Updater for Terrateam
===================================
Updates Terraform modules within the same repository
"""

import os
import subprocess
import sys

def run_command(cmd):
    """Run a command and return success"""
    try:
        result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
        print(f"✅ {cmd}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {cmd}: {e}")
        return False

def update_modules():
    """Update Terraform modules"""
    print("🔄 Updating Terraform modules...")
    
    # Check if terraform is available
    if not run_command("terraform version"):
        print("❌ Terraform not found")
        return False
    
    # Update modules if .terraform exists, otherwise just init
    if os.path.exists('.terraform'):
        success = run_command("terraform get -update")
    else:
        print("🚀 Initializing Terraform...")
        success = run_command("terraform init")
    
    if success:
        print("✅ Module update completed")
    else:
        print("❌ Module update failed")
    
    return success

def main():
    """Main function"""
    print("📦 Terrateam Module Updater")
    success = update_modules()
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()