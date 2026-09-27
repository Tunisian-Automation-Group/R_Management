terraform {
  required_version = ">= 1.10"
  backend "s3" {
    # Created by infra/bootstrap. use_lockfile: S3-native state locking.
    bucket       = "cappy-terraform-state"
    key          = "prod/terraform.tfstate"
    region       = "eu-central-1"
    encrypt      = true
    use_lockfile = true
  }
  required_providers {
    aws     = { source = "hashicorp/aws", version = "~> 6.0" }
    random  = { source = "hashicorp/random", version = "~> 3.6" }
    http    = { source = "hashicorp/http", version = "~> 3.4" }
    archive = { source = "hashicorp/archive", version = "~> 2.4" }
  }
}

provider "aws" {
  region = var.region
  default_tags {
    tags = { app = "cappy", env = "prod", cell = var.cell, managed_by = "terraform" }
  }
}

# CloudFront certificates and WAF live in us-east-1.
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"
  default_tags {
    tags = { app = "cappy", env = "prod", managed_by = "terraform" }
  }
}

# The cell (ADR 0013) and its region: eu in eu-central-1 today; a second
# cell is another state (terraform init -backend-config=key=<cell>/prod/...),
# set by the deploy workflow from the environment's CELL and AWS_REGION (M-46).
variable "cell" {
  type    = string
  default = "eu"
}

variable "region" {
  type    = string
  default = "eu-central-1"
}

variable "image_tag" {
  type = string
}

variable "zone_id" {
  type = string
}

variable "alarm_email" {
  type = string
}

# Kill switches. Set by the GitHub environment variable SWITCHES (deploy.yml
# passes it as TF_VAR_switches), e.g. {"bookings":false,"payouts":true,"listings":true}
variable "switches" {
  type    = object({ bookings = bool, payouts = bool, listings = bool })
  default = { bookings = true, payouts = true, listings = true }
}

# The operator on fee invoices (§ 14 UStG). Set by the GitHub environment
# variable LEGAL (TF_VAR_legal):
# {"company":"…","address":"…","email":"…","vat_id":"…","tax_number":"","register":"…","directors":"…"}
variable "legal" {
  type = object({ company = string, address = string, email = string, vat_id = string, tax_number = string, register = optional(string, ""), directors = optional(string, "") })
}

# Feature flags (S-26). Set by the GitHub environment variable FEATURE_FLAGS
# (TF_VAR_feature_flags), e.g. newcheckout:25,chat:100
variable "feature_flags" {
  type    = string
  default = ""
}

# The store apps (TF_VAR_apps from the APPS variable), once they ship:
# {"apple_team_id":"…","android_sha256":"AB:CD:…","app_store_url":"…","play_store_url":"…"}
variable "apps" {
  type = object({
    apple_team_id  = optional(string, "")
    android_sha256 = optional(string, "")
    app_store_url  = optional(string, "")
    play_store_url = optional(string, "")
  })
  default = {}
}

# The pager's SNS HTTPS integration URL (TF_VAR_pager_endpoint from the
# PAGER_ENDPOINT secret). A prod plan fails without one unless allow_no_pager.
variable "pager_endpoint" {
  type      = string
  default   = ""
  sensitive = true
}

# Only on purpose (R2-23): lets a prod apply go ahead without a pager.
# TF_VAR_allow_no_pager from the environment variable ALLOW_NO_PAGER.
variable "allow_no_pager" {
  type    = bool
  default = false
}

module "platform" {
  source = "../../platform"
  # Real money moves through these accounts: threat protection (compromised
  # credentials, adaptive auth) is worth its per-user price in prod (P-8).
  cognito_threat_protection = true
  providers                 = { aws = aws, aws.us_east_1 = aws.us_east_1 }

  switches       = var.switches
  feature_flags  = var.feature_flags
  legal          = var.legal
  apps           = var.apps
  pager_endpoint = var.pager_endpoint
  allow_no_pager = var.allow_no_pager

  env          = "prod"
  cell         = var.cell
  region       = var.region
  image_tag    = var.image_tag
  zone_id      = var.zone_id
  alarm_email  = var.alarm_email
  domain       = "cappy.app"
  nat_gateways = 3
  db_min_acu   = 1
  db_max_acu   = 64
  db_instances = 2
  bot_control  = true
  # Launch traffic (INFRA §6): Aurora with a reader, 3 NATs, Cognito Plus,
  # Bot Control, the private CA. Raise with real numbers.
  monthly_budget_usd = 4000
}

output "platform" {
  value = module.platform
}
