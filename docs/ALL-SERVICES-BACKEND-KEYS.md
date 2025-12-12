# Backend Key Examples - All AWS Services

## The Backend Key Works for ALL Services

The system automatically detects the service from your tfvars and generates the correct backend key.

---

## ✅ S3 Buckets

**Tfvars:**
```hcl
project = "my-app"
s3_buckets = {
  "data-bucket" = { bucket_name = "arj-data-prd" }
}
```

**Backend Key:**
```
s3/arj-wkld-a-prd/us-east-1/my-app/data-bucket/terraform.tfstate
^^^ Service auto-detected from 's3_buckets'
```

---

## ✅ IAM Roles

**Tfvars:**
```hcl
project = "my-app"
iam_roles = {
  "admin-role" = { 
    role_name = "arj-admin-role"
    assume_role_policy = "..."
  }
}
```

**Backend Key:**
```
iam/arj-wkld-a-prd/us-east-1/my-app/admin-role/terraform.tfstate
^^^ Service auto-detected from 'iam_roles'
```

---

## ✅ KMS Keys

**Tfvars:**
```hcl
project = "encryption"
kms_keys = {
  "data-key" = {
    alias = "alias/data-encryption"
    description = "Data encryption key"
  }
}
```

**Backend Key:**
```
kms/arj-wkld-a-prd/us-east-1/encryption/data-key/terraform.tfstate
^^^ Service auto-detected from 'kms_keys'
```

---

## ✅ Lambda Functions

**Tfvars:**
```hcl
project = "api-backend"
lambda_functions = {
  "api-handler" = {
    function_name = "arj-api-handler"
    runtime = "python3.9"
  }
}
```

**Backend Key:**
```
lambda/arj-wkld-a-prd/us-east-1/api-backend/api-handler/terraform.tfstate
^^^^^^ Service auto-detected from 'lambda_functions'
```

---

## ✅ DynamoDB Tables

**Tfvars:**
```hcl
project = "user-data"
dynamodb_tables = {
  "users-table" = {
    table_name = "arj-users"
    hash_key = "userId"
  }
}
```

**Backend Key:**
```
dynamodb/arj-wkld-a-prd/us-east-1/user-data/users-table/terraform.tfstate
^^^^^^^^ Service auto-detected from 'dynamodb_tables'
```

---

## ✅ RDS Instances

**Tfvars:**
```hcl
project = "database"
rds_instances = {
  "main-db" = {
    instance_class = "db.t3.micro"
    engine = "postgres"
  }
}
```

**Backend Key:**
```
rds/arj-wkld-a-prd/us-east-1/database/main-db/terraform.tfstate
^^^ Service auto-detected from 'rds_instances'
```

---

## ✅ VPC Configuration

**Tfvars:**
```hcl
project = "network"
vpc_configs = {
  "main-vpc" = {
    cidr_block = "10.0.0.0/16"
  }
}
```

**Backend Key:**
```
vpc/arj-wkld-a-prd/us-east-1/network/main-vpc/terraform.tfstate
^^^ Service auto-detected from 'vpc_configs'
```

---

## ✅ SNS Topics

**Tfvars:**
```hcl
project = "notifications"
sns_topics = {
  "alerts-topic" = {
    topic_name = "arj-alerts"
  }
}
```

**Backend Key:**
```
sns/arj-wkld-a-prd/us-east-1/notifications/alerts-topic/terraform.tfstate
^^^ Service auto-detected from 'sns_topics'
```

---

## ✅ SQS Queues

**Tfvars:**
```hcl
project = "message-queue"
sqs_queues = {
  "job-queue" = {
    queue_name = "arj-job-queue"
  }
}
```

**Backend Key:**
```
sqs/arj-wkld-a-prd/us-east-1/message-queue/job-queue/terraform.tfstate
^^^ Service auto-detected from 'sqs_queues'
```

---

## ✅ CloudWatch Alarms

**Tfvars:**
```hcl
project = "monitoring"
cloudwatch_alarms = {
  "cpu-alarm" = {
    alarm_name = "arj-high-cpu"
  }
}
```

**Backend Key:**
```
cloudwatch/arj-wkld-a-prd/us-east-1/monitoring/cpu-alarm/terraform.tfstate
^^^^^^^^^^ Service auto-detected from 'cloudwatch_alarms'
```

---

## ✅ API Gateway

**Tfvars:**
```hcl
project = "rest-api"
api_gateways = {
  "main-api" = {
    api_name = "arj-main-api"
  }
}
```

**Backend Key:**
```
apigateway/arj-wkld-a-prd/us-east-1/rest-api/main-api/terraform.tfstate
^^^^^^^^^^ Service auto-detected from 'api_gateways'
```

---

## 🔀 Multiple Resources (Same Service)

**Example: 3 Lambda Functions**

**Tfvars:**
```hcl
project = "microservices"
lambda_functions = {
  "auth-function"    = { ... }
  "data-function"    = { ... }
  "process-function" = { ... }
}
```

**Backend Key:**
```
lambda/arj-wkld-a-prd/us-east-1/microservices/terraform.tfstate
                                               ^^^^^^^^^^^^^^^^^ No subfolder needed!
```

---

## 🔀 Multiple Services (Different Types)

**Example: S3 + Lambda + IAM**

**Tfvars:**
```hcl
project = "data-pipeline"

s3_buckets = {
  "input-bucket" = { ... }
}

lambda_functions = {
  "processor" = { ... }
}

iam_roles = {
  "lambda-role" = { ... }
}
```

**Backend Key:**
```
multi/arj-wkld-a-prd/us-east-1/data-pipeline/iam-lambda-s3/terraform.tfstate
^^^^^                                         ^^^^^^^^^^^^^^ Shows which services!
```

---

## Complete Service Mapping

The orchestrator supports these tfvars keys:

| Tfvars Key | Service | Example Backend Key |
|------------|---------|---------------------|
| `s3_buckets` | s3 | `s3/.../project/bucket-name/...` |
| `kms_keys` | kms | `kms/.../project/key-name/...` |
| `iam_roles` | iam | `iam/.../project/role-name/...` |
| `iam_policies` | iam | `iam/.../project/policy-name/...` |
| `iam_users` | iam | `iam/.../project/user-name/...` |
| `lambda_functions` | lambda | `lambda/.../project/function-name/...` |
| `dynamodb_tables` | dynamodb | `dynamodb/.../project/table-name/...` |
| `rds_instances` | rds | `rds/.../project/db-name/...` |
| `rds_clusters` | rds | `rds/.../project/cluster-name/...` |
| `ec2_instances` | ec2 | `ec2/.../project/instance-name/...` |
| `vpc_configs` | vpc | `vpc/.../project/vpc-name/...` |
| `security_groups` | vpc | `vpc/.../project/sg-name/...` |
| `sns_topics` | sns | `sns/.../project/topic-name/...` |
| `sqs_queues` | sqs | `sqs/.../project/queue-name/...` |
| `cloudwatch_alarms` | cloudwatch | `cloudwatch/.../project/alarm-name/...` |
| `api_gateways` | apigateway | `apigateway/.../project/api-name/...` |

---

## Key Patterns Work for All Services

### Single Resource
```
{service}/.../project/{resource-name}/terraform.tfstate
```

**Works for:**
- `s3/.../project/my-bucket/terraform.tfstate`
- `iam/.../project/my-role/terraform.tfstate`
- `lambda/.../project/my-function/terraform.tfstate`

### Multiple Resources (Same Service)
```
{service}/.../project/terraform.tfstate
```

**Works for:**
- `s3/.../project/terraform.tfstate` (any number of S3 buckets)
- `iam/.../project/terraform.tfstate` (any number of IAM roles)
- `lambda/.../project/terraform.tfstate` (any number of Lambda functions)
- `dynamodb/.../project/terraform.tfstate` (any number of DynamoDB tables)

### Multiple Services
```
multi/.../project/{service1-service2-service3}/terraform.tfstate
```

**Works for:**
- S3 + IAM → `multi/.../project/iam-s3/terraform.tfstate`
- Lambda + DynamoDB + IAM → `multi/.../project/dynamodb-iam-lambda/terraform.tfstate`
- VPC + EC2 + SG → `multi/.../project/ec2-vpc/terraform.tfstate`
- Any combination (services listed alphabetically)

---

## Summary

✅ **System supports 20+ AWS services automatically**
✅ **Service detected from tfvars key (s3_buckets, iam_roles, etc.)**
✅ **Same rules apply to all services:**
  - 1 resource → `{service}/.../project/resource-name/terraform.tfstate`
  - Multiple same service → `{service}/.../project/terraform.tfstate`
  - Multiple services → `multi/.../project/{service1-service2}/terraform.tfstate`

✅ **No special configuration needed - just use the right tfvars key!**
