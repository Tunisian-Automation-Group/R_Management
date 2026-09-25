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
