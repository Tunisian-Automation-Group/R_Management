# Account-level detection (P-14): who did what (CloudTrail), threats
# (GuardDuty), and posture against AWS's own baseline (Security Hub). Off with
# var.account_security when the organisation already runs these centrally for
# every account, which is where they belong once there is more than one.

locals {
  security = var.account_security ? 1 : 0
}

# The trail's bucket cannot lose what it holds: object lock in compliance
# mode keeps every log for a year, whoever asks (deploy role included), and
# log file validation proves nothing was altered.
resource "aws_s3_bucket" "trail" {
  count               = local.security
  bucket              = "${local.name}-trail-${data.aws_caller_identity.me.account_id}"
  object_lock_enabled = true
}

resource "aws_s3_bucket_object_lock_configuration" "trail" {
  count  = local.security
  bucket = aws_s3_bucket.trail[0].id
  rule {
    default_retention {
      mode = "COMPLIANCE"
      days = 365
    }
  }
}

resource "aws_s3_bucket_public_access_block" "trail" {
  count                   = local.security
  bucket                  = aws_s3_bucket.trail[0].id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_policy" "trail" {
  count  = local.security
  bucket = aws_s3_bucket.trail[0].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "TrailAcl"
        Effect    = "Allow"
        Principal = { Service = "cloudtrail.amazonaws.com" }
        Action    = "s3:GetBucketAcl"
        Resource  = aws_s3_bucket.trail[0].arn
      },
      {
        Sid       = "TrailWrite"
        Effect    = "Allow"
        Principal = { Service = "cloudtrail.amazonaws.com" }
        Action    = "s3:PutObject"
        Resource  = "${aws_s3_bucket.trail[0].arn}/AWSLogs/${data.aws_caller_identity.me.account_id}/*"
        Condition = { StringEquals = { "s3:x-amz-acl" = "bucket-owner-full-control" } }
      },
    ]
  })
}

# A copy in CloudWatch Logs, so root use and IAM changes can alarm.
resource "aws_cloudwatch_log_group" "trail" {
  count             = local.security
  name              = "/cappy/${local.name}/cloudtrail"
  retention_in_days = 90
}

resource "aws_iam_role" "trail_logs" {
  count = local.security
  name  = "${local.name}-trail-logs"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "cloudtrail.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
}

resource "aws_iam_role_policy" "trail_logs" {
  count = local.security
  role  = aws_iam_role.trail_logs[0].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
      Resource = "${aws_cloudwatch_log_group.trail[0].arn}:*"
    }]
  })
}

resource "aws_cloudtrail" "main" {
  count                         = local.security
  name                          = "${local.name}-trail"
  s3_bucket_name                = aws_s3_bucket.trail[0].id
  is_multi_region_trail         = true
  include_global_service_events = true
  enable_log_file_validation    = true
  cloud_watch_logs_group_arn    = "${aws_cloudwatch_log_group.trail[0].arn}:*"
  cloud_watch_logs_role_arn     = aws_iam_role.trail_logs[0].arn
  depends_on                    = [aws_s3_bucket_policy.trail]
}

resource "aws_guardduty_detector" "main" {
  count                        = local.security
  enable                       = true
  finding_publishing_frequency = "FIFTEEN_MINUTES"
}

resource "aws_securityhub_account" "main" {
  count = local.security
}

resource "aws_securityhub_standards_subscription" "foundational" {
  count         = local.security
  standards_arn = "arn:aws:securityhub:${var.region}::standards/aws-foundational-security-best-practices/v/1.0.0"
  depends_on    = [aws_securityhub_account.main]
}

# High and critical GuardDuty findings page (R2-6); the rest is Security
# Hub's to show.
resource "aws_cloudwatch_event_rule" "guardduty_high" {
  count = local.security
  name  = "${local.name}-guardduty-high"
  event_pattern = jsonencode({
    source        = ["aws.guardduty"]
    "detail-type" = ["GuardDuty Finding"]
    detail        = { severity = [{ numeric = [">=", 7] }] }
  })
}

resource "aws_cloudwatch_event_target" "guardduty_high" {
  count = local.security
  rule  = aws_cloudwatch_event_rule.guardduty_high[0].name
  arn   = aws_sns_topic.alarms.arn
}

resource "aws_sns_topic_policy" "alarms_events" {
  count = local.security
  arn   = aws_sns_topic.alarms.arn
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "Alarms"
        Effect    = "Allow"
        Principal = { Service = "cloudwatch.amazonaws.com" }
        Action    = "sns:Publish"
        Resource  = aws_sns_topic.alarms.arn
      },
      {
        Sid       = "GuardDuty"
        Effect    = "Allow"
        Principal = { Service = "events.amazonaws.com" }
        Action    = "sns:Publish"
        Resource  = aws_sns_topic.alarms.arn
      },
    ]
  })
}

# CIS 3.x style alarms on the trail: the root user doing anything, and anyone
# changing IAM policies. Either should be a surprise.
locals {
  trail_alarms = var.account_security ? {
    root-used   = "{ $.userIdentity.type = \"Root\" && $.userIdentity.invokedBy NOT EXISTS && $.eventType != \"AwsServiceEvent\" }"
    iam-changed = "{ ($.eventSource = \"iam.amazonaws.com\") && (($.eventName = \"PutRolePolicy\") || ($.eventName = \"AttachRolePolicy\") || ($.eventName = \"CreatePolicyVersion\") || ($.eventName = \"PutUserPolicy\") || ($.eventName = \"AttachUserPolicy\") || ($.eventName = \"CreateAccessKey\") || ($.eventName = \"DeleteRolePolicy\") || ($.eventName = \"DetachRolePolicy\")) }"
  } : {}
}

resource "aws_cloudwatch_log_metric_filter" "trail" {
  for_each       = local.trail_alarms
  name           = "${local.name}-${each.key}"
  log_group_name = aws_cloudwatch_log_group.trail[0].name
  pattern        = each.value
  metric_transformation {
    name      = each.key
    namespace = "Cappy/Security"
    value     = "1"
  }
}

resource "aws_cloudwatch_metric_alarm" "trail" {
  for_each            = local.trail_alarms
  alarm_name          = "${local.name}-${each.key}"
  alarm_description   = "CloudTrail: ${each.key} (runbook: Security incident)"
  namespace           = "Cappy/Security"
  metric_name         = each.key
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  # Root use pages; an IAM change is a ticket (deploys change IAM on purpose).
  alarm_actions = each.key == "root-used" ? local.alarm_actions : local.ticket_actions
  depends_on    = [aws_cloudwatch_log_metric_filter.trail]
}
