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
    catalog       = ["booking.rated", "payment.payouts_ready", "booking.renter_rated", "booking.owner_reliability", "moderation.person_flagged", "payment.identity_verified", "staff.action"]
    booking       = ["payment.authorised", "payment.failed", "listing.changed", "moderation.owner_suspended", "payment.identity_verified", "profile.deleted", "person.signed_out", "moderation.owner_reinstated"]
    payments      = ["booking.status_changed", "profile.deleted", "person.signed_out"]
    notifications = ["booking.status_changed", "payment.payout_sent", "profile.deleted", "person.signed_out", "booking.message", "moderation.report_received", "moderation.decision", "listing.idle", "booking.dispute_offer", "booking.notice"]
  }
}

output "messaging" {
  value = module.messaging
}
