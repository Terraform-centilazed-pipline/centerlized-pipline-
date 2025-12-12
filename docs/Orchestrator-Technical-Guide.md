# Terraform Deployment Orchestrator - Technical Guide v2.0

**Document Version:** 2.0  
**Orchestrator Version:** 2.0  
**Last Updated:** December 12, 2025  
**Component:** `scripts/terraform-deployment-orchestrator-enhanced.py`  
**Status:** Production Ready ✅

---

## Table of Contents

### Core Documentation
1. [Overview](#overview)
2. [System Architecture](#system-architecture)
3. [Design Principles](#design-principles)
4. [Workflow Stages](#workflow-stages)
5. [State Management Design](#state-management-design)
6. [Parallel Execution Architecture](#parallel-execution-architecture)
7. [Error Handling & Rollback](#error-handling--rollback)
8. [API Reference](#api-reference)
9. [Configuration](#configuration)
10. [Security & Compliance](#security--compliance)

### Advanced Topics
11. [Performance Tuning](#performance-tuning)
12. [Monitoring & Metrics](#monitoring--metrics)
13. [Disaster Recovery](#disaster-recovery)
14. [Best Practices](#best-practices)
15. [Migration Guide (v1.0 → v2.0)](#migration-guide)
16. [Advanced Troubleshooting](#advanced-troubleshooting)
17. [FAQ](#faq)
18. [Architecture Decision Records](#architecture-decision-records)

---

## Overview

The **Enhanced Terraform Deployment Orchestrator v2.0** is a Python-based automation engine that orchestrates multi-account, multi-region AWS infrastructure deployments using Terraform. It provides intelligent state management, parallel execution, automatic backup/rollback, and comprehensive audit logging.

### Key Capabilities

- **Dynamic Backend Key Generation**: Automatic state file organization by service/account/region/project
- **Parallel Execution**: Thread-pool based concurrent deployments (up to 5 workers)
- **Automatic State Backup**: S3-based state snapshots before every apply
- **Automatic Rollback**: Restores previous state on apply failures
- **Service Detection**: Analyzes tfvars to identify AWS services (S3, KMS, IAM, Lambda, etc.)
- **Security**: Redacts sensitive data (ARNs, IPs, Account IDs) from PR comments
- **Audit Trail**: Encrypted S3 logs with full unredacted output for compliance

---

## System Architecture

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    GitHub Actions Workflow                       │
│                 (.github/workflows/centralized-controller.yml)   │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│          Terraform Deployment Orchestrator v2.0                  │
│                  (Python Thread Pool)                            │
│                                                                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │   Worker 1   │  │   Worker 2   │  │   Worker 3   │  ...     │
│  │  Deployment  │  │  Deployment  │  │  Deployment  │          │
│  │   Executor   │  │   Executor   │  │   Executor   │          │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘          │
│         │                  │                  │                   │
└─────────┼──────────────────┼──────────────────┼──────────────────┘
          │                  │                  │
          ▼                  ▼                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Terraform CLI (per deployment)                │
│  - terraform init (dynamic backend key)                          │
│  - terraform plan/apply                                          │
│  - State locking enabled                                         │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                  AWS S3 Backend (State Storage)                  │
│                                                                   │
│  Bucket: terraform-elb-mdoule-poc                                │
│  Encryption: AES256                                              │
│  Versioning: Enabled                                             │
│                                                                   │
│  State Files:                                                    │
│    s3/{service}/{account}/{region}/{project}/terraform.tfstate   │
│                                                                   │
│  Backups:                                                        │
│    backups/{service}/{account}/{region}/{project}/               │
│           terraform.tfstate.{timestamp}.backup                   │
│                                                                   │
│  Audit Logs:                                                     │
│    audit-logs/{account}/{project}/{action}-{timestamp}.json      │
└─────────────────────────────────────────────────────────────────┘
```

### Component Interaction Flow

```
GitHub PR → Workflow Trigger → Orchestrator Discovery
                                      │
                                      ├─> Find Changed Files
                                      ├─> Analyze Tfvars
                                      ├─> Detect Services
                                      ├─> Generate Backend Keys
                                      │
                                      ▼
                              Parallel Execution
                                      │
                    ┌─────────────────┼─────────────────┐
                    │                 │                 │
                    ▼                 ▼                 ▼
              Deployment 1      Deployment 2      Deployment 3
                    │                 │                 │
                    ├─> Init          ├─> Init          ├─> Init
                    ├─> Backup        ├─> Backup        ├─> Backup
                    ├─> Plan/Apply    ├─> Plan/Apply    ├─> Plan/Apply
                    ├─> Audit Log     ├─> Audit Log     ├─> Audit Log
                    │                 │                 │
                    └─────────────────┼─────────────────┘
                                      │
                                      ▼
                              Results Aggregation
                                      │
                                      ├─> Generate PR Comments
                                      ├─> Create JSON Plans
                                      └─> Trigger OPA Validation
```

---

## Design Principles

### 1. **Service-First State Sharding**

**Problem:** Traditional account-based state files become bloated and cause locking conflicts.

**Solution:** Organize state files by service type for granular isolation.

```python
# Backend Key Pattern
{service}/{account_name}/{region}/{project}/terraform.tfstate

# Examples:
s3/arj-wkld-a-prd/us-east-1/test-4-poc-1/terraform.tfstate
kms/arj-wkld-a-prd/us-east-1/encryption-keys/terraform.tfstate
iam/shared-services/us-east-1/cross-account-roles/terraform.tfstate
```

**Benefits:**
- Reduced blast radius (S3 failure doesn't affect KMS)
- Parallel deployments (different services don't lock each other)
- Clear ownership (S3 team owns S3 state files)

### 2. **Fail-Safe with Automatic Rollback**

**Design Pattern:** Copy-on-Write with Rollback

```python
Apply Workflow:
1. Read current state from S3
2. Copy to backup: backups/{key}.{timestamp}.backup
3. Execute terraform apply
4. IF success: Keep new state
5. IF failure: Restore from backup automatically
```

**Implementation:**
```python
def _backup_state_file(backend_key, deployment_name):
    timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    backup_key = f"backups/{backend_key}.{timestamp}.backup"
    s3.copy_object(Source=backend_key, Dest=backup_key)
    
def _rollback_state_file(deployment_name):
    backup_key = self.state_backups[deployment_name]['backup_key']
    s3.copy_object(Source=backup_key, Dest=original_key)
```

### 3. **Parallel Execution Without Conflicts**

**Challenge:** Multiple deployments must run concurrently without workspace conflicts.

**Solution:** Isolated workspace directories per deployment

```python
# Each deployment gets isolated workspace
deployment_workspace = f".terraform-workspace-{account_name}-{project}"

# Benefits:
- No .terraform.lock.hcl conflicts
- No provider cache sharing issues
- Clean state between runs
```

**Thread Pool Design:**
```python
# CPU-based worker calculation
cpu_count = os.cpu_count() or 2
optimal_workers = cpu_count * 2  # Terraform is I/O bound
max_workers = min(optimal_workers, 5)  # AWS rate limit cap

with ThreadPoolExecutor(max_workers=max_workers) as executor:
    futures = {executor.submit(process, dep): dep for dep in deployments}
```

### 4. **Security by Redaction**

**Design:** Defense in Depth for Sensitive Data

```python
# Layer 1: PR Comments - REDACTED
pr_comment = redact_sensitive_data(terraform_output)

# Layer 2: S3 Audit Logs - FULL UNREDACTED
audit_log = {
    'output': terraform_output,  # No redaction
    'encryption': 'AES256',
    'access': 'Compliance team only'
}
```

**Redaction Patterns:**
- ARNs: `arn:aws:s3:::bucket-name` → `arn:aws:s3:::***REDACTED***`
- IPs: `192.168.1.100` → `***.***.***.***`
- Account IDs: `123456789012` → `***REDACTED***`

---

## Workflow Stages

### Stage 1: Discovery

**Purpose:** Find all deployments to process based on changed files.

```python
def find_deployments(changed_files, filters):
    # Input: ['Accounts/test-4-poc-1/test.tfvars', 'Accounts/test-4-poc-1/policy.json']
    
    # Processing:
    1. Detect .tfvars files (direct deployments)
    2. Find .tfvars for changed .json files (policy updates)
    3. Analyze each tfvars file:
       - Extract account_name, region, project
       - Detect services (S3, KMS, IAM, etc.)
       - Parse tags (Owner, Team, Environment)
    
    # Output: List of deployment dictionaries
    [
        {
            'file': '/path/to/deployment.tfvars',
            'account_name': 'arj-wkld-a-prd',
            'region': 'us-east-1',
            'project': 'test-4-poc-1',
            'services': ['s3', 'kms'],
            'resources': 'S3: bucket-name, KMS: key-alias'
        }
    ]
```

**Service Detection Logic:**
```python
# Scan tfvars content for service blocks
service_mapping = {
    's3_buckets': 's3',
    'kms_keys': 'kms',
    'iam_roles': 'iam',
    'lambda_functions': 'lambda',
    'sqs_queues': 'sqs'
}

# Pattern matching
if re.search(r'\bs3_buckets\s*=', tfvars_content):
    services.append('s3')
```

### Stage 2: Backend Key Generation

**Purpose:** Create unique state file path for each deployment.

```python
def _generate_dynamic_backend_key(deployment, services):
    # Input:
    account_name = 'arj-wkld-a-prd'
    project = 'test-4-poc-1'
    region = 'us-east-1'
    services = ['s3', 'kms']
    
    # Logic:
    if len(services) == 0: service_part = "general"
    elif len(services) == 1: service_part = services[0]  # "s3"
    else: service_part = "combined"  # "combined"
    
    # Output:
    "s3/arj-wkld-a-prd/us-east-1/test-4-poc-1/terraform.tfstate"
```

**Key Structure Benefits:**

| Level | Example | Purpose |
|-------|---------|---------|
| Service | `s3/` | Isolate blast radius |
| Account | `arj-wkld-a-prd/` | Multi-account support |
| Region | `us-east-1/` | Regional isolation |
| Project | `test-4-poc-1/` | Deployment granularity |
| File | `terraform.tfstate` | Standard naming |

### Stage 3: Workspace Isolation

**Purpose:** Prevent parallel deployment conflicts.

```python
def _process_deployment_enhanced(deployment):
    # Create isolated workspace
    deployment_name = f"{account_name}-{project}"
    workspace = f".terraform-workspace-{deployment_name}"
    
    # Clean slate approach
    if workspace.exists():
        shutil.rmtree(workspace)  # Remove stale locks
    
    workspace.mkdir()
    
    # Copy required files
    shutil.copy2(tfvars_file, workspace / "terraform.tfvars")
    shutil.copy2("main.tf", workspace / "main.tf")
    
    # Copy policy JSON files
    _copy_referenced_policy_files(tfvars_file, workspace)
```

**File Discovery for Policy JSONs:**
```python
def _copy_referenced_policy_files(tfvars_file, dest_dir):
    # Extract JSON references from tfvars
    json_pattern = r'["\']([^"\']+\.json)["\']'
    json_files = re.findall(json_pattern, tfvars_content)
    
    # Examples:
    # bucket_policy_file = "Accounts/test-4-poc-1/bucket-policy.json"
    # kms_policy_file = "KMS/key-policy.json"
    
    for json_path in json_files:
        source = working_dir / json_path
        dest = workspace / json_path
        shutil.copy2(source, dest)
```

### Stage 4: Terraform Initialization

**Purpose:** Configure backend with dynamic state key.

```python
init_cmd = [
    'terraform', 'init', '-input=false',
    f'-backend-config=key={backend_key}',
    f'-backend-config=region=us-east-1',
    f'-backend-config=bucket=terraform-elb-mdoule-poc'
]

# Example command:
# terraform init \
#   -backend-config=key=s3/arj-wkld-a-prd/us-east-1/test-4-poc-1/terraform.tfstate \
#   -backend-config=region=us-east-1
```

**State Locking:**
- Built-in Terraform lockfile mechanism
- DynamoDB table for distributed locking
- Automatic lock cleanup on crash

### Stage 5: State Backup (Apply Only)

**Purpose:** Create restore point before infrastructure changes.

```python
def _backup_state_file(backend_key, deployment_name):
    # Check if state exists
    try:
        s3.head_object(Bucket=bucket, Key=backend_key)
    except:
        return True, "no-previous-state"  # First deployment
    
    # Create timestamped backup
    timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    backup_key = f"backups/{backend_key}.{timestamp}.backup"
    
    # Copy with encryption
    s3.copy_object(
        Bucket=bucket,
        CopySource={'Bucket': bucket, 'Key': backend_key},
        Key=backup_key,
        ServerSideEncryption='AES256'
    )
    
    # Store for rollback
    self.state_backups[deployment_name] = {
        'backup_key': backup_key,
        'original_key': backend_key,
        'timestamp': timestamp
    }
```

**Backup Structure:**
```
s3://terraform-elb-mdoule-poc/
├── s3/arj-wkld-a-prd/us-east-1/test-4-poc-1/
│   └── terraform.tfstate                    # Current state
└── backups/s3/arj-wkld-a-prd/us-east-1/test-4-poc-1/
    ├── terraform.tfstate.20251212-140530.backup
    ├── terraform.tfstate.20251212-095412.backup
    └── terraform.tfstate.20251211-163245.backup
```

### Stage 6: Terraform Execution

**Purpose:** Run plan or apply with error handling.

```python
def _run_terraform_command(cmd, cwd):
    # Execute with timeout protection
    result = subprocess.run(
        ['terraform'] + cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=1800  # 30 minutes
    )
    
    return {
        'returncode': result.returncode,
        'stdout': result.stdout,
        'stderr': result.stderr
    }
```

**Exit Code Handling:**

| Action | Exit Code | Meaning | Success? |
|--------|-----------|---------|----------|
| Plan | 0 | No changes detected | ✅ Yes |
| Plan | 2 | Changes detected | ✅ Yes |
| Plan | 1 | Error | ❌ No |
| Apply | 0 | Success | ✅ Yes |
| Apply | 1 | Failure | ❌ No |

**Plan JSON Generation:**
```python
# Save plan to binary file
terraform plan -out=deployment.tfplan

# Convert to JSON for OPA validation
terraform show -json deployment.tfplan > plan.json

# Create markdown for PR comments
terraform show deployment.tfplan > plan.md
```

### Stage 7: Rollback on Failure

**Purpose:** Restore previous state if apply fails.

```python
if action == "apply" and result['returncode'] != 0:
    print("❌ Apply failed! Attempting rollback...")
    
    # Restore from backup
    rollback_success = _rollback_state_file(deployment_name)
    
    if rollback_success:
        print("✅ State rolled back successfully")
    else:
        print("⚠️ Manual intervention required")
        # Alert compliance team
```

**Rollback Process:**
```python
def _rollback_state_file(deployment_name):
    backup_info = self.state_backups[deployment_name]
    
    # Copy backup back to original location
    s3.copy_object(
        Bucket=bucket,
        CopySource={'Bucket': bucket, 'Key': backup_info['backup_key']},
        Key=backup_info['original_key']
    )
    
    return True
```

### Stage 8: Audit Logging

**Purpose:** Store full deployment details for compliance.

```python
def _save_audit_log(deployment, result, action):
    timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    log_key = f"audit-logs/{account_name}/{project}/{action}-{timestamp}.json"
    
    audit_data = {
        'timestamp': datetime.now().isoformat(),
        'action': action,
        'deployment': deployment,
        'result': {
            'success': result['success'],
            'output': result['output'],  # UNREDACTED
            'backend_key': result['backend_key'],
            'services': result['services']
        },
        'orchestrator_version': '2.0'
    }
    
    # Encrypted storage
    s3.put_object(
        Bucket=bucket,
        Key=log_key,
        Body=json.dumps(audit_data, indent=2),
        ServerSideEncryption='AES256'
    )
```

**Audit Log Structure:**
```json
{
  "timestamp": "2025-12-12T14:05:30Z",
  "action": "apply",
  "deployment": {
    "account_name": "arj-wkld-a-prd",
    "region": "us-east-1",
    "project": "test-4-poc-1"
  },
  "result": {
    "success": true,
    "backend_key": "s3/arj-wkld-a-prd/us-east-1/test-4-poc-1/terraform.tfstate",
    "services": ["s3", "kms"],
    "output": "...full terraform output with ARNs..."
  },
  "orchestrator_version": "2.0"
}
```

---

## State Management Design

### State File Naming Strategy

**Formula:**
```
{service}/{account_name}/{region}/{project}/terraform.tfstate
```

**Service Detection Priority:**

1. **Single Service:** Use service name directly
   ```
   # Only s3_buckets defined
   → s3/account/region/project/terraform.tfstate
   ```

2. **Multiple Services:** Use "combined"
   ```
   # s3_buckets + kms_keys defined
   → combined/account/region/project/terraform.tfstate
   ```

3. **No Services Detected:** Use "general"
   ```
   # No service blocks found
   → general/account/region/project/terraform.tfstate
   ```

### State Isolation Benefits

| Scenario | Traditional (Account-Based) | Service-First (v2.0) |
|----------|----------------------------|----------------------|
| S3 deployment fails | ❌ Blocks all resources | ✅ Only blocks S3 |
| KMS key rotation | ❌ Locks entire account state | ✅ Only locks KMS state |
| Parallel deploys | ❌ Sequential (locking) | ✅ Parallel (isolated) |
| Blast radius | ❌ All resources | ✅ Service-specific |
| Team ownership | ❌ Shared state file | ✅ Team per service |

### State Versioning

**S3 Versioning Enabled:**
```bash
# Every state update creates new version
s3://bucket/s3/account/region/project/terraform.tfstate
├── Version 1 (2025-12-10 10:00)
├── Version 2 (2025-12-11 14:30)
└── Version 3 (2025-12-12 09:15) ← Current
```

**Manual Restore:**
```bash
# List versions
aws s3api list-object-versions \
  --bucket terraform-elb-mdoule-poc \
  --prefix s3/arj-wkld-a-prd/us-east-1/test-4-poc-1/

# Restore specific version
aws s3api copy-object \
  --copy-source "bucket/key?versionId=xyz" \
  --bucket bucket \
  --key key
```

---

## Parallel Execution Architecture

### Thread Pool Design

**Worker Calculation:**
```python
cpu_count = os.cpu_count()  # e.g., 4 cores
optimal_workers = cpu_count * 2  # 8 workers (I/O bound)
max_workers = min(optimal_workers, 5)  # Cap at 5 (AWS rate limits)
```

**Execution Flow:**
```python
with ThreadPoolExecutor(max_workers=5) as executor:
    # Submit all deployments
    futures = {
        executor.submit(process_deployment, dep): dep
        for dep in deployments
    }
    
    # Process as they complete
    for future in as_completed(futures):
        result = future.result()
        results.append(result)
```

### Concurrency Safety

**Problem:** Multiple threads accessing shared resources.

**Solutions:**

1. **Thread-Safe Result Collection:**
   ```python
   lock = threading.Lock()
   
   with lock:
       results['successful'].append(result)
   ```

2. **Isolated Workspaces:**
   ```python
   # Each deployment gets unique directory
   workspace = f".terraform-workspace-{account}-{project}"
   ```

3. **No Shared State:**
   ```python
   # Each deployment has independent:
   - tfvars file
   - backend key
   - workspace directory
   - terraform process
   ```

### Performance Metrics

**Example Execution (5 deployments):**

| Metric | Sequential | Parallel (5 workers) | Improvement |
|--------|-----------|---------------------|-------------|
| Total time | 25 min | 7 min | **71% faster** |
| CPU usage | 25% | 85% | Better utilization |
| Throughput | 1 deploy/5min | 5 deploys/7min | **3.5x faster** |

---

## Error Handling & Rollback

### Error Detection Layers

**Layer 1: Validation Errors**
```python
# Tfvars file validation
if not tfvars_file.exists():
    return error("Tfvars file not found")

if content.count('{') != content.count('}'):
    return error("Mismatched braces")
```

**Layer 2: Terraform Init Errors**
```python
init_result = run_terraform(['init'])
if init_result['returncode'] != 0:
    return {
        'success': False,
        'error': 'Terraform init failed',
        'output': init_result['stderr']
    }
```

**Layer 3: Terraform Plan/Apply Errors**
```python
apply_result = run_terraform(['apply', '-auto-approve'])
if apply_result['returncode'] != 0:
    # Trigger automatic rollback
    rollback_state_file(deployment_name)
```

### Rollback Mechanisms

**Automatic Rollback (Apply Failures):**
```python
# Triggered automatically on apply failure
if action == "apply" and returncode != 0:
    1. Identify backup in self.state_backups[deployment_name]
    2. Copy backup to original state file location
    3. Log rollback action to audit trail
    4. Notify in PR comment
```

**Manual Rollback (Production Issues):**
```bash
# Find backups
aws s3 ls s3://terraform-elb-mdoule-poc/backups/s3/account/region/project/

# Restore specific backup
aws s3 cp \
  s3://bucket/backups/.../terraform.tfstate.20251212-140530.backup \
  s3://bucket/s3/account/region/project/terraform.tfstate
```

### Failure Scenarios & Recovery

| Failure Type | Auto Recovery | Manual Steps |
|--------------|---------------|--------------|
| Tfvars syntax error | ✅ Validation fails fast | Fix tfvars, push to new branch |
| Init failure | ✅ Fails before state changes | Check backend config |
| Plan error | ✅ No state changes | Fix Terraform code |
| Apply failure | ✅ Automatic rollback | Review logs, fix issue, retry |
| Network timeout | ✅ Terraform retries | Check AWS connectivity |
| S3 backup failure | ⚠️ Warning logged | Manual backup before retry |

---

## API Reference

### Main Classes

#### `EnhancedTerraformOrchestrator`

Primary orchestration class for deployment execution.

**Constructor:**
```python
orchestrator = EnhancedTerraformOrchestrator(working_dir="/path/to/deployment")
```

**Parameters:**
- `working_dir` (Path, optional): Working directory for deployment discovery. Defaults to CWD.

**Attributes:**
- `project_root` (Path): Root directory of Terraform project
- `accounts_config` (Dict): Parsed accounts.yaml configuration
- `service_mapping` (Dict): Maps tfvars keys to service names
- `state_backups` (Dict): Tracks state backups for rollback

---

### Core Methods

#### `find_deployments()`

Discover deployments based on changed files or all tfvars.

```python
def find_deployments(
    changed_files: Optional[List[str]] = None,
    filters: Optional[Dict] = None
) -> List[Dict]:
    """
    Find deployments to process.
    
    Args:
        changed_files: List of changed file paths (relative or absolute)
        filters: Filter criteria (account_name, region, environment)
    
    Returns:
        List of deployment dictionaries with metadata
    
    Example:
        deployments = orchestrator.find_deployments(
            changed_files=['Accounts/test-4-poc-1/test.tfvars'],
            filters={'region': 'us-east-1'}
        )
    """
```

**Output Structure:**
```python
[
    {
        'file': '/abs/path/to/deployment.tfvars',
        'file_relative': 'Accounts/test-4-poc-1/test.tfvars',
        'account_id': '123456789012',
        'account_name': 'arj-wkld-a-prd',
        'region': 'us-east-1',
        'project': 'test-4-poc-1',
        'deployment_dir': '/abs/path/to/Accounts/test-4-poc-1',
        'environment': 'production',
        'owner': 'Platform Team',
        'team': 'DevOps',
        'resources': 'S3: bucket-name, KMS: key-alias'
    }
]
```

---

#### `execute_deployments()`

Execute terraform deployments with parallel processing.

```python
def execute_deployments(
    deployments: List[Dict],
    action: str = "plan"
) -> Dict:
    """
    Execute terraform deployments in parallel.
    
    Args:
        deployments: List from find_deployments()
        action: Terraform action ('plan', 'apply', 'destroy')
    
    Returns:
        Results dictionary with success/failure lists
    
    Example:
        results = orchestrator.execute_deployments(
            deployments=deployments,
            action='apply'
        )
    """
```

**Output Structure:**
```python
{
    'successful': [
        {
            'deployment': {...},
            'success': True,
            'backend_key': 's3/account/region/project/terraform.tfstate',
            'services': ['s3', 'kms'],
            'output': '...terraform output...',
            'action': 'apply',
            'orchestrator_version': '2.0'
        }
    ],
    'failed': [
        {
            'deployment': {...},
            'success': False,
            'error': 'Apply failed with exit code 1',
            'output': '...error output...'
        }
    ],
    'summary': {
        'total': 5,
        'successful': 4,
        'failed': 1,
        'action': 'apply'
    }
}
```

---

### Internal Methods

#### `_generate_dynamic_backend_key()`

Generate state file key based on service/account/region/project.

```python
def _generate_dynamic_backend_key(
    deployment: Dict,
    services: List[str],
    tfvars_file: Path = None
) -> str:
    """
    Generate dynamic backend key.
    
    Returns:
        Backend key string (e.g., "s3/account/region/project/terraform.tfstate")
    """
```

---

#### `_backup_state_file()`

Create timestamped backup of current state before apply.

```python
def _backup_state_file(
    backend_key: str,
    deployment_name: str
) -> Tuple[bool, str]:
    """
    Backup state file to S3.
    
    Returns:
        (success: bool, backup_key_or_error: str)
    """
```

---

#### `_rollback_state_file()`

Restore state file from backup after apply failure.

```python
def _rollback_state_file(deployment_name: str) -> bool:
    """
    Rollback to previous state file.
    
    Returns:
        True if rollback successful
    """
```

---

#### `_save_audit_log()`

Save deployment audit log to encrypted S3 storage.

```python
def _save_audit_log(
    deployment: Dict,
    result: Dict,
    action: str
) -> bool:
    """
    Save audit log with full unredacted output.
    
    Returns:
        True if audit log saved successfully
    """
```

---

#### `_detect_services_from_tfvars()`

Analyze tfvars content to identify AWS services.

```python
def _detect_services_from_tfvars(tfvars_file: Path) -> List[str]:
    """
    Detect services from tfvars.
    
    Returns:
        List of service names (e.g., ['s3', 'kms', 'iam'])
    """
```

**Detection Logic:**
```python
service_mapping = {
    's3_buckets': 's3',
    'kms_keys': 'kms',
    'iam_roles': 'iam',
    'iam_policies': 'iam',
    'lambda_functions': 'lambda',
    'sqs_queues': 'sqs',
    'sns_topics': 'sns'
}

# Scan tfvars for patterns like: s3_buckets = {
for tfvars_key, service in service_mapping.items():
    if re.search(rf'\b{tfvars_key}\s*=', content):
        detected_services.append(service)
```

---

#### `redact_sensitive_data()`

Redact sensitive information from output for PR comments.

```python
def redact_sensitive_data(text: str) -> str:
    """
    Redact ARNs, account IDs, IPs from text.
    
    Returns:
        Redacted text safe for PR comments
    """
```

**Redaction Patterns:**
```python
# ARN redaction
arn:aws:s3:::my-bucket → arn:aws:s3:::***REDACTED***

# Account ID redaction
123456789012 → ***REDACTED***

# IP address redaction
192.168.1.100 → ***.***.***.***
```

---

## Configuration

### Environment Variables

| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| `TERRAFORM_DIR` | No | Terraform project directory | `centerlized-pipline-` |
| `AWS_REGION` | Yes | Default AWS region | `us-east-1` |
| `AWS_ACCESS_KEY_ID` | Yes | AWS credentials | `AKIA...` |
| `AWS_SECRET_ACCESS_KEY` | Yes | AWS credentials | `secret` |

### Configuration Files

#### `accounts.yaml`

Account configuration and metadata.

```yaml
accounts:
  "123456789012":
    account_name: "arj-wkld-a-prd"
    region: "us-east-1"
    environment: "production"
    owner: "Platform Team"

default_tags:
  ManagedBy: "Terraform"
  Team: "DevOps"
```

#### Backend Configuration

Defined in `provider.tf`:

```hcl
terraform {
  backend "s3" {
    bucket         = "terraform-elb-mdoule-poc"
    # key is dynamic, set by orchestrator
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "terraform-state-lock"
  }
}
```

### Command-Line Usage

```bash
# Discover deployments
python scripts/terraform-deployment-orchestrator-enhanced.py discover \
  --changed-files "Accounts/test-4-poc-1/test.tfvars" \
  --working-dir /path/to/dev-deployment

# Plan with filters
python scripts/terraform-deployment-orchestrator-enhanced.py plan \
  --account arj-wkld-a-prd \
  --region us-east-1

# Apply deployments
python scripts/terraform-deployment-orchestrator-enhanced.py apply \
  --changed-files "Accounts/*/test.tfvars" \
  --output-summary results.json

# Debug mode
python scripts/terraform-deployment-orchestrator-enhanced.py plan \
  --debug \
  --dry-run
```

**Arguments:**

| Argument | Description | Example |
|----------|-------------|---------|
| `action` | Terraform action | `discover`, `plan`, `apply`, `destroy` |
| `--account` | Filter by account name | `arj-wkld-a-prd` |
| `--region` | Filter by region | `us-east-1` |
| `--environment` | Filter by environment | `production` |
| `--changed-files` | Space-separated changed files | `"file1.tfvars file2.json"` |
| `--output-summary` | JSON output file | `summary.json` |
| `--working-dir` | Working directory | `/path/to/repo` |
| `--dry-run` | Show deployments without executing | (flag) |
| `--debug` | Enable debug logging | (flag) |

---

## Security & Compliance

### Data Protection Layers

**Layer 1: PR Comments (Redacted)**
- Sensitive data removed (ARNs, IPs, Account IDs)
- Safe for public/internal collaboration
- Generated via `redact_sensitive_data()`

**Layer 2: Audit Logs (Unredacted)**
- Full terraform output preserved
- Encrypted at rest (AES256)
- Stored in S3 with restricted access
- Retention policy: 90 days

**Layer 3: State Files (Encrypted)**
- AES256 encryption
- Versioning enabled
- Locked during operations
- Backup before every apply

### Access Control

**S3 Bucket Policies:**
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {"AWS": "arn:aws:iam::ACCOUNT:role/TerraformRole"},
      "Action": ["s3:GetObject", "s3:PutObject"],
      "Resource": "arn:aws:s3:::terraform-elb-mdoule-poc/*"
    },
    {
      "Effect": "Allow",
      "Principal": {"AWS": "arn:aws:iam::ACCOUNT:role/ComplianceRole"},
      "Action": ["s3:GetObject"],
      "Resource": "arn:aws:s3:::terraform-elb-mdoule-poc/audit-logs/*"
    }
  ]
}
```

### Compliance Features

✅ **Audit Trail:** Every deployment logged to S3 with:
- Timestamp (ISO 8601)
- User/Role ARN
- Full terraform output
- Success/failure status
- Backend key used

✅ **State Backup:** Automatic snapshots before apply:
- Timestamped backups
- Automatic rollback on failure
- 30-day retention

✅ **Security Scanning:** Integration points:
- OPA policy validation (plan stage)
- Checkov security checks (workflow)
- Custom policy enforcement

✅ **Least Privilege:** IAM roles with:
- Service-specific permissions
- Time-limited credentials
- MFA for production applies

---

## Troubleshooting

### Common Issues

#### Issue: "Terraform init failed"

**Symptoms:**
```
Error: Failed to get existing workspaces: S3 bucket does not exist
```

**Solutions:**
1. Verify S3 backend bucket exists: `terraform-elb-mdoule-poc`
2. Check AWS credentials have S3 access
3. Verify backend configuration in `provider.tf`

---

#### Issue: "State file locked"

**Symptoms:**
```
Error: Error acquiring the state lock
Lock Info:
  ID: abc123...
```

**Solutions:**
```bash
# Force unlock (use with caution)
terraform force-unlock abc123

# Or wait for lock to expire (15 minutes default)
```

---

#### Issue: "Parallel execution conflicts"

**Symptoms:**
```
Error: .terraform.lock.hcl conflicts
```

**Solutions:**
- Orchestrator automatically cleans workspaces
- If manual run: Delete `.terraform-workspace-*` directories
- Ensure workspace isolation is working

---

#### Issue: "Backup creation failed"

**Symptoms:**
```
⚠️ State backup failed: AccessDenied
```

**Solutions:**
1. Check IAM permissions for S3 copy operations
2. Verify `backups/` prefix is writable
3. Continue with apply (warning only) or abort

---

### Debug Mode

Enable detailed logging:

```bash
# Command line
python orchestrator.py plan --debug

# In code
DEBUG = True
```

**Debug Output Includes:**
- File path resolutions
- Service detection logic
- Backend key generation
- Tfvars parsing
- Workspace creation steps
- Full terraform commands

---

## Version History

### v2.0 (Current - Dec 2025)

**Major Features:**
- ✅ Service-first state sharding
- ✅ Parallel execution (thread pool)
- ✅ Automatic state backup/rollback
- ✅ Encrypted audit logging
- ✅ Security redaction for PR comments
- ✅ Enhanced error handling

### v1.0 (Legacy)

**Features:**
- Basic deployment orchestration
- Sequential execution
- Account-based state files
- Manual rollback

---

## Related Documentation

- [README.md](../README.md) - Complete platform documentation
- [WORKFLOW_ARCHITECTURE.md](../WORKFLOW_ARCHITECTURE.md) - GitHub Actions workflow design
- [accounts.yaml](../accounts.yaml) - Account configuration
- [deployment-rules.yaml](../deployment-rules.yaml) - Deployment rules

---

## Support & Contacts

**Team:** Platform Engineering  
**Owner:** DevOps Team  
**Slack:** #terraform-platform  
**Email:** devops@company.com

**Escalation Path:**
1. Check troubleshooting section above
2. Review audit logs in S3
3. Contact Platform Engineering team
4. Escalate to Cloud Architect

---

*Last Updated: December 12, 2025*  
*Document Version: 1.0*  
*Orchestrator Version: 2.0*
