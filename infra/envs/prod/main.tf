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
  region = "eu-central-1"
  default_tags {
    tags = { app = "cappy", env = "prod", managed_by = "terraform" }
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

variable "image_tag" {
  type = string
}

variable "zone_id" {
  type = string
}

variable "alarm_email" {
  type = string
}

# Kill switches: terraform apply -var 'switches={bookings=false,payouts=true,listings=true}'
variable "switches" {
  type    = object({ bookings = bool, payouts = bool, listings = bool })
  default = { bookings = true, payouts = true, listings = true }
}

module "platform" {
  source    = "../../platform"
  providers = { aws = aws, aws.us_east_1 = aws.us_east_1 }

  env          = "prod"
  image_tag    = var.image_tag
  zone_id      = var.zone_id
  alarm_email  = var.alarm_email
  domain       = "cappy.app"
  nat_gateways = 3
  db_min_acu   = 1
  db_max_acu   = 64
  db_instances = 2
  bot_control  = true
}

output "platform" {
  value = module.platform
}
