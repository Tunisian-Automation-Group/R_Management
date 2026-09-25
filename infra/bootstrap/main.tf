# Run once per AWS account, by a person, with local state:
#   terraform init && terraform apply -var github_repo=Tunisian-Automation-Group/R_Management
# Creates what everything else stands on: the state bucket and the roles
# GitHub Actions assumes through OIDC (no long-lived AWS keys anywhere).

terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 6.0" }
  }
}

provider "aws" {
  region = "eu-central-1"
}

variable "github_repo" {
  description = "owner/name"
  type        = string
}

resource "aws_s3_bucket" "state" {
  bucket = "cappy-terraform-state"
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "state" {
  bucket = aws_s3_bucket.state.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "aws:kms"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "state" {
  bucket                  = aws_s3_bucket.state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
}

locals {
  # Only deploy jobs, in a protected GitHub environment and running the
  # workflow from main, may assume a role. Pull requests get no AWS access at
  # all: CI needs none, and state holds secrets.
  roles = {
    deploy-staging = {
      subjects = ["repo:${var.github_repo}:environment:staging"]
      policy   = "arn:aws:iam::aws:policy/AdministratorAccess"
    }
    deploy-prod = {
      subjects = ["repo:${var.github_repo}:environment:prod"]
      policy   = "arn:aws:iam::aws:policy/AdministratorAccess"
    }
  }
}

resource "aws_iam_role" "github" {
  for_each = local.roles
  name     = "cappy-github-${each.key}"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = aws_iam_openid_connect_provider.github.arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud"              = "sts.amazonaws.com"
          "token.actions.githubusercontent.com:ref"              = "refs/heads/main"
          "token.actions.githubusercontent.com:job_workflow_ref" = "${var.github_repo}/.github/workflows/deploy.yml@refs/heads/main"
        }
        StringLike = { "token.actions.githubusercontent.com:sub" = each.value.subjects }
      }
    }]
  })
  max_session_duration = 3600
}

resource "aws_iam_role_policy_attachment" "github" {
  for_each   = local.roles
  role       = aws_iam_role.github[each.key].name
  policy_arn = each.value.policy
}

output "role_arns" {
  value = { for k, r in aws_iam_role.github : k => r.arn }
}
