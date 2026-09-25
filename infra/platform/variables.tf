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
