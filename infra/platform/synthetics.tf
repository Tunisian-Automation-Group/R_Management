# Outside-in checks of the public site every 5 minutes (resilience F34).

data "archive_file" "canary" {
  type        = "zip"
  source_dir  = "${path.module}/canary"
  output_path = "${path.module}/.build/canary.zip"
}

resource "aws_s3_bucket" "canary" {
  bucket        = "${local.name}-canary-${data.aws_caller_identity.me.account_id}"
  force_destroy = true
}

resource "aws_s3_bucket_lifecycle_configuration" "canary" {
  bucket = aws_s3_bucket.canary.id
  rule {
    id     = "expire-artifacts"
    status = "Enabled"
    filter {}
    expiration {
      days = 14
    }
  }
}

resource "aws_iam_role" "canary" {
  name = "${local.name}-canary"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "lambda.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
}

resource "aws_iam_role_policy" "canary" {
  role = aws_iam_role.canary.name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["s3:PutObject", "s3:GetBucketLocation"], Resource = [aws_s3_bucket.canary.arn, "${aws_s3_bucket.canary.arn}/*"] },
      { Effect = "Allow", Action = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"], Resource = "*" },
      { Effect = "Allow", Action = "cloudwatch:PutMetricData", Resource = "*", Condition = { StringEquals = { "cloudwatch:namespace" = "CloudWatchSynthetics" } } },
      { Effect = "Allow", Action = ["s3:ListAllMyBuckets", "xray:PutTraceSegments"], Resource = "*" },
    ]
  })
}

resource "aws_synthetics_canary" "journeys" {
  name                 = substr(replace("${local.name}-journeys", "_", "-"), 0, 21)
  artifact_s3_location = "s3://${aws_s3_bucket.canary.bucket}/"
  execution_role_arn   = aws_iam_role.canary.arn
  handler              = "journeys.handler"
  zip_file             = data.archive_file.canary.output_path
  runtime_version      = "syn-nodejs-puppeteer-9.1"
  start_canary         = true
  schedule {
    expression = "rate(5 minutes)"
  }
  run_config {
    timeout_in_seconds = 60
    environment_variables = {
      CAPPY_HOST = var.domain
    }
  }
}

resource "aws_cloudwatch_metric_alarm" "canary" {
  alarm_name          = "${local.name}-canary-failing"
  alarm_description   = "The public site fails an outside-in check (web, categories, search, privacy of internal routes)"
  namespace           = "CloudWatchSynthetics"
  metric_name         = "SuccessPercent"
  dimensions          = { CanaryName = aws_synthetics_canary.journeys.name }
  statistic           = "Average"
  period              = 300
  evaluation_periods  = 2
  threshold           = 100
  comparison_operator = "LessThanThreshold"
  treat_missing_data  = "breaching"
  alarm_actions       = local.alarm_actions
  ok_actions          = local.alarm_actions
}
