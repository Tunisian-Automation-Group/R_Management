# Backups nobody here can delete (R2-5). Aurora's own point-in-time restore
# (14 days in prod) lives and dies with the cluster; these recovery points
# live in a vault under Vault Lock in compliance mode, so no role in this
# account, the deploy role included, can shorten or delete them.
#
# ponytail: one vault in the cell's own region, which keeps EU data in the EU
# (ADR 0013). A copy in a second EU region or a separate backup account is
# the next step, when the owner has one (copy_action on the rule).

resource "aws_backup_vault" "main" {
  name = "${local.name}-vault"
}

resource "aws_backup_vault_lock_configuration" "main" {
  backup_vault_name  = aws_backup_vault.main.name
  min_retention_days = 35
  max_retention_days = 400
  # After these 3 days the lock can no longer be removed, by anyone.
  changeable_for_days = 3
}

resource "aws_backup_plan" "main" {
  name = "${local.name}-backups"

  rule {
    rule_name         = "daily"
    target_vault_name = aws_backup_vault.main.name
    schedule          = "cron(0 2 * * ? *)"
    lifecycle {
      delete_after = 35
    }
  }

  rule {
    rule_name         = "monthly"
    target_vault_name = aws_backup_vault.main.name
    schedule          = "cron(0 3 1 * ? *)"
    lifecycle {
      delete_after = var.env == "prod" ? 365 : 35
    }
  }
}

resource "aws_iam_role" "backup" {
  name = "${local.name}-backup"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "backup.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
}

resource "aws_iam_role_policy_attachment" "backup" {
  for_each = toset([
    "arn:aws:iam::aws:policy/service-role/AWSBackupServiceRolePolicyForBackup",
    "arn:aws:iam::aws:policy/service-role/AWSBackupServiceRolePolicyForRestores",
    "arn:aws:iam::aws:policy/AWSBackupServiceRolePolicyForS3Backup",
    "arn:aws:iam::aws:policy/AWSBackupServiceRolePolicyForS3Restore",
  ])
  role       = aws_iam_role.backup.name
  policy_arn = each.value
}

# The database and the photos (the media bucket is versioned, which S3 backup needs).
resource "aws_backup_selection" "main" {
  name         = "${local.name}-data"
  plan_id      = aws_backup_plan.main.id
  iam_role_arn = aws_iam_role.backup.arn
  resources    = [aws_rds_cluster.main.arn, aws_s3_bucket.media.arn]
}

# A failed backup job is a ticket; nobody learns of it otherwise.
resource "aws_cloudwatch_event_rule" "backup_failed" {
  name = "${local.name}-backup-failed"
  event_pattern = jsonencode({
    source        = ["aws.backup"]
    "detail-type" = ["Backup Job State Change"]
    detail        = { state = ["FAILED", "ABORTED", "EXPIRED"] }
  })
}

resource "aws_cloudwatch_event_target" "backup_failed" {
  rule = aws_cloudwatch_event_rule.backup_failed.name
  arn  = aws_sns_topic.tickets.arn
}

resource "aws_sns_topic_policy" "tickets_events" {
  arn = aws_sns_topic.tickets.arn
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "Alarms"
        Effect    = "Allow"
        Principal = { Service = "cloudwatch.amazonaws.com" }
        Action    = "sns:Publish"
        Resource  = aws_sns_topic.tickets.arn
        # Only this account's services may publish (R2-23).
        Condition = { StringEquals = { "aws:SourceAccount" = data.aws_caller_identity.me.account_id } }
      },
      {
        Sid       = "Events"
        Effect    = "Allow"
        Principal = { Service = ["events.amazonaws.com", "budgets.amazonaws.com", "costalerts.amazonaws.com"] }
        Action    = "sns:Publish"
        Resource  = aws_sns_topic.tickets.arn
        Condition = { StringEquals = { "aws:SourceAccount" = data.aws_caller_identity.me.account_id } }
      },
    ]
  })
}

# What the account spends (R2-4): a budget per environment, warned at 80% of
# the forecast and at 100% of the actual, and AWS's anomaly detection on
# every service. Both mail the tickets topic.
resource "aws_budgets_budget" "monthly" {
  name         = "${local.name}-monthly"
  budget_type  = "COST"
  limit_amount = tostring(var.monthly_budget_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  # The env tag (default_tags) must be activated as a cost allocation tag
  # once, in Billing (runbook step 1).
  cost_filter {
    name   = "TagKeyValue"
    values = [format("user:env$%s", var.env)]
  }

  notification {
    comparison_operator       = "GREATER_THAN"
    threshold                 = 80
    threshold_type            = "PERCENTAGE"
    notification_type         = "FORECASTED"
    subscriber_sns_topic_arns = [aws_sns_topic.tickets.arn]
  }

  notification {
    comparison_operator       = "GREATER_THAN"
    threshold                 = 100
    threshold_type            = "PERCENTAGE"
    notification_type         = "ACTUAL"
    subscriber_sns_topic_arns = [aws_sns_topic.tickets.arn]
  }
}

resource "aws_ce_anomaly_monitor" "services" {
  name              = "${local.name}-services"
  monitor_type      = "DIMENSIONAL"
  monitor_dimension = "SERVICE"
}

resource "aws_ce_anomaly_subscription" "services" {
  name             = "${local.name}-anomalies"
  frequency        = "IMMEDIATE"
  monitor_arn_list = [aws_ce_anomaly_monitor.services.arn]
  subscriber {
    type    = "SNS"
    address = aws_sns_topic.tickets.arn
  }
  threshold_expression {
    dimension {
      key           = "ANOMALY_TOTAL_IMPACT_ABSOLUTE"
      match_options = ["GREATER_THAN_OR_EQUAL"]
      values        = ["50"]
    }
  }
}
