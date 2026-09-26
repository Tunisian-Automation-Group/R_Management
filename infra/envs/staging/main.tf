terraform {
  required_version = ">= 1.10"
  backend "s3" {
    # Created by infra/bootstrap. use_lockfile: S3-native state locking.
    bucket       = "cappy-terraform-state"
    key          = "staging/terraform.tfstate"
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
  region = "eu-central-1"
  default_tags {
    tags = { app = "cappy", env = "staging", managed_by = "terraform" }
  }
}

# CloudFront certificates and WAF live in us-east-1.
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"
  default_tags {
    tags = { app = "cappy", env = "staging", managed_by = "terraform" }
  }
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
# variable LEGAL (TF_VAR_legal): {"company":"…","address":"…","vat_id":"…","tax_number":""}
variable "legal" {
  type = object({ company = string, address = string, vat_id = string, tax_number = string })
}

# Feature flags (S-26). Set by the GitHub environment variable FEATURE_FLAGS
# (TF_VAR_feature_flags), e.g. newcheckout:25,chat:100
variable "feature_flags" {
  type    = string
  default = ""
}

module "platform" {
  source    = "../../platform"
  providers = { aws = aws, aws.us_east_1 = aws.us_east_1 }

  switches      = var.switches
  feature_flags = var.feature_flags
  legal         = var.legal

  env          = "staging"
  image_tag    = var.image_tag
  zone_id      = var.zone_id
  alarm_email  = var.alarm_email
  domain       = "staging.cappy.app"
  nat_gateways = 1
  db_min_acu   = 0.5
  db_max_acu   = 4
  db_instances = 1
  scale = {
    gateway       = { cpu = 256, memory = 512, min = 1, max = 4 }
    catalog       = { cpu = 256, memory = 512, min = 1, max = 4 }
    matching      = { cpu = 512, memory = 1024, min = 1, max = 4 }
    booking       = { cpu = 256, memory = 512, min = 1, max = 4 }
    payments      = { cpu = 256, memory = 512, min = 1, max = 2 }
    notifications = { cpu = 256, memory = 512, min = 1, max = 2 }
  }
}

output "platform" {
  value = module.platform
}
