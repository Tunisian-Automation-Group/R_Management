# ADR 0003: one topic; one queue (and dead-letter queue) per consuming
# service, subscribed with a filter on the event type. Keep in step with
# local/bootstrap.py.

terraform {
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 6.0" }
  }
}

variable "name" {
  type = string
}

variable "consumers" {
  description = "service => event types its queue receives"
  type        = map(list(string))
}

locals {
  consumers = var.consumers
}

resource "aws_sns_topic" "events" {
  name              = "${var.name}-events"
  kms_master_key_id = "alias/aws/sns"
}

resource "aws_sqs_queue" "dlq" {
  for_each                  = local.consumers
  name                      = "${var.name}-${each.key}-dlq"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true
}

resource "aws_sqs_queue" "events" {
  for_each                   = local.consumers
  name                       = "${var.name}-${each.key}"
  visibility_timeout_seconds = 60
  receive_wait_time_seconds  = 20
  sqs_managed_sse_enabled    = true
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq[each.key].arn
    maxReceiveCount     = 5
  })
}

resource "aws_sqs_queue_policy" "events" {
  for_each  = local.consumers
  queue_url = aws_sqs_queue.events[each.key].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "sns.amazonaws.com" }
      Action    = "sqs:SendMessage"
      Resource  = aws_sqs_queue.events[each.key].arn
      Condition = { ArnEquals = { "aws:SourceArn" = aws_sns_topic.events.arn } }
    }]
  })
}

resource "aws_sns_topic_subscription" "events" {
  for_each             = local.consumers
  topic_arn            = aws_sns_topic.events.arn
  protocol             = "sqs"
  endpoint             = aws_sqs_queue.events[each.key].arn
  raw_message_delivery = true
  filter_policy        = jsonencode({ type = each.value })
}

output "topic_arn" {
  value = aws_sns_topic.events.arn
}

output "queue_urls" {
  value = { for k, q in aws_sqs_queue.events : k => q.url }
}

output "queue_arns" {
  value = { for k, q in aws_sqs_queue.events : k => q.arn }
}

output "queue_names" {
  value = { for k, q in aws_sqs_queue.events : k => q.name }
}

output "dlq_names" {
  value = { for k, q in aws_sqs_queue.dlq : k => q.name }
}
