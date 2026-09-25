# ADR 0002: Cognito holds identities, passwords and email verification.
# Services verify its access tokens; nothing else is trusted to say who you are.

resource "aws_cognito_user_pool" "main" {
  name                     = local.name
  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]
  deletion_protection      = var.env == "prod" ? "ACTIVE" : "INACTIVE"
  mfa_configuration        = "OPTIONAL"
  user_pool_tier           = var.cognito_threat_protection ? "PLUS" : "ESSENTIALS"

  dynamic "user_pool_add_ons" {
    for_each = var.cognito_threat_protection ? [1] : []
    content {
      advanced_security_mode = "ENFORCED"
    }
  }

  software_token_mfa_configuration {
    enabled = true
  }

  # NIST SP 800-63B-4: length, not composition rules (they make passwords
  # more predictable, not stronger). Breached passwords: Cognito threat
  # protection's compromised-credentials check (T-06).
  password_policy {
    minimum_length                   = 12
    require_lowercase                = false
    require_uppercase                = false
    require_numbers                  = false
    require_symbols                  = false
    temporary_password_validity_days = 3
  }

  # A changed email only takes effect once the new address is verified (P-25).
  user_attribute_update_settings {
    attributes_require_verification_before_update = ["email"]
  }

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  email_configuration {
    email_sending_account = "DEVELOPER"
    source_arn            = aws_sesv2_email_identity.domain.arn
    from_email_address    = "Cappy <no-reply@${var.domain}>"
  }

  verification_message_template {
    default_email_option = "CONFIRM_WITH_CODE"
    email_subject        = "Your Cappy code"
    email_message        = "Your Cappy verification code is {####}"
  }

  schema {
    name                = "email"
    attribute_data_type = "String"
    required            = true
    mutable             = true
    string_attribute_constraints {
      min_length = 3
      max_length = 254
    }
  }
}

resource "aws_cognito_user_pool_client" "web" {
  name         = "web"
  user_pool_id = aws_cognito_user_pool.main.id
  # A browser cannot keep a secret.
  generate_secret = false
  explicit_auth_flows = [
    "ALLOW_USER_SRP_AUTH",
    "ALLOW_USER_PASSWORD_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
  ]
  # The app writes only the email (at sign-up) and the language; nothing a
  # user sets on themselves may look like something we vouch for (P-25).
  read_attributes               = ["email", "email_verified", "locale"]
  write_attributes              = ["email", "locale"]
  prevent_user_existence_errors = "ENABLED"
  enable_token_revocation       = true
  # Short-lived: an access token outlives a sign-out-everywhere or a deleted
  # account by at most this long where the services' not-before check cannot
  # see it (P-24). The app refreshes silently.
  access_token_validity  = 15
  id_token_validity      = 15
  refresh_token_validity = 30
  token_validity_units {
    access_token  = "minutes"
    id_token      = "minutes"
    refresh_token = "days"
  }
}

locals {
  auth_issuer = "https://cognito-idp.${var.region}.amazonaws.com/${aws_cognito_user_pool.main.id}"
}

# The pool's signing keys at deploy time. Services start with them, so a task
# launched while Cognito is unreachable still verifies tokens (resilience F5).
# Cognito does not rotate these keys by itself; the next deploy refreshes them.
data "http" "jwks" {
  url = "${local.auth_issuer}/.well-known/jwks.json"
  request_headers = {
    Accept = "application/json"
  }
}

# Staff: moderators and support. Membership is granted by hand
# (aws cognito-idp admin-add-user-to-group), never by the app.
resource "aws_cognito_user_group" "admin" {
  name         = "admin"
  user_pool_id = aws_cognito_user_pool.main.id
  description  = "Cappy staff: moderation, support, dispute resolution"
}

# Sign-in and sign-up go straight to Cognito, past CloudFront's WAF: a
# regional web ACL of their own against credential stuffing (P-8).
resource "aws_wafv2_web_acl" "cognito" {
  name  = "${local.name}-cognito"
  scope = "REGIONAL"

  default_action {
    allow {}
  }

  rule {
    name     = "auth-per-ip"
    priority = 1
    action {
      block {}
    }
    statement {
      rate_based_statement {
        limit              = 100
        aggregate_key_type = "IP"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "cognito-auth-per-ip"
      sampled_requests_enabled   = false
    }
  }

  rule {
    name     = "ip-reputation"
    priority = 2
    override_action {
      none {}
    }
    statement {
      managed_rule_group_statement {
        vendor_name = "AWS"
        name        = "AWSManagedRulesAmazonIpReputationList"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "cognito-ip-reputation"
      sampled_requests_enabled   = false
    }
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "${local.name}-cognito"
    sampled_requests_enabled   = false
  }
}

resource "aws_wafv2_web_acl_association" "cognito" {
  resource_arn = aws_cognito_user_pool.main.arn
  web_acl_arn  = aws_wafv2_web_acl.cognito.arn
}
