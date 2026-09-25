# The part of the platform LocalStack can run for real: the event fabric.
# `make infra-local` applies it and proves an event reaches exactly the
# queues whose filters ask for it.

terraform {
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 6.0" }
  }
}

provider "aws" {
  region                      = "eu-central-1"
  access_key                  = "test"
  secret_key                  = "test"
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true
  endpoints {
    sns = "http://localhost:4566"
    sqs = "http://localhost:4566"
  }
}

module "messaging" {
  source = "../modules/messaging"
  name   = "cappy-tf"
  consumers = {
    catalog       = ["booking.rated", "payment.payouts_ready", "booking.renter_rated", "booking.owner_reliability", "moderation.person_flagged"]
    booking       = ["payment.authorised", "payment.failed", "listing.changed", "moderation.owner_suspended", "payment.identity_verified", "profile.deleted", "moderation.owner_reinstated"]
    payments      = ["booking.status_changed", "profile.deleted"]
    notifications = ["booking.status_changed", "payment.payout_sent", "profile.deleted", "booking.message", "moderation.report_received", "moderation.decision"]
  }
}

output "messaging" {
  value = module.messaging
}
