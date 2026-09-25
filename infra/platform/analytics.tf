# Product analytics from the events the services already publish (research:
# server-side events need no cookie consent). SNS -> Firehose -> S3 (Parquet-
# friendly JSON, partitioned by day) -> Athena for the funnel and marketplace
# health: searches become requests, requests acceptances, completions reviews.

resource "aws_s3_bucket" "analytics" {
  bucket = "${local.name}-analytics-${data.aws_caller_identity.me.account_id}"
}

resource "aws_s3_bucket_public_access_block" "analytics" {
  bucket                  = aws_s3_bucket.analytics.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "analytics" {
  bucket = aws_s3_bucket.analytics.id
  rule {
    id     = "cold-after-90-days"
    status = "Enabled"
    filter {}
    transition {
      days          = 90
      storage_class = "GLACIER_IR"
    }
    # Only ids and non-identifying fields arrive (analytics/scrub.py, P-6);
    # kept two years for trends. Deleting an account needs nothing here: the
    # lake holds its pseudonymous id and nothing to tie it to a person.
    expiration {
      days = 730
    }
  }
}

resource "aws_iam_role" "firehose" {
  name = "${local.name}-analytics-firehose"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "firehose.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
}

resource "aws_iam_role_policy" "firehose" {
  role = aws_iam_role.firehose.name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["s3:AbortMultipartUpload", "s3:GetBucketLocation", "s3:ListBucket", "s3:PutObject"]
      Resource = [aws_s3_bucket.analytics.arn, "${aws_s3_bucket.analytics.arn}/*"]
      }, {
      Effect   = "Allow"
      Action   = ["lambda:InvokeFunction", "lambda:GetFunctionConfiguration"]
      Resource = ["${aws_lambda_function.analytics_scrub.arn}", "${aws_lambda_function.analytics_scrub.arn}:*"]
    }]
  })
}

resource "aws_kinesis_firehose_delivery_stream" "events" {
  name        = "${local.name}-events"
  destination = "extended_s3"
  extended_s3_configuration {
    role_arn            = aws_iam_role.firehose.arn
    bucket_arn          = aws_s3_bucket.analytics.arn
    prefix              = "events/dt=!{timestamp:yyyy-MM-dd}/"
    error_output_prefix = "errors/!{firehose:error-output-type}/dt=!{timestamp:yyyy-MM-dd}/"
    buffering_interval  = 300
    buffering_size      = 64
    compression_format  = "GZIP"

    # Only allowlisted, non-identifying fields reach the lake (P-6).
    processing_configuration {
      enabled = true
      processors {
        type = "Lambda"
        parameters {
          parameter_name  = "LambdaArn"
          parameter_value = "${aws_lambda_function.analytics_scrub.arn}:$LATEST"
        }
      }
    }
  }
}

data "archive_file" "analytics_scrub" {
  type        = "zip"
  source_file = "${path.module}/analytics/scrub.py"
  output_path = "${path.module}/.build/analytics-scrub.zip"
}

resource "aws_iam_role" "analytics_scrub" {
  name = "${local.name}-analytics-scrub"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "lambda.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
}

resource "aws_iam_role_policy_attachment" "analytics_scrub_logs" {
  role       = aws_iam_role.analytics_scrub.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_lambda_function" "analytics_scrub" {
  function_name    = "${local.name}-analytics-scrub"
  role             = aws_iam_role.analytics_scrub.arn
  runtime          = "python3.12"
  handler          = "scrub.handler"
  filename         = data.archive_file.analytics_scrub.output_path
  source_code_hash = data.archive_file.analytics_scrub.output_base64sha256
  timeout          = 60
  memory_size      = 256
}

resource "aws_iam_role" "sns_to_firehose" {
  name = "${local.name}-sns-to-firehose"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "sns.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
}

resource "aws_iam_role_policy" "sns_to_firehose" {
  role = aws_iam_role.sns_to_firehose.name
  policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Action = ["firehose:PutRecord", "firehose:PutRecordBatch"], Resource = aws_kinesis_firehose_delivery_stream.events.arn }]
  })
}

resource "aws_sns_topic_subscription" "analytics" {
  topic_arn             = module.messaging.topic_arn
  protocol              = "firehose"
  endpoint              = aws_kinesis_firehose_delivery_stream.events.arn
  subscription_role_arn = aws_iam_role.sns_to_firehose.arn
  raw_message_delivery  = true
}

# Athena: `SELECT type, count(*) FROM cappy_events WHERE dt >= '…' GROUP BY 1`.
resource "aws_glue_catalog_database" "analytics" {
  name = replace("${local.name}_analytics", "-", "_")
}

resource "aws_glue_catalog_table" "events" {
  name          = "cappy_events"
  database_name = aws_glue_catalog_database.analytics.name
  table_type    = "EXTERNAL_TABLE"
  parameters = {
    "projection.enabled"        = "true"
    "projection.dt.type"        = "date"
    "projection.dt.format"      = "yyyy-MM-dd"
    "projection.dt.range"       = "2026-01-01,NOW"
    "storage.location.template" = "s3://${aws_s3_bucket.analytics.bucket}/events/dt=$${dt}/"
  }
  partition_keys {
    name = "dt"
    type = "string"
  }
  storage_descriptor {
    location      = "s3://${aws_s3_bucket.analytics.bucket}/events/"
    input_format  = "org.apache.hadoop.mapred.TextInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat"
    ser_de_info {
      serialization_library = "org.openx.data.jsonserde.JsonSerDe"
    }
    columns {
      name = "id"
      type = "string"
    }
    columns {
      name = "type"
      type = "string"
    }
    columns {
      name = "source"
      type = "string"
    }
    columns {
      name = "occurredat"
      type = "string"
    }
    columns {
      name = "data"
      type = "string"
    }
  }
}
