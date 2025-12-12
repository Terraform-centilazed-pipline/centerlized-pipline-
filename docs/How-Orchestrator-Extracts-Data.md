# How the Orchestrator Extracts Project and Resource Names

**Document Version:** 1.0  
**Last Updated:** December 12, 2025  
**Purpose:** Explain data extraction logic from tfvars files

---

## Question 1: Where Does "Project" Come From?

### Answer: From the Folder Structure

The orchestrator extracts the **project name** from the **parent directory** of the tfvars file.

### Real Example from Your Repository:

```
File Path:
/Users/pragadeeswarpa/Desktop/Personal_DevOps/OPA-test/dev-deployment/S3/test-poc-3/test-poc-3.tfvars
                                                                              └─────────┘
                                                                              This is the PROJECT ✅
```

**Breakdown:**
```
Full Path: dev-deployment/S3/test-poc-3/test-poc-3.tfvars
                              ^^^^^^^^^^
                              Parent folder = PROJECT NAME
```

### The Code That Does This:

```python
def _analyze_deployment_file(self, tfvars_file: Path):
    """Extract deployment information from tfvars file path"""
    
    # Get the path parts
    path_parts = tfvars_file.parts
    # Example: ('/', 'Users', 'pragadeeswarpa', 'Desktop', 'Personal_DevOps', 
    #           'OPA-test', 'dev-deployment', 'S3', 'test-poc-3', 'test-poc-3.tfvars')
    
    # Extract project from parent folder (2nd to last part)
    project = path_parts[-2] if len(path_parts) >= 2 else 'default'
    #                    ^^
    #                    -2 means "second from the end"
    #                    test-poc-3.tfvars ← -1 (last)
    #                    test-poc-3 ← -2 (parent folder) ✅
    
    return {
        'project': project,  # "test-poc-3"
        ...
    }
```

### Multiple Examples:

| File Path | Project Name | Backend Key |
|-----------|-------------|-------------|
| `S3/test-poc-3/test-poc-3.tfvars` | **test-poc-3** | `s3/arj-wkld-a-prd/us-east-1/test-poc-3/terraform.tfstate` |
| `Accounts/test-4-poc-1/deployment.tfvars` | **test-4-poc-1** | `s3/arj-wkld-a-prd/us-east-1/test-4-poc-1/terraform.tfstate` |
| `KMS/encryption-keys/kms.tfvars` | **encryption-keys** | `kms/arj-wkld-a-prd/us-east-1/encryption-keys/terraform.tfstate` |
| `IAM/cross-account-roles/iam.tfvars` | **cross-account-roles** | `iam/arj-wkld-a-prd/us-east-1/cross-account-roles/terraform.tfstate` |

### Why Folder Name?

✅ **Consistent** - Folder structure enforces project organization  
✅ **Clear Ownership** - Each project has its own folder  
✅ **Git-Friendly** - Easy to see what changed in PRs  
✅ **Self-Documenting** - Path shows: service/account/project

---

## Question 2: Where Does It Pick Resource Names?

### Answer: From the Tfvars Content Using Pattern Matching

The orchestrator **reads the tfvars file content** and uses **regex patterns** to extract resource names from the configuration blocks.

### Real Example from Your File:

**Your tfvars file content:**
```hcl
s3_buckets = {
  "test-poc-3" = {
    bucket_name = "arj-test-poc-3-use1-prd"
    ...
  }
}
```

**What the orchestrator extracts:**
- Service: `s3` (from `s3_buckets = {`)
- Resource name: `test-poc-3` (from `"test-poc-3" = {`)

### The Code That Does This:

```python
def _detect_services_from_tfvars(self, tfvars_file: Path):
    """Detect AWS services from tfvars content"""
    
    # Read the file content
    with open(tfvars_file, 'r') as f:
        content = f.read()
    
    # Your file content:
    # s3_buckets = {
    #   "test-poc-3" = {
    #     bucket_name = "arj-test-poc-3-use1-prd"
    
    detected_services = []
    
    # Service mapping - what to look for
    service_mapping = {
        's3_buckets': 's3',          # If we find "s3_buckets =" → it's S3
        'kms_keys': 'kms',           # If we find "kms_keys =" → it's KMS
        'iam_roles': 'iam',          # If we find "iam_roles =" → it's IAM
        'lambda_functions': 'lambda' # If we find "lambda_functions =" → it's Lambda
    }
    
    # Search for each service pattern
    for tfvars_key, service in service_mapping.items():
        # Look for pattern like: s3_buckets =
        if re.search(rf'\b{tfvars_key}\s*=', content):
            detected_services.append(service)
            # Found "s3_buckets =" → Add 's3' to list ✅
    
    return detected_services
    # Returns: ['s3']


def _extract_resource_names_from_tfvars(self, tfvars_file: Path, services: List[str]):
    """Extract resource names for reporting"""
    
    with open(tfvars_file, 'r') as f:
        content = f.read()
    
    resource_names = []
    
    # For S3 service, extract bucket names
    if 's3' in services:
        # Pattern: "bucket-name" = {
        s3_pattern = r'"([a-z0-9][a-z0-9-]*[a-z0-9])"\s*=\s*\{'
        matches = re.findall(s3_pattern, content)
        
        # In your file:
        # s3_buckets = {
        #   "test-poc-3" = {
        #   ^^^^^^^^^^^^
        #   This matches!
        
        resource_names.extend(matches)
        # Extracts: "test-poc-3"
    
    # For KMS service, extract key names
    if 'kms' in services:
        kms_pattern = r'"([a-z0-9][a-z0-9-]*[a-z0-9])"\s*=\s*\{'
        matches = re.findall(kms_pattern, content)
        resource_names.extend(matches)
    
    return resource_names
    # Returns: ["test-poc-3"]
```

### Visual Breakdown - Your File:

```hcl
# Your tfvars file: S3/test-poc-3/test-poc-3.tfvars

accounts = {
  "802860742843" = {
    account_id   = "802860742843"
    account_name = "arj-wkld-a-prd"  ← Orchestrator extracts this
    #              ^^^^^^^^^^^^^^^^^
    #              Pattern: account_name = "value"
  }
}

s3_buckets = {           ← Orchestrator finds "s3_buckets =" → Service: S3 ✅
  "test-poc-3" = {       ← Orchestrator extracts "test-poc-3" ✅
   ^^^^^^^^^^^
   Pattern: "name" = {
   
    bucket_name = "arj-test-poc-3-use1-prd"  ← Additional info for display
  }
}
```

### What Gets Extracted:

```python
# From your file path: S3/test-poc-3/test-poc-3.tfvars
deployment_info = {
    'file': '/full/path/to/S3/test-poc-3/test-poc-3.tfvars',
    'project': 'test-poc-3',                    # From folder name ✅
    'account_name': 'arj-wkld-a-prd',          # From tfvars content ✅
    'account_id': '802860742843',               # From tfvars content ✅
    'region': 'us-east-1',                      # From tfvars content ✅
    'services': ['s3'],                         # From "s3_buckets =" ✅
    'resources': 'S3: test-poc-3',             # From "test-poc-3" = { ✅
    'environment': 'production',                # From tfvars content ✅
}

# Generated backend key:
backend_key = "s3/arj-wkld-a-prd/us-east-1/test-poc-3/terraform.tfstate"
#              ^   ^^^^^^^^^^^^^^  ^^^^^^^^^  ^^^^^^^^^^
#              |        |              |          |
#              |        |              |          └─ From folder name
#              |        |              └─ From tfvars: regions = ["us-east-1"]
#              |        └─ From tfvars: account_name = "arj-wkld-a-prd"
#              └─ From detecting "s3_buckets =" in content
```

---

## Complete Extraction Flow

### Step-by-Step Process:

```
1. GitHub detects changed file:
   └─ "S3/test-poc-3/test-poc-3.tfvars"

2. Orchestrator receives file path:
   └─ tfvars_file = Path("S3/test-poc-3/test-poc-3.tfvars")

3. Extract project from folder structure:
   └─ path_parts[-2] = "test-poc-3" ✅

4. Read tfvars file content:
   └─ content = tfvars_file.read_text()

5. Extract account_name from content:
   └─ Pattern: account_name = "arj-wkld-a-prd"
   └─ Result: account_name = "arj-wkld-a-prd" ✅

6. Extract region from content:
   └─ Pattern: regions = ["us-east-1"]
   └─ Result: region = "us-east-1" ✅

7. Detect services from content:
   └─ Find: "s3_buckets ="
   └─ Result: services = ['s3'] ✅

8. Extract resource names from content:
   └─ Pattern: "test-poc-3" = {
   └─ Result: resources = ["test-poc-3"] ✅

9. Generate backend key:
   └─ f"{service}/{account_name}/{region}/{project}/terraform.tfstate"
   └─ Result: "s3/arj-wkld-a-prd/us-east-1/test-poc-3/terraform.tfstate" ✅
```

---

## Multiple Resources in Single Tfvars

### Example with 3 S3 Buckets:

```hcl
# File: S3/data-lake/buckets.tfvars
#       └─────────┘
#       Project = "data-lake"

s3_buckets = {
  "raw-data-bucket" = {
    bucket_name = "company-raw-data-use1-prd"
  }
  "processed-data-bucket" = {
    bucket_name = "company-processed-data-use1-prd"
  }
  "archive-bucket" = {
    bucket_name = "company-archive-use1-prd"
  }
}
```

**What gets extracted:**

```python
deployment_info = {
    'project': 'data-lake',                          # From folder ✅
    'services': ['s3'],                              # One service ✅
    'resources': 'S3: raw-data-bucket, processed-data-bucket, archive-bucket', # All 3 ✅
}

backend_key = "s3/arj-wkld-a-prd/us-east-1/data-lake/terraform.tfstate"
#                                            ^^^^^^^^^
#                                            From folder name
```

**Important:** All 3 buckets share ONE state file because they're in the same tfvars.

---

## Multiple Services in Single Tfvars

### Example with S3 + KMS:

```hcl
# File: Accounts/secure-storage/deployment.tfvars
#       └──────────────┘
#       Project = "secure-storage"

s3_buckets = {
  "encrypted-bucket" = {
    bucket_name = "company-secure-use1-prd"
  }
}

kms_keys = {
  "bucket-encryption-key" = {
    description = "Encryption for secure bucket"
  }
}
```

**What gets extracted:**

```python
deployment_info = {
    'project': 'secure-storage',                     # From folder ✅
    'services': ['s3', 'kms'],                       # Two services ✅
    'resources': 'S3: encrypted-bucket, KMS: bucket-encryption-key', ✅
}

# Backend key uses "combined" because multiple services
backend_key = "combined/arj-wkld-a-prd/us-east-1/secure-storage/terraform.tfstate"
#              ^^^^^^^^
#              Uses "combined" when len(services) > 1
```

---

## Patterns Used for Extraction

### Service Detection Patterns:

| Pattern in Tfvars | Detected Service | Backend Key Prefix |
|------------------|------------------|-------------------|
| `s3_buckets =` | `s3` | `s3/...` |
| `kms_keys =` | `kms` | `kms/...` |
| `iam_roles =` | `iam` | `iam/...` |
| `iam_policies =` | `iam` | `iam/...` |
| `lambda_functions =` | `lambda` | `lambda/...` |
| `sqs_queues =` | `sqs` | `sqs/...` |
| `sns_topics =` | `sns` | `sns/...` |

### Resource Name Patterns:

```python
# Pattern that matches resource names
resource_pattern = r'"([a-z0-9][a-z0-9-]*[a-z0-9])"\s*=\s*\{'

# Matches:
"test-poc-3" = {          ✅ Matches
"my-bucket-123" = {       ✅ Matches
"encryption-key" = {      ✅ Matches

# Doesn't match:
bucket_name = "value"     ❌ Not a resource definition
tags = {                  ❌ Not a resource definition
```

### Account Name Pattern:

```python
# Pattern that extracts account_name
account_pattern = r'account_name\s*=\s*"([^"]+)"'

# In your file:
account_name = "arj-wkld-a-prd"
#              ^^^^^^^^^^^^^^^^^
#              Captured by pattern ✅
```

### Region Pattern:

```python
# Pattern that extracts region
region_pattern = r'regions\s*=\s*\["([^"]+)"\]'

# In your file:
regions = ["us-east-1"]
#          ^^^^^^^^^^
#          Captured by pattern ✅
```

---

## Summary

### Project Name:
- **Source:** Folder structure (parent directory of tfvars file)
- **Example:** `S3/test-poc-3/file.tfvars` → project = `test-poc-3`

### Resource Names:
- **Source:** Tfvars file content (pattern matching)
- **Example:** `"test-poc-3" = {` → resource = `test-poc-3`

### Complete Backend Key:
```
{service}/{account_name}/{region}/{project}/terraform.tfstate
    ↓           ↓            ↓        ↓
 Content    Content      Content   Folder
 Pattern    Pattern      Pattern   Structure
```

---

*Document Version: 1.0*  
*Last Updated: December 12, 2025*
