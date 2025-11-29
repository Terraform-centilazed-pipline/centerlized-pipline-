## Terraform Plan: arj-wkld-a-prd/test-4-poc-1

**Backend Key:** `s3/arj-wkld-a-prd/us-east-1/test-4-poc-1/terraform.tfstate`

**Services:** s3

```terraform

Terraform used the selected providers to generate the following execution
plan. Resource actions are indicated with the following symbols:
  [32m+[0m create[0m

Terraform will perform the following actions:

[1m  # module.s3[0].aws_s3_bucket.buckets["test-4-poc-1"][0m will be created
[0m  [32m+[0m[0m resource "aws_s3_bucket" "buckets" {
      [32m+[0m[0m acceleration_status         = (known after apply)
      [32m+[0m[0m acl                         = (known after apply)
      [32m+[0m[0m arn                         = (known after apply)
      [32m+[0m[0m bucket                      = "arj-test-4-poc-1-use1-prd"
      [32m+[0m[0m bucket_domain_name          = (known after apply)
      [32m+[0m[0m bucket_prefix               = (known after apply)
      [32m+[0m[0m bucket_region               = (known after apply)
      [32m+[0m[0m bucket_regional_domain_name = (known after apply)
      [32m+[0m[0m force_destroy               = false
      [32m+[0m[0m hosted_zone_id              = (known after apply)
      [32m+[0m[0m id                          = (known after apply)
      [32m+[0m[0m object_lock_enabled         = (known after apply)
      [32m+[0m[0m policy                      = (known after apply)
      [32m+[0m[0m region                      = "us-east-1"
      [32m+[0m[0m request_payer               = (known after apply)
      [32m+[0m[0m tags                        = {
          [32m+[0m[0m "AccessType"  = "vpc-endpoint-only"
          [32m+[0m[0m "Account"     = "802860742843"
          [32m+[0m[0m "Environment" = "production"
          [32m+[0m[0m "ManagedBy"   = "terraform"
          [32m+[0m[0m "Name"        = "arj-test-4-poc-1-use1-prd"
          [32m+[0m[0m "Owner"       = "pra"
          [32m+[0m[0m "Project"     = "test-4-poc-1"
          [32m+[0m[0m "Region"      = "us-east-1"
          [32m+[0m[0m "VPCAccess"   = "true"
        }
      [32m+[0m[0m tags_all                    = {
          [32m+[0m[0m "AccessType"  = "vpc-endpoint-only"
          [32m+[0m[0m "Account"     = "802860742843"
          [32m+[0m[0m "Environment" = "production"
          [32m+[0m[0m "ManagedBy"   = "terraform"
          [32m+[0m[0m "Name"        = "arj-test-4-poc-1-use1-prd"
          [32m+[0m[0m "Owner"       = "pra"
          [32m+[0m[0m "Project"     = "test-4-poc-1"
          [32m+[0m[0m "Region"      = "us-east-1"
          [32m+[0m[0m "VPCAccess"   = "true"
        }
      [32m+[0m[0m website_domain              = (known after apply)
      [32m+[0m[0m website_endpoint            = (known after apply)

      [32m+[0m[0m cors_rule (known after apply)

      [32m+[0m[0m grant (known after apply)

      [32m+[0m[0m lifecycle_rule (known after apply)

      [32m+[0m[0m logging (known after apply)

      [32m+[0m[0m object_lock_configuration (known after apply)

      [32m+[0m[0m replication_configuration (known after apply)

      [32m+[0m[0m server_side_encryption_configuration (known after apply)

      [32m+[0m[0m versioning (known after apply)

      [32m+[0m[0m website (known after apply)
    }

[1m  # module.s3[0].aws_s3_bucket_lifecycle_configuration.lifecycle["test-4-poc-1"][0m will be created
[0m  [32m+[0m[0m resource "aws_s3_bucket_lifecycle_configuration" "lifecycle" {
      [32m+[0m[0m bucket                                 = (known after apply)
      [32m+[0m[0m expected_bucket_owner                  = (known after apply)
      [32m+[0m[0m id                                     = (known after apply)
      [32m+[0m[0m region                                 = "us-east-1"
      [32m+[0m[0m transition_default_minimum_object_size = "all_storage_classes_128K"

      [32m+[0m[0m rule {
          [32m+[0m[0m id     = "intelligent-tiering-default"
          [32m+[0m[0m status = "Enabled"
            [90m# (1 unchanged attribute hidden)[0m[0m

          [32m+[0m[0m filter {
                [90m# (1 unchanged attribute hidden)[0m[0m
            }

          [32m+[0m[0m transition {
              [32m+[0m[0m days          = 0
              [32m+[0m[0m storage_class = "INTELLIGENT_TIERING"
            }
        }
    }

[1m  # module.s3[0].aws_s3_bucket_policy.bucket_policies["test-4-poc-1"][0m will be created
[0m  [32m+[0m[0m resource "aws_s3_bucket_policy" "bucket_policies" {
      [32m+[0m[0m bucket = (known after apply)
      [32m+[0m[0m id     = (known after apply)
      [32m+[0m[0m policy = jsonencode(
            {
              [32m+[0m[0m Statement = [
                  [32m+[0m[0m {
                      [32m+[0m[0m Action    = [
                          [32m+[0m[0m "s3:PutObject",
                          [32m+[0m[0m "s3:GetObject",
                          [32m+[0m[0m "s3:DeleteObject",
                        ]
                      [32m+[0m[0m Condition = {
                          [32m+[0m[0m ArnNotLike = {
                              [32m+[0m[0m "aws:PrincipalArn" = "arn:aws:iam::802860742843:role/TerraformExecutionRole"
                            }
                        }
                      [32m+[0m[0m Effect    = "Deny"
                      [32m+[0m[0m Principal = "*"
                      [32m+[0m[0m Resource  = [
                          [32m+[0m[0m "arn:aws:s3:::arj-test-4-poc-1-use1-prd/*",
                          [32m+[0m[0m "arn:aws:s3:::arj-test-4-poc-1-use1-prd",
                        ]
                    },
                  [32m+[0m[0m {
                      [32m+[0m[0m Action    = [
                          [32m+[0m[0m "s3:PutObject",
                          [32m+[0m[0m "s3:GetObject",
                          [32m+[0m[0m "s3:DeleteObject",
                        ]
                      [32m+[0m[0m Condition = {
                          [32m+[0m[0m StringNotEquals = {
                              [32m+[0m[0m "aws:SourceVpce" = [
                                  [32m+[0m[0m "vpce-use1-interface-s3-shared",
                                  [32m+[0m[0m "vpce-useast1-gateway-XXXXXXXX",
                                ]
                            }
                        }
                      [32m+[0m[0m Effect    = "Deny"
                      [32m+[0m[0m Principal = "*"
                      [32m+[0m[0m Resource  = [
                          [32m+[0m[0m "arn:aws:s3:::arj-test-4-poc-1-use1-prd/*",
                          [32m+[0m[0m "arn:aws:s3:::arj-test-4-poc-1-use1-prd",
                        ]
                    },
                  [32m+[0m[0m {
                      [32m+[0m[0m Action    = "s3:PutObject"
                      [32m+[0m[0m Condition = {
                          [32m+[0m[0m StringNotEquals = {
                              [32m+[0m[0m "s3:x-amz-server-side-encryption-aws-kms-key-id" = "arn:aws:kms:us-east-1:802860742843:key/e978f725-a300-4993-9c85-1b2767982749"
                            }
                        }
                      [32m+[0m[0m Effect    = "Deny"
                      [32m+[0m[0m Principal = "*"
                      [32m+[0m[0m Resource  = "arn:aws:s3:::arj-test-4-poc-1-use1-prd/*"
                      [32m+[0m[0m Sid       = "DenyEncryptionHeaderWithoutAWSKMS"
                    },
                ]
              [32m+[0m[0m Version   = "2012-10-17"
            }
        )
      [32m+[0m[0m region = "us-east-1"
    }

[1m  # module.s3[0].aws_s3_bucket_server_side_encryption_configuration.encryption["test-4-poc-1"][0m will be created
[0m  [32m+[0m[0m resource "aws_s3_bucket_server_side_encryption_configuration" "encryption" {
      [32m+[0m[0m bucket = (known after apply)
      [32m+[0m[0m id     = (known after apply)
      [32m+[0m[0m region = "us-east-1"

      [32m+[0m[0m rule {
          [32m+[0m[0m blocked_encryption_types = []
          [32m+[0m[0m bucket_key_enabled       = true

          [32m+[0m[0m apply_server_side_encryption_by_default {
              [32m+[0m[0m kms_master_key_id = "arn:aws:kms:us-east-1:802860742843:key/e978f725-a300-4993-9c85-1b2767982749"
              [32m+[0m[0m sse_algorithm     = "aws:kms"
            }
        }
    }

[1m  # module.s3[0].aws_s3_bucket_versioning.versioning["test-4-poc-1"][0m will be created
[0m  [32m+[0m[0m resource "aws_s3_bucket_versioning" "versioning" {
      [32m+[0m[0m bucket = (known after apply)
      [32m+[0m[0m id     = (known after apply)
      [32m+[0m[0m region = "us-east-1"

      [32m+[0m[0m versioning_configuration {
          [32m+[0m[0m mfa_delete = (known after apply)
          [32m+[0m[0m status     = "Enabled"
        }
    }

[1mPlan:[0m 5 to add, 0 to change, 0 to destroy.
[0m
Changes to Outputs:
  [32m+[0m[0m bucket_encryption          = {
      [32m+[0m[0m test-4-poc-1 = {
          [32m+[0m[0m id   = (known after apply)
          [32m+[0m[0m rule = [
              [32m+[0m[0m {
                  [32m+[0m[0m apply_server_side_encryption_by_default = [
                      [32m+[0m[0m {
                          [32m+[0m[0m kms_master_key_id = "arn:aws:kms:us-east-1:802860742843:key/e978f725-a300-4993-9c85-1b2767982749"
                          [32m+[0m[0m sse_algorithm     = "aws:kms"
                        },
                    ]
                  [32m+[0m[0m blocked_encryption_types                = []
                  [32m+[0m[0m bucket_key_enabled                      = true
                },
            ]
        }
    }
  [32m+[0m[0m bucket_lifecycle           = {
      [32m+[0m[0m test-4-poc-1 = {
          [32m+[0m[0m id   = (known after apply)
          [32m+[0m[0m rule = [
              [32m+[0m[0m {
                  [32m+[0m[0m abort_incomplete_multipart_upload = []
                  [32m+[0m[0m expiration                        = []
                  [32m+[0m[0m filter                            = [
                      [32m+[0m[0m {
                          [32m+[0m[0m and                      = []
                          [32m+[0m[0m object_size_greater_than = [90mnull[0m[0m
                          [32m+[0m[0m object_size_less_than    = [90mnull[0m[0m
                          [32m+[0m[0m prefix                   = ""
                          [32m+[0m[0m tag                      = []
                        },
                    ]
                  [32m+[0m[0m id                                = "intelligent-tiering-default"
                  [32m+[0m[0m noncurrent_version_expiration     = []
                  [32m+[0m[0m noncurrent_version_transition     = []
                  [32m+[0m[0m prefix                            = ""
                  [32m+[0m[0m status                            = "Enabled"
                  [32m+[0m[0m transition                        = [
                      [32m+[0m[0m {
                          [32m+[0m[0m date          = [90mnull[0m[0m
                          [32m+[0m[0m days          = 0
                          [32m+[0m[0m storage_class = "INTELLIGENT_TIERING"
                        },
                    ]
                },
            ]
        }
    }
  [32m+[0m[0m bucket_policies            = {
      [32m+[0m[0m test-4-poc-1 = {
          [32m+[0m[0m id     = (known after apply)
          [32m+[0m[0m policy = jsonencode(
                {
                  [32m+[0m[0m Statement = [
                      [32m+[0m[0m {
                          [32m+[0m[0m Action    = [
                              [32m+[0m[0m "s3:PutObject",
                              [32m+[0m[0m "s3:GetObject",
                              [32m+[0m[0m "s3:DeleteObject",
                            ]
                          [32m+[0m[0m Condition = {
                              [32m+[0m[0m ArnNotLike = {
                                  [32m+[0m[0m "aws:PrincipalArn" = "arn:aws:iam::802860742843:role/TerraformExecutionRole"
                                }
                            }
                          [32m+[0m[0m Effect    = "Deny"
                          [32m+[0m[0m Principal = "*"
                          [32m+[0m[0m Resource  = [
                              [32m+[0m[0m "arn:aws:s3:::arj-test-4-poc-1-use1-prd/*",
                              [32m+[0m[0m "arn:aws:s3:::arj-test-4-poc-1-use1-prd",
                            ]
                        },
                      [32m+[0m[0m {
                          [32m+[0m[0m Action    = [
                              [32m+[0m[0m "s3:PutObject",
                              [32m+[0m[0m "s3:GetObject",
                              [32m+[0m[0m "s3:DeleteObject",
                            ]
                          [32m+[0m[0m Condition = {
                              [32m+[0m[0m StringNotEquals = {
                                  [32m+[0m[0m "aws:SourceVpce" = [
                                      [32m+[0m[0m "vpce-use1-interface-s3-shared",
                                      [32m+[0m[0m "vpce-useast1-gateway-XXXXXXXX",
                                    ]
                                }
                            }
                          [32m+[0m[0m Effect    = "Deny"
                          [32m+[0m[0m Principal = "*"
                          [32m+[0m[0m Resource  = [
                              [32m+[0m[0m "arn:aws:s3:::arj-test-4-poc-1-use1-prd/*",
                              [32m+[0m[0m "arn:aws:s3:::arj-test-4-poc-1-use1-prd",
                            ]
                        },
                      [32m+[0m[0m {
                          [32m+[0m[0m Action    = "s3:PutObject"
                          [32m+[0m[0m Condition = {
                              [32m+[0m[0m StringNotEquals = {
                                  [32m+[0m[0m "s3:x-amz-server-side-encryption-aws-kms-key-id" = "arn:aws:kms:us-east-1:802860742843:key/e978f725-a300-4993-9c85-1b2767982749"
                                }
                            }
                          [32m+[0m[0m Effect    = "Deny"
                          [32m+[0m[0m Principal = "*"
                          [32m+[0m[0m Resource  = "arn:aws:s3:::arj-test-4-poc-1-use1-prd/*"
                          [32m+[0m[0m Sid       = "DenyEncryptionHeaderWithoutAWSKMS"
                        },
                    ]
                  [32m+[0m[0m Version   = "2012-10-17"
                }
            )
        }
    }
  [32m+[0m[0m bucket_versioning          = {
      [32m+[0m[0m test-4-poc-1 = {
          [32m+[0m[0m id                       = (known after apply)
          [32m+[0m[0m versioning_configuration = [
              [32m+[0m[0m {
                  [32m+[0m[0m mfa_delete = (known after apply)
                  [32m+[0m[0m status     = "Enabled"
                },
            ]
        }
    }
  [32m+[0m[0m deployment_summary         = {
      [32m+[0m[0m account_id   = "802860742843"
      [32m+[0m[0m deployed_at  = (known after apply)
      [32m+[0m[0m iam_policies = 0
      [32m+[0m[0m iam_roles    = 0
      [32m+[0m[0m iam_users    = 0
      [32m+[0m[0m kms_keys     = 0
      [32m+[0m[0m region       = "us-east-1"
      [32m+[0m[0m s3_buckets   = 1
    }
  [32m+[0m[0m resource_map               = {
      [32m+[0m[0m iam_roles  = {}
      [32m+[0m[0m iam_users  = {}
      [32m+[0m[0m kms_keys   = {}
      [32m+[0m[0m s3_buckets = {
          [32m+[0m[0m test-4-poc-1 = {
              [32m+[0m[0m arn = (known after apply)
              [32m+[0m[0m id  = (known after apply)
            }
        }
    }
  [32m+[0m[0m s3_bucket_arns             = {
      [32m+[0m[0m test-4-poc-1 = (known after apply)
    }
  [32m+[0m[0m s3_bucket_domains          = {
      [32m+[0m[0m test-4-poc-1 = (known after apply)
    }
  [32m+[0m[0m s3_bucket_names            = {
      [32m+[0m[0m test-4-poc-1 = (known after apply)
    }
  [32m+[0m[0m s3_buckets                 = {
      [32m+[0m[0m test-4-poc-1 = {
          [32m+[0m[0m arn                         = (known after apply)
          [32m+[0m[0m bucket_domain_name          = (known after apply)
          [32m+[0m[0m bucket_regional_domain_name = (known after apply)
          [32m+[0m[0m hosted_zone_id              = (known after apply)
          [32m+[0m[0m id                          = (known after apply)
          [32m+[0m[0m region                      = "us-east-1"
          [32m+[0m[0m tags_all                    = {
              [32m+[0m[0m AccessType  = "vpc-endpoint-only"
              [32m+[0m[0m Account     = "802860742843"
              [32m+[0m[0m Environment = "production"
              [32m+[0m[0m ManagedBy   = "terraform"
              [32m+[0m[0m Name        = "arj-test-4-poc-1-use1-prd"
              [32m+[0m[0m Owner       = "pra"
              [32m+[0m[0m Project     = "test-4-poc-1"
              [32m+[0m[0m Region      = "us-east-1"
              [32m+[0m[0m VPCAccess   = "true"
            }
        }
    }

```
