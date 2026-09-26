# Alarms on what a person would be paged for: users seeing errors or slowness,
# events stuck in a dead-letter queue, and the database running hot.

resource "aws_sns_topic" "alarms" {
  name = "${local.name}-alarms"
}

resource "aws_sns_topic_subscription" "alarms_email" {
  topic_arn = aws_sns_topic.alarms.arn
  protocol  = "email"
  endpoint  = var.alarm_email
}

locals {
  alarm_actions = [aws_sns_topic.alarms.arn]
}

resource "aws_cloudwatch_metric_alarm" "api_5xx_rate" {
  alarm_name          = "${local.name}-api-5xx-rate"
  alarm_description   = "More than 2% of API requests fail with 5xx"
  comparison_operator = "GreaterThanThreshold"
  threshold           = 2
  evaluation_periods  = 3
  datapoints_to_alarm = 2
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions
  ok_actions          = local.alarm_actions

  metric_query {
    id          = "rate"
    expression  = "100 * errors / MAX([errors, requests])"
    label       = "5xx %"
    return_data = true
  }
  metric_query {
    id = "errors"
    metric {
      namespace   = "AWS/ApplicationELB"
      metric_name = "HTTPCode_Target_5XX_Count"
      dimensions  = { LoadBalancer = aws_lb.main.arn_suffix }
      period      = 60
      stat        = "Sum"
    }
  }
  metric_query {
    id = "requests"
    metric {
      namespace   = "AWS/ApplicationELB"
      metric_name = "RequestCount"
      dimensions  = { LoadBalancer = aws_lb.main.arn_suffix }
      period      = 60
      stat        = "Sum"
    }
  }
}

resource "aws_cloudwatch_metric_alarm" "api_latency" {
  alarm_name          = "${local.name}-api-p99-latency"
  alarm_description   = "p99 API latency above 1.5 s"
  namespace           = "AWS/ApplicationELB"
  metric_name         = "TargetResponseTime"
  dimensions          = { LoadBalancer = aws_lb.main.arn_suffix }
  extended_statistic  = "p99"
  period              = 60
  evaluation_periods  = 5
  datapoints_to_alarm = 3
  threshold           = 1.5
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions
  ok_actions          = local.alarm_actions
}

resource "aws_cloudwatch_metric_alarm" "dlq" {
  for_each            = module.messaging.dlq_names
  alarm_name          = "${local.name}-${each.key}-dead-letters"
  alarm_description   = "Events ${each.key} could not handle; see docs/runbook.md"
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = each.value }
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions
}

resource "aws_cloudwatch_metric_alarm" "queue_age" {
  for_each            = module.messaging.queue_names
  alarm_name          = "${local.name}-${each.key}-queue-age"
  alarm_description   = "${each.key} is falling behind on events"
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateAgeOfOldestMessage"
  dimensions          = { QueueName = each.value }
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 5
  threshold           = 300
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions
}

resource "aws_cloudwatch_metric_alarm" "db_cpu" {
  alarm_name          = "${local.name}-db-cpu"
  namespace           = "AWS/RDS"
  metric_name         = "CPUUtilization"
  dimensions          = { DBClusterIdentifier = aws_rds_cluster.main.cluster_identifier }
  statistic           = "Average"
  period              = 60
  evaluation_periods  = 10
  threshold           = 80
  comparison_operator = "GreaterThanThreshold"
  alarm_actions       = local.alarm_actions
}

resource "aws_cloudwatch_metric_alarm" "db_capacity" {
  alarm_name          = "${local.name}-db-at-max-capacity"
  alarm_description   = "Aurora is near its ACU ceiling; raise db_max_acu"
  namespace           = "AWS/RDS"
  metric_name         = "ServerlessDatabaseCapacity"
  dimensions          = { DBClusterIdentifier = aws_rds_cluster.main.cluster_identifier }
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 3
  threshold           = var.db_max_acu * 0.9
  comparison_operator = "GreaterThanOrEqualToThreshold"
  alarm_actions       = local.alarm_actions
}

# A chargeback holds a payout and needs a person (docs/runbook.md).
resource "aws_cloudwatch_log_metric_filter" "chargebacks" {
  name           = "${local.name}-chargebacks"
  log_group_name = aws_cloudwatch_log_group.service["payments"].name
  pattern        = "\"CHARGEBACK\""
  metric_transformation {
    name      = "Chargebacks"
    namespace = "Cappy/${var.env}"
    value     = "1"
  }
}

resource "aws_cloudwatch_metric_alarm" "chargebacks" {
  alarm_name          = "${local.name}-chargeback"
  alarm_description   = "A card holder disputed a charge; the payout is held. See docs/runbook.md"
  namespace           = "Cappy/${var.env}"
  metric_name         = "Chargebacks"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions
}

# An outbox row that failed 20 times is set aside: its change committed, its
# event will not go out on its own (D-14). Republish after fixing the cause:
# docs/runbook.md "An event was set aside".
resource "aws_cloudwatch_log_metric_filter" "outbox_set_aside" {
  for_each       = toset(local.db_services)
  name           = "${local.name}-${each.key}-outbox-set-aside"
  log_group_name = aws_cloudwatch_log_group.service[each.key].name
  pattern        = "\"OUTBOX_SET_ASIDE\""
  metric_transformation {
    name      = "OutboxSetAside"
    namespace = "Cappy/${var.env}"
    value     = "1"
  }
}

resource "aws_cloudwatch_metric_alarm" "outbox_set_aside" {
  alarm_name          = "${local.name}-outbox-set-aside"
  alarm_description   = "An event was set aside after 20 failed publishes. See docs/runbook.md"
  namespace           = "Cappy/${var.env}"
  metric_name         = "OutboxSetAside"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions
}

# --- error-budget burn (docs/slo.md) --------------------------------------------------
# Availability SLO 99.5% on the API: the budget is 0.5% errors. Page when it
# burns 14.4x too fast over both 1 h and 5 min (2% of the month's budget in an
# hour); open a ticket at 6x over both 6 h and 30 min (Google SRE workbook).

locals {
  slo_budget = 0.005
  burn_windows = {
    page_long    = { seconds = 3600, factor = 14.4 }
    page_short   = { seconds = 300, factor = 14.4 }
    ticket_long  = { seconds = 21600, factor = 6 }
    ticket_short = { seconds = 1800, factor = 6 }
  }
}

resource "aws_cloudwatch_metric_alarm" "burn" {
  for_each            = local.burn_windows
  alarm_name          = "${local.name}-slo-burn-${each.key}"
  comparison_operator = "GreaterThanThreshold"
  threshold           = 100 * local.slo_budget * each.value.factor
  evaluation_periods  = 1
  treat_missing_data  = "notBreaching"

  metric_query {
    id          = "rate"
    expression  = "100 * errors / MAX([errors, requests])"
    return_data = true
  }
  metric_query {
    id = "errors"
    metric {
      namespace   = "AWS/ApplicationELB"
      metric_name = "HTTPCode_Target_5XX_Count"
      dimensions  = { LoadBalancer = aws_lb.main.arn_suffix }
      period      = each.value.seconds
      stat        = "Sum"
    }
  }
  metric_query {
    id = "requests"
    metric {
      namespace   = "AWS/ApplicationELB"
      metric_name = "RequestCount"
      dimensions  = { LoadBalancer = aws_lb.main.arn_suffix }
      period      = each.value.seconds
      stat        = "Sum"
    }
  }
}

resource "aws_cloudwatch_composite_alarm" "burn_page" {
  alarm_name        = "${local.name}-slo-burning-fast"
  alarm_description = "The API is spending its monthly error budget 14x too fast. Page."
  alarm_rule        = "ALARM(${aws_cloudwatch_metric_alarm.burn["page_long"].alarm_name}) AND ALARM(${aws_cloudwatch_metric_alarm.burn["page_short"].alarm_name})"
  alarm_actions     = local.alarm_actions
  ok_actions        = local.alarm_actions
}

resource "aws_cloudwatch_composite_alarm" "burn_ticket" {
  alarm_name        = "${local.name}-slo-burning"
  alarm_description = "The API is spending its monthly error budget 6x too fast. Look today."
  alarm_rule        = "ALARM(${aws_cloudwatch_metric_alarm.burn["ticket_long"].alarm_name}) AND ALARM(${aws_cloudwatch_metric_alarm.burn["ticket_short"].alarm_name})"
  alarm_actions     = local.alarm_actions
}
