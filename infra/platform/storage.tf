# Two private buckets: the built web app and listing photos. Only CloudFront
# reads them (origin access control); only the catalog writes photos.

data "aws_caller_identity" "me" {}

resource "aws_s3_bucket" "web" {
  bucket = "${local.name}-web-${data.aws_caller_identity.me.account_id}"
}

resource "aws_s3_bucket" "media" {
  bucket = "${local.name}-media-${data.aws_caller_identity.me.account_id}"
}

resource "aws_s3_bucket_public_access_block" "all" {
  for_each                = { web = aws_s3_bucket.web.id, media = aws_s3_bucket.media.id }
  bucket                  = each.value
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "all" {
  for_each = { web = aws_s3_bucket.web.id, media = aws_s3_bucket.media.id }
  bucket   = each.value
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_versioning" "media" {
  bucket = aws_s3_bucket.media.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "media" {
  bucket = aws_s3_bucket.media.id
  rule {
    id     = "expire-old-versions"
    status = "Enabled"
    filter {}
    noncurrent_version_expiration {
      noncurrent_days = 30
    }
    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }
}

resource "aws_s3_bucket_policy" "cloudfront_reads" {
  for_each = { web = aws_s3_bucket.web, media = aws_s3_bucket.media }
  bucket   = each.value.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "cloudfront.amazonaws.com" }
      Action    = "s3:GetObject"
      # Photos: only the public prefix. Hand-over evidence (private/) is never
      # readable through the CDN, only through booking's signed links (P-27).
      Resource  = each.key == "media" ? "${each.value.arn}/media/*" : "${each.value.arn}/*"
      Condition = { StringEquals = { "AWS:SourceArn" = aws_cloudfront_distribution.main.arn } }
    }]
  })
}
