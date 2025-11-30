# PR Merge Handler Script

## Overview
This Python script handles PR approval checking and merging with OPA validation integration. It replaces the complex JavaScript logic in the GitHub Actions workflow for better maintainability.

## Features

### 1. **Dynamic Commit Messages with Audit Trail**
- Includes PR author, approver, changed files
- Adds workflow URL and timestamps
- Full audit trail for compliance

### 2. **Approval-Based Merge**
- Requires at least one PR approval before merge
- Waits for approval if not yet reviewed
- Auto-merges after approval (for OPA passed)

### 3. **OPA Failure Blocking**
- **Regular users**: Cannot merge if OPA fails (auto or manual blocked)
- **Special approvers**: Can override with justification
- Requires "OVERRIDE" keyword in comment with risk assessment

### 4. **Special Approver Override**
- Configured in `SPECIAL_APPROVERS` list
- Must provide justification comment
- Tracks override in commit message and labels

## Configuration

### Special Approvers
Edit the script to add/remove special approvers:

```python
SPECIAL_APPROVERS = ['pragadeeswarpa', 'another-user']
```

## Environment Variables Required

The script expects these environment variables (set by workflow):

- `GITHUB_TOKEN`: GitHub authentication token
- `OPA_VALIDATION_STATUS`: Result from OPA validation (`passed` or `failed`)
- `SOURCE_OWNER`: Repository owner
- `SOURCE_REPO`: Repository name
- `PR_NUMBER`: Pull request number
- `WORKFLOW_URL`: GitHub Actions workflow run URL

## Workflow Integration

```yaml
- name: 🐍 Setup Python
  uses: actions/setup-python@v4
  with:
    python-version: '3.11'
    
- name: 📦 Install Python dependencies
  run: pip install -r scripts/requirements.txt
  
- name: 🏷️ Check Approval and Merge PR
  id: merge
  env:
    GITHUB_TOKEN: ${{ steps.app-token.outputs.token }}
    OPA_VALIDATION_STATUS: ${{ steps.opa.outputs.validation_status }}
    SOURCE_OWNER: ${{ github.event.client_payload.source_owner }}
    SOURCE_REPO: ${{ github.event.client_payload.source_repo }}
    PR_NUMBER: ${{ github.event.client_payload.pr_number }}
    WORKFLOW_URL: ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}
  run: python scripts/handle_pr_merge.py
```

## Outputs

The script sets these outputs for subsequent workflow steps:

- `merged`: `true` if PR was merged, `false` otherwise
- `merge_sha`: Git SHA of the merge commit (if merged)
- `result`: JSON object with full result details

## Behavior

### When OPA Passes:
1. Check for PR approvals
2. If no approval → Post comment, wait
3. If approved → Merge with audit trail
4. Post success notifications
5. Add labels: `opa-passed`, `ready-to-merge`

### When OPA Fails:
1. Check for special approver in approval list
2. If no special approver:
   - Block PR completely
   - Add labels: `opa-failed`, `blocked`, `requires-special-approval`
   - Post blocking comment
3. If special approver exists:
   - Check for OVERRIDE justification comment
   - If no justification → Request it
   - If justified → Merge with override warning
   - Add labels: `opa-override`, `special-approval`

## Example Override Comment

```
OVERRIDE: Emergency production fix required.
Risk: Low - temporary workaround, will fix in next sprint.
Timeline: Fix planned for Sprint 24.
```

## Dependencies

- `PyGithub==2.1.1`: GitHub API library

Install with:
```bash
pip install -r scripts/requirements.txt
```

## Testing Locally

```bash
export GITHUB_TOKEN="your-token"
export OPA_VALIDATION_STATUS="passed"
export SOURCE_OWNER="org-name"
export SOURCE_REPO="repo-name"
export PR_NUMBER="123"
export WORKFLOW_URL="https://github.com/..."

python scripts/handle_pr_merge.py
```

## Error Handling

- Missing environment variables → Exit with error
- Merge conflicts → Post comment, set merged=false
- API errors → Log error, graceful failure
- Network issues → Retry with exponential backoff (future enhancement)

## Security Notes

- Uses GitHub App token for authentication
- Special approvers hardcoded (consider moving to config file)
- All actions logged for audit trail
- Override requires explicit justification

## Future Enhancements

- [ ] Move SPECIAL_APPROVERS to config file
- [ ] Add retry logic for API calls
- [ ] Support multiple approval requirements
- [ ] Integrate with Slack/Teams notifications
- [ ] Add metrics collection
