#!/usr/bin/env python3
"""
Simple Team Manager for Terrateam
=================================
Handles team identification and basic notifications
"""

import os
import sys
import json

def identify_team(repo_name):
    """Identify which team owns a repository"""
    teams = {
        "dev-deployment": {"team": "platform", "approval": "auto"},
        "app1-dev": {"team": "app-team-1", "approval": "manual"},
        "service1-dev": {"team": "app-team-1", "approval": "manual"},
    }
    
    for pattern, info in teams.items():
        if pattern in repo_name or repo_name in pattern:
            result = {
                "team": info["team"],
                "repository": repo_name,
                "approval_policy": info["approval"]
            }
            print(json.dumps(result))
            return True
    
    # Default team
    result = {
        "team": "platform",
        "repository": repo_name,
        "approval_policy": "manual"
    }
    print(json.dumps(result))
    return False

def notify_team(team_name, message):
    """Simple notification (can be extended)"""
    print(f"📢 Notification for {team_name}: {message}")
    return True

def main():
    if len(sys.argv) < 2:
        print("Usage: team-manager.py <command> [args]")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "identify-team":
        repo = os.getenv('TERRATEAM_REPO', sys.argv[2] if len(sys.argv) > 2 else 'unknown')
        identify_team(repo)
    elif command == "notify-team":
        team = sys.argv[2] if len(sys.argv) > 2 else "platform"
        message = sys.argv[3] if len(sys.argv) > 3 else "Deployment completed"
        notify_team(team, message)
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)

if __name__ == "__main__":
    main()