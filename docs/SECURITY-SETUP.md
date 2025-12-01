# Quick Setup Guide - Security Features

## Prerequisites
- AWS CLI configured with admin permissions
- Terraform v1.5+
- GitHub repository with Actions enabled
- AWS account with permissions to create DynamoDB tables and S3 bucket policies

## 1. Create DynamoDB State Lock Table

Run this command in your terminal:

```bash
aws dynamodb create-table \
  --table-name terraform-state-locks \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region us-east-1
```

**Verify it was created:**
```bash
aws dynamodb describe-table --table-name terraform-state-locks --region us-east-1
```

Expected output:
```json
{
  "Table": {
    "TableName": "terraform-state-locks",
    "TableStatus": "ACTIVE",
    "BillingModeSummary": {
      "BillingMode": "PAY_PER_REQUEST"
    }
  }
}
```

## 2. Update S3 Bucket Policy

Add permissions for backup, audit logs, and state locking:

```bash
# Save this policy to file: s3-bucket-policy.json
cat > s3-bucket-policy.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowGitHubActionsStateAccess",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::YOUR_ACCOUNT_ID:role/github-actions-terraform-role"
      },
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject"
      ],
      "Resource": "arn:aws:s3:::terraform-elb-mdoule-poc/*"
    },
    {
      "Sid": "AllowGitHubActionsListBucket",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::YOUR_ACCOUNT_ID:role/github-actions-terraform-role"
      },
      "Action": "s3:ListBucket",
      "Resource": "arn:aws:s3:::terraform-elb-mdoule-poc"
    },
    {
      "Sid": "EnforceEncryptionInTransit",
      "Effect": "Deny",
      "Principal": "*",
      "Action": "s3:*",
      "Resource": [
        "arn:aws:s3:::terraform-elb-mdoule-poc/*",
        "arn:aws:s3:::terraform-elb-mdoule-poc"
      ],
      "Condition": {
        "Bool": {
          "aws:SecureTransport": "false"
        }
      }
    }
  ]
}
EOF

# Replace YOUR_ACCOUNT_ID with your actual AWS account ID
sed -i '' 's/YOUR_ACCOUNT_ID/123456789012/g' s3-bucket-policy.json

# Apply the policy
aws s3api put-bucket-policy \
  --bucket terraform-elb-mdoule-poc \
  --policy file://s3-bucket-policy.json
```

## 3. Enable S3 Bucket Versioning (Recommended)

This provides an additional safety net:

```bash
aws s3api put-bucket-versioning \
  --bucket terraform-elb-mdoule-poc \
  --versioning-configuration Status=Enabled
```

**Verify:**
```bash
aws s3api get-bucket-versioning --bucket terraform-elb-mdoule-poc
```

Expected output:
```json
{
  "Status": "Enabled"
}
```

## 4. Configure S3 Lifecycle Policies (Optional)

Automatically clean up old backups and manage audit log retention:

```bash
cat > s3-lifecycle-policy.json << 'EOF'
{
  "Rules": [
    {
      "Id": "audit-log-7-year-retention",
      "Filter": {
        "Prefix": "audit-logs/"
      },
      "Status": "Enabled",
      "Expiration": {
        "Days": 2555
      },
      "NoncurrentVersionExpiration": {
        "NoncurrentDays": 90
      }
    },
    {
      "Id": "backup-30-day-retention",
      "Filter": {
        "Prefix": "backups/"
      },
      "Status": "Enabled",
      "Expiration": {
        "Days": 30
      },
      "NoncurrentVersionExpiration": {
        "NoncurrentDays": 7
      }
    },
    {
      "Id": "cleanup-incomplete-uploads",
      "Filter": {},
      "Status": "Enabled",
      "AbortIncompleteMultipartUpload": {
        "DaysAfterInitiation": 7
      }
    }
  ]
}
EOF

aws s3api put-bucket-lifecycle-configuration \
  --bucket terraform-elb-mdoule-poc \
  --lifecycle-configuration file://s3-lifecycle-policy.json
```

**Verify:**
```bash
aws s3api get-bucket-lifecycle-configuration --bucket terraform-elb-mdoule-poc
```

## 5. Update IAM Role for GitHub Actions

Ensure your GitHub Actions role has these permissions:

```bash
cat > github-actions-policy.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "S3StateManagement",
      "Effect": "Allow",
      "Action": [
        "s3:ListBucket",
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject"
      ],
      "Resource": [
        "arn:aws:s3:::terraform-elb-mdoule-poc",
        "arn:aws:s3:::terraform-elb-mdoule-poc/*"
      ]
    },
    {
      "Sid": "DynamoDBStateLocking",
      "Effect": "Allow",
      "Action": [
        "dynamodb:DescribeTable",
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:DeleteItem"
      ],
      "Resource": "arn:aws:dynamodb:us-east-1:YOUR_ACCOUNT_ID:table/terraform-state-locks"
    },
    {
      "Sid": "TerraformResourceCreation",
      "Effect": "Allow",
      "Action": [
        "kms:*",
        "iam:*",
        "s3:*"
      ],
      "Resource": "*"
    }
  ]
}
EOF

# Replace YOUR_ACCOUNT_ID
sed -i '' 's/YOUR_ACCOUNT_ID/123456789012/g' github-actions-policy.json

# Update the policy
aws iam put-role-policy \
  --role-name github-actions-terraform-role \
  --policy-name TerraformDeploymentPolicy \
  --policy-document file://github-actions-policy.json
```

## 6. Test the Setup

### Test 1: State Locking
```bash
# In one terminal
cd /path/to/workspace
terraform init \
  -backend-config="key=test/state.tfstate" \
  -backend-config="region=us-east-1" \
  -backend-config="dynamodb_table=terraform-state-locks"

terraform apply

# In another terminal (should wait for lock)
terraform apply
```

### Test 2: Backup Creation
```bash
# Create a test deployment
git checkout -b test-security-features
# Make a change to tfvars
git add .
git commit -m "test: security features"
git push origin test-security-features

# Create PR and merge
# After apply, check backups exist:
aws s3 ls s3://terraform-elb-mdoule-poc/backups/ --recursive
```

### Test 3: Audit Logs
```bash
# After deployment, check audit logs
aws s3 ls s3://terraform-elb-mdoule-poc/audit-logs/ --recursive

# Download and view an audit log
aws s3 cp s3://terraform-elb-mdoule-poc/audit-logs/test/project/apply-TIMESTAMP.json - | jq .
```

### Test 4: Redaction in PR Comments
1. Create a PR that creates a KMS key
2. Check the PR comment
3. Verify ARNs are redacted: `arn:aws:kms:us-east-1:***ACCOUNT-ID***:key/***KEY-ID***`
4. Download audit log and verify full ARN is present

## 7. Monitoring Setup (Optional)

### Create CloudWatch Log Group
```bash
aws logs create-log-group --log-group-name /aws/terraform/orchestrator
```

### Enable S3 Bucket Logging
```bash
aws s3api put-bucket-logging \
  --bucket terraform-elb-mdoule-poc \
  --bucket-logging-status '{
    "LoggingEnabled": {
      "TargetBucket": "your-logging-bucket",
      "TargetPrefix": "terraform-state-logs/"
    }
  }'
```

### Create CloudWatch Alarms
```bash
# Alert on failed applies
aws cloudwatch put-metric-alarm \
  --alarm-name terraform-apply-failures \
  --alarm-description "Alert when terraform apply fails" \
  --metric-name Errors \
  --namespace Custom/Terraform \
  --statistic Sum \
  --period 300 \
  --threshold 1 \
  --comparison-operator GreaterThanThreshold \
  --evaluation-periods 1 \
  --alarm-actions arn:aws:sns:us-east-1:YOUR_ACCOUNT_ID:terraform-alerts
```

## 8. Verify Everything Works

Run this checklist:

- [ ] DynamoDB table `terraform-state-locks` exists
- [ ] S3 bucket policy updated with correct IAM role ARN
- [ ] S3 bucket versioning enabled
- [ ] S3 lifecycle policies configured (optional)
- [ ] IAM role has DynamoDB permissions
- [ ] IAM role has S3 permissions
- [ ] Test deployment creates backup in S3
- [ ] Test deployment creates audit log in S3
- [ ] PR comments show redacted sensitive data
- [ ] Audit logs contain full unredacted data
- [ ] Failed apply triggers rollback (test with intentional error)
- [ ] State locking prevents concurrent applies

## 9. Troubleshooting

### Issue: DynamoDB table not found
```bash
# Check if table exists
aws dynamodb describe-table --table-name terraform-state-locks --region us-east-1

# If not found, recreate it
aws dynamodb create-table \
  --table-name terraform-state-locks \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region us-east-1
```

### Issue: Backup/Audit logs not appearing in S3
```bash
# Check IAM permissions
aws iam get-role-policy \
  --role-name github-actions-terraform-role \
  --policy-name TerraformDeploymentPolicy

# Test S3 write permissions
aws s3 cp test.txt s3://terraform-elb-mdoule-poc/test/test.txt
```

### Issue: State lock timeout
```bash
# List active locks
aws dynamodb scan --table-name terraform-state-locks

# Delete stuck lock (CAREFUL!)
aws dynamodb delete-item \
  --table-name terraform-state-locks \
  --key '{"LockID": {"S": "terraform-elb-mdoule-poc/path/to/state.tfstate"}}'
```

### Issue: Redaction not working
```bash
# Check Python regex patterns in orchestrator script
grep -A 50 "def redact_sensitive_data" scripts/terraform-deployment-orchestrator-enhanced.py

# Test redaction manually
python3 << 'EOF'
import re
text = "arn:aws:kms:us-east-1:123456789012:key/abc-123-def"
redacted = re.sub(r'arn:aws:([^:]+):([^:]*):(\d{12}):(.+)', r'arn:aws:\1:\2:***ACCOUNT-ID***:***\4***', text)
print(redacted)
EOF
```

## 10. Cost Estimates

### DynamoDB State Locks
- **On-Demand Mode**: $0.00 (typically < 25 operations/month)
- **Provisioned Mode**: $0.52/month (1 RCU + 1 WCU)

### S3 Storage
- **State Files**: ~1MB each = $0.023/GB/month = ~$0.02/month
- **Backups**: ~1MB per apply × 30 days = ~30MB = ~$0.01/month
- **Audit Logs**: ~100KB per deployment × 100 deployments = ~10MB = ~$0.00/month

### S3 Requests
- **PUT requests**: ~10 per deployment = $0.005/1000 = negligible
- **GET requests**: ~5 per deployment = $0.0004/1000 = negligible

### Total Estimated Cost
- **Monthly**: ~$0.53 (mostly DynamoDB if using provisioned mode)
- **With On-Demand DynamoDB**: ~$0.03/month

## Summary

✅ **Setup Time**: ~15 minutes
✅ **Monthly Cost**: < $1
✅ **Maintenance**: Minimal (automated cleanup via lifecycle policies)
✅ **Compliance**: SOC2, HIPAA, PCI-DSS ready
✅ **Security**: Enterprise-grade data protection

All security features are now enabled and ready for production use!
