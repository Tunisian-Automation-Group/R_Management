variable "env" {
  description = "staging or prod"
  type        = string
  validation {
    condition     = contains(["staging", "prod"], var.env)
    error_message = "env must be staging or prod"
  }
}

variable "region" {
  type    = string
  default = "eu-central-1"
}

# ADR 0013: a cell is a full copy of the stack for a group of markets
# (markets.json "cell"). Every name carries it, so two cells can share an
# account without their IAM roles, buckets or us-east-1 WAF colliding (M-46).
variable "cell" {
  type    = string
  default = "eu"
  validation {
    condition     = contains(["eu", "na"], var.cell)
    error_message = "cell must be eu or na (markets.json)"
  }
}

variable "domain" {
  description = "The public domain the app is served on, e.g. cappy.app or staging.cappy.app"
  type        = string
}

variable "zone_id" {
  description = "Route 53 hosted zone that holds var.domain"
  type        = string
}

variable "image_tag" {
  description = "The image tag every service runs; CD sets it to the commit sha"
  type        = string
}

variable "az_count" {
  type    = number
  default = 3
}

variable "nat_gateways" {
  description = "1 is cheaper (staging); one per AZ survives an AZ outage (prod)"
  type        = number
  default     = 1
}

variable "db_min_acu" {
  type    = number
  default = 0.5
}

variable "db_max_acu" {
  type    = number
  default = 16
}

variable "db_instances" {
  description = "Writer plus readers; 2+ is multi-AZ"
  type        = number
  default     = 2
}

variable "scale" {
  description = "Per-service task counts and sizes"
  type = map(object({
    cpu    = number
    memory = number
    min    = number
    max    = number
  }))
  default = {
    gateway       = { cpu = 512, memory = 1024, min = 2, max = 20 }
    catalog       = { cpu = 512, memory = 1024, min = 2, max = 20 }
    matching      = { cpu = 1024, memory = 2048, min = 2, max = 30 }
    booking       = { cpu = 512, memory = 1024, min = 2, max = 20 }
    payments      = { cpu = 256, memory = 512, min = 2, max = 10 }
    notifications = { cpu = 256, memory = 512, min = 1, max = 4 }
  }
}

variable "alarm_email" {
  description = "Where alarms go"
  type        = string
}

variable "waf_rate_limit" {
  description = "Requests per 5 minutes per IP before WAF blocks"
  type        = number
  default     = 2000
}

variable "switches" {
  description = "Kill switches (docs/runbook.md): turn one off and apply to pause it everywhere"
  type = object({
    bookings = bool
    payouts  = bool
    listings = bool
  })
  default = { bookings = true, payouts = true, listings = true }
}

variable "legal" {
  description = "The operator's identity for fee invoices (§ 14 UStG) and the Impressum, privacy policy and DSA contact point in the app: legal name, address (comma-separated lines), contact email, VAT ID and/or tax number, commercial register entry, managing directors (§ 35a GmbHG). Payments refuses to start without it; a release web build refuses to build without company, address and email."
  type        = object({ company = string, address = string, email = string, vat_id = string, tax_number = string, register = optional(string, ""), directors = optional(string, "") })
}

variable "apps" {
  description = "The store apps, for deep links and the update screen: Apple team id, the Android release signing SHA-256 (colon hex), the store URLs. Empty until the apps ship; a web-only launch leaves them empty and publishes no app-link files"
  type = object({
    apple_team_id  = optional(string, "")
    android_sha256 = optional(string, "")
    app_store_url  = optional(string, "")
    play_store_url = optional(string, "")
  })
  default = {}
}

variable "monthly_budget_usd" {
  description = "The environment's monthly AWS budget in USD: forecast above 80% and actual above 100% open a ticket (backup.tf, R2-4)"
  type        = number
  default     = 1000
}

variable "account_security" {
  description = "CloudTrail (multi-region, validated, object-locked), GuardDuty and Security Hub for this account (security.tf). Turn off only when the AWS organisation already runs them for every account"
  type        = bool
  default     = true
}

variable "allow_no_pager" {
  description = "Let prod apply without a pager (R2-23): only on purpose, e.g. a rehearsal before the on-call exists"
  type        = bool
  default     = false
}

variable "pager_endpoint" {
  description = "The pager's SNS HTTPS integration URL (PagerDuty, Opsgenie, or an Incident Manager response plan's endpoint): page-level alarms go there as well as to alarm_email. A prod plan fails without it unless allow_no_pager"
  type        = string
  default     = ""
  sensitive   = true
}

variable "feature_flags" {
  description = "Feature flags for the apps, \"name:percent,...\" (backend/libs/cappy_common/cappy_common/flags.py)"
  type        = string
  default     = ""
}

variable "bot_control" {
  description = "WAF Bot Control (common): about $10/month + $1 per million requests"
  type        = bool
  default     = false
}

variable "cognito_threat_protection" {
  description = "Cognito Plus tier with threat protection: about $0.02 per monthly active user. Off until account-takeover attempts show up"
  type        = bool
  default     = false
}

variable "push_app_arns" {
  description = "SNS platform application ARNs for push (APNs, FCM v1), created once by an operator with the store credentials"
  type        = object({ ios = string, android = string })
  default     = { ios = "", android = "" }
}
