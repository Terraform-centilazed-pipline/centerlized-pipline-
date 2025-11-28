terraform {
  required_version = ">= 1.0.0"

  backend "s3" {
    bucket  = "terraform-elb-mdoule-poc"
    encrypt = true

    # The 'key' and 'region' must be provided via CLI, do not define them here.

    # New format for assuming a role (Terraform 1.11+)
    assume_role = {
      role_arn     = "arn:aws:iam::802860742843:role/TerraformExecutionRole"
      session_name = "terraform-s3-backend"
    }

    # Optional: if your role requires an external ID
    # external_id = "your-external-id"
  }
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.19"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.6"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}


locals {
  # Extract environment from tfvars filename (e.g., "prod" from "prod-s3-use1.tfvars")
  tfvars_files   = [for f in fileset(path.module, "**/**.tfvars") : f if length(regexall("(prod|staging|dev)-.*\\.tfvars$", f)) > 0]
  tfvars_file    = length(local.tfvars_files) > 0 ? basename(local.tfvars_files[0]) : ""
  target_account = length(regexall("^(prod|staging|dev)", local.tfvars_file)) > 0 ? regex("^(prod|staging|dev)", local.tfvars_file)[0] : ""
}

provider "aws" {
  region = var.aws_regions[var.s3_buckets[keys(var.s3_buckets)[0]].region_code].name

  # Assume role for cross-account access
  # Role ARN comes from tfvars (account_id extracted by controller)
  # Session name is unique per team/environment deployment
  assume_role {
    role_arn     = "arn:aws:iam::${var.accounts[var.s3_buckets[keys(var.s3_buckets)[0]].account_key].id}:role/${var.assume_role_name}"
    session_name = var.terraform_session_name  # Dynamic per deployment
  }

  # Default tags applied to all resources
  #default_tags {
  #  tags = var.common_tags
  #}
}