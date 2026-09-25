output "url" {
  value = "https://${var.domain}"
}

output "cluster" {
  value = aws_ecs_cluster.main.name
}

output "services" {
  value = local.services
}

# What each service must be running after a deploy (the deploy checks it).
output "service_task_definitions" {
  value = { for k, v in aws_ecs_task_definition.service : k => v.arn }
}

output "migrate_task_definitions" {
  value = { for k, v in aws_ecs_task_definition.migrate : k => v.arn }
}

output "private_subnets" {
  value = aws_subnet.private[*].id
}

output "task_security_group" {
  value = aws_security_group.tasks.id
}

output "ecr" {
  value = { for k, v in aws_ecr_repository.service : k => v.repository_url }
}

output "web_bucket" {
  value = aws_s3_bucket.web.bucket
}

output "cloudfront_id" {
  value = aws_cloudfront_distribution.main.id
}

# What the web build needs (VITE_*); none of it is secret.
output "web_config" {
  value = {
    VITE_COGNITO_REGION    = var.region
    VITE_COGNITO_CLIENT_ID = aws_cognito_user_pool_client.web.id
  }
}
