# ECS on Fargate, one service per deployable, all from the one image recipe
# (backend/Dockerfile). Services find each other through Service Connect as
# http://<name>:8000; only the gateway is behind the load balancer.

locals {
  services = keys(var.scale)
  # Called by other services, so they get a Service Connect name.
  servers = ["catalog", "matching", "booking", "payments"]

  common_env = {
    APP_ENV            = var.env
    LOG_JSON           = "true"
    AWS_REGION         = var.region
    EVENT_BUS_URL      = "sns://${module.messaging.topic_arn}"
    AUTH_ISSUER        = local.auth_issuer
    AUTH_CLIENT_IDS    = aws_cognito_user_pool_client.web.id
    AUTH_JWKS_FALLBACK = data.http.jwks.response_body
    CATALOG_URL        = "http://catalog:8000"
    MATCHING_URL       = "http://matching:8000"
    BOOKING_URL        = "http://booking:8000"
    PAYMENTS_URL       = "http://payments:8000"
  }
  service_env = {
    # The App Store and Google Play shells call the API cross-origin (ADR 0012).
    gateway = { CORS_ORIGINS = "capacitor://localhost,https://localhost" }
    catalog = {
      MEDIA_BUCKET           = aws_s3_bucket.media.bucket
      REQUIRE_PAYABLE_OWNERS = "true"
      ACCEPTING_LISTINGS     = tostring(var.switches.listings)
    }
    matching = {}
    booking  = { ACCEPTING_BOOKINGS = tostring(var.switches.bookings) }
    payments = {
      PAYMENTS_PROVIDER      = "stripe"
      PAYOUTS_ON             = tostring(var.switches.payouts)
      WEB_BASE_URL           = "https://${var.domain}"
      STRIPE_PUBLISHABLE_KEY = "" # replaced from the secret below
    }
    notifications = {
      MAILER       = "ses"
      MAIL_FROM    = "Cappy <no-reply@${var.domain}>"
      USER_POOL_ID = aws_cognito_user_pool.main.id
      WEB_BASE_URL = "https://${var.domain}"
    }
  }
  env = {
    for s in local.services : s => merge(
      local.common_env,
      { for k, v in local.service_env[s] : k => v if v != "" },
      contains(keys(local.consumers), s) ? { EVENT_QUEUE_URL = module.messaging.queue_urls[s] } : {},
    )
  }
  secrets = {
    for s in local.services : s => merge(
      s == "gateway" ? {} : { INTERNAL_TOKEN = aws_secretsmanager_secret.internal_token.arn },
      contains(local.db_services, s) ? { DATABASE_URL = aws_secretsmanager_secret.db_url[s].arn } : {},
      contains(local.read_services, s) ? { DATABASE_READ_URL = aws_secretsmanager_secret.db_read_url[s].arn } : {},
      s == "payments" ? {
        STRIPE_SECRET_KEY      = "${aws_secretsmanager_secret.stripe.arn}:STRIPE_SECRET_KEY::"
        STRIPE_WEBHOOK_SECRET  = "${aws_secretsmanager_secret.stripe.arn}:STRIPE_WEBHOOK_SECRET::"
        STRIPE_PUBLISHABLE_KEY = "${aws_secretsmanager_secret.stripe.arn}:STRIPE_PUBLISHABLE_KEY::"
      } : {},
    )
  }
}

resource "aws_ecs_cluster" "main" {
  name = local.name
  setting {
    name  = "containerInsights"
    value = "enhanced"
  }
  service_connect_defaults {
    namespace = aws_service_discovery_http_namespace.main.arn
  }
}

resource "aws_service_discovery_http_namespace" "main" {
  name = local.name
}

resource "aws_ecr_repository" "service" {
  for_each             = toset(local.services)
  name                 = "cappy/${each.key}"
  image_tag_mutability = "IMMUTABLE"
  force_delete         = var.env != "prod"
  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_lifecycle_policy" "service" {
  for_each   = aws_ecr_repository.service
  repository = each.value.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "keep the last 50 images"
      selection    = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = 50 }
      action       = { type = "expire" }
    }]
  })
}

resource "aws_cloudwatch_log_group" "service" {
  for_each          = toset(concat(local.services, ["migrate"]))
  name              = "/cappy/${var.env}/${each.key}"
  retention_in_days = var.env == "prod" ? 90 : 14
}

# --- network access -------------------------------------------------------------------

resource "aws_security_group" "tasks" {
  name   = "${local.name}-tasks"
  vpc_id = aws_vpc.main.id
}

# Tasks talk to each other (Service Connect) and are reached by the ALB; nothing else.
resource "aws_vpc_security_group_ingress_rule" "tasks_from_tasks" {
  security_group_id            = aws_security_group.tasks.id
  referenced_security_group_id = aws_security_group.tasks.id
  ip_protocol                  = "tcp"
  from_port                    = 8000
  to_port                      = 8000
}

resource "aws_vpc_security_group_ingress_rule" "tasks_from_alb" {
  security_group_id            = aws_security_group.tasks.id
  referenced_security_group_id = aws_security_group.alb.id
  ip_protocol                  = "tcp"
  from_port                    = 8000
  to_port                      = 8000
}

resource "aws_vpc_security_group_egress_rule" "tasks_out" {
  security_group_id = aws_security_group.tasks.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
}

# --- permissions ------------------------------------------------------------------------

data "aws_iam_policy_document" "ecs_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

# Pulls the image, writes logs, reads exactly this service's secrets.
resource "aws_iam_role" "execution" {
  for_each           = toset(concat(local.services, ["migrate"]))
  name               = "${local.name}-${each.key}-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

resource "aws_iam_role_policy_attachment" "execution" {
  for_each   = aws_iam_role.execution
  role       = each.value.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

locals {
  secret_arns = merge(
    { for s in local.services : s => distinct([for v in values(local.secrets[s]) : split(":STRIPE", v)[0]]) },
    { migrate = concat([aws_secretsmanager_secret.db_admin_url.arn], [for s in local.db_services : aws_secretsmanager_secret.db_url[s].arn]) },
  )
}

resource "aws_iam_role_policy" "read_secrets" {
  for_each = aws_iam_role.execution
  role     = each.value.name
  policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Action = "secretsmanager:GetSecretValue", Resource = local.secret_arns[each.key] }]
  })
}

# What each service's code may do in AWS.
locals {
  publishes = ["catalog", "booking", "payments"]
  task_statements = {
    gateway  = []
    matching = []
    catalog = [
      { Effect = "Allow", Action = ["s3:PutObject", "s3:GetObject"], Resource = "${aws_s3_bucket.media.arn}/media/*" },
    ]
    booking  = []
    payments = []
    notifications = [
      { Effect = "Allow", Action = ["ses:SendEmail", "ses:SendRawEmail"], Resource = "*", Condition = { StringEquals = { "ses:FromAddress" = "no-reply@${var.domain}" } } },
      { Effect = "Allow", Action = ["cognito-idp:AdminGetUser", "cognito-idp:ListUsers"], Resource = aws_cognito_user_pool.main.arn },
    ]
  }
}

resource "aws_iam_role" "task" {
  for_each           = toset(local.services)
  name               = "${local.name}-${each.key}-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

resource "aws_iam_role_policy" "task" {
  for_each = aws_iam_role.task
  role     = each.value.name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat(
      local.task_statements[each.key],
      contains(local.publishes, each.key) ? [{ Effect = "Allow", Action = "sns:Publish", Resource = module.messaging.topic_arn }] : [],
      contains(keys(local.consumers), each.key) ? [{
        Effect   = "Allow"
        Action   = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:ChangeMessageVisibility", "sqs:GetQueueAttributes"]
        Resource = module.messaging.queue_arns[each.key]
      }] : [],
      # ECS Exec, for an operator's shell during an incident.
      [{ Effect = "Allow", Action = ["ssmmessages:CreateControlChannel", "ssmmessages:CreateDataChannel", "ssmmessages:OpenControlChannel", "ssmmessages:OpenDataChannel"], Resource = "*" }],
    )
  })
}

# --- tasks and services ---------------------------------------------------------------------

resource "aws_ecs_task_definition" "service" {
  for_each                 = toset(local.services)
  family                   = "${local.name}-${each.key}"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.scale[each.key].cpu
  memory                   = var.scale[each.key].memory
  execution_role_arn       = aws_iam_role.execution[each.key].arn
  task_role_arn            = aws_iam_role.task[each.key].arn
  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }
  # The root filesystem is read-only; uploads over 1 MB spool to /tmp.
  volume {
    name = "tmp"
  }
  container_definitions = jsonencode([{
    name                   = each.key
    mountPoints            = [{ sourceVolume = "tmp", containerPath = "/tmp", readOnly = false }]
    image                  = "${aws_ecr_repository.service[each.key].repository_url}:${var.image_tag}"
    essential              = true
    readonlyRootFilesystem = true
    portMappings           = [{ name = "http", containerPort = 8000, protocol = "tcp", appProtocol = "http" }]
    environment            = [for k, v in local.env[each.key] : { name = k, value = v }]
    secrets                = [for k, v in local.secrets[each.key] : { name = k, valueFrom = v }]
    healthCheck = {
      command     = ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz')"]
      interval    = 10
      timeout     = 3
      retries     = 3
      startPeriod = 20
    }
    stopTimeout = 30
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.service[each.key].name
        awslogs-region        = var.region
        awslogs-stream-prefix = each.key
      }
    }
  }])
}

resource "aws_ecs_service" "service" {
  for_each               = toset(local.services)
  name                   = each.key
  cluster                = aws_ecs_cluster.main.id
  task_definition        = aws_ecs_task_definition.service[each.key].arn
  desired_count          = var.scale[each.key].min
  launch_type            = "FARGATE"
  enable_execute_command = true
  propagate_tags         = "SERVICE"

  network_configuration {
    subnets         = aws_subnet.private[*].id
    security_groups = [aws_security_group.tasks.id]
  }

  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200
  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  service_connect_configuration {
    enabled = true
    dynamic "service" {
      for_each = contains(local.servers, each.key) ? [each.key] : []
      content {
        port_name = "http"
        client_alias {
          port     = 8000
          dns_name = each.key
        }
      }
    }
  }

  dynamic "load_balancer" {
    for_each = each.key == "gateway" ? [1] : []
    content {
      target_group_arn = aws_lb_target_group.gateway.arn
      container_name   = "gateway"
      container_port   = 8000
    }
  }

  lifecycle {
    # Autoscaling owns the count after the first apply.
    ignore_changes = [desired_count]
  }
}

resource "aws_appautoscaling_target" "service" {
  for_each           = toset(local.services)
  service_namespace  = "ecs"
  resource_id        = "service/${aws_ecs_cluster.main.name}/${aws_ecs_service.service[each.key].name}"
  scalable_dimension = "ecs:service:DesiredCount"
  min_capacity       = var.scale[each.key].min
  max_capacity       = var.scale[each.key].max
}

resource "aws_appautoscaling_policy" "cpu" {
  for_each           = aws_appautoscaling_target.service
  name               = "cpu"
  policy_type        = "TargetTrackingScaling"
  service_namespace  = each.value.service_namespace
  resource_id        = each.value.resource_id
  scalable_dimension = each.value.scalable_dimension
  target_tracking_scaling_policy_configuration {
    target_value       = 60
    scale_in_cooldown  = 120
    scale_out_cooldown = 30
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
  }
}

# Consumers wait on I/O (Stripe, SES, the database), so CPU says little about
# how far behind they are: they also scale on their queue's backlog.
resource "aws_appautoscaling_policy" "backlog" {
  for_each           = module.messaging.queue_names
  name               = "backlog"
  policy_type        = "TargetTrackingScaling"
  service_namespace  = aws_appautoscaling_target.service[each.key].service_namespace
  resource_id        = aws_appautoscaling_target.service[each.key].resource_id
  scalable_dimension = aws_appautoscaling_target.service[each.key].scalable_dimension
  target_tracking_scaling_policy_configuration {
    target_value       = 100
    scale_in_cooldown  = 300
    scale_out_cooldown = 60
    customized_metric_specification {
      namespace   = "AWS/SQS"
      metric_name = "ApproximateNumberOfMessagesVisible"
      statistic   = "Average"
      dimensions {
        name  = "QueueName"
        value = each.value
      }
    }
  }
}

resource "aws_appautoscaling_policy" "gateway_requests" {
  name               = "requests"
  policy_type        = "TargetTrackingScaling"
  service_namespace  = aws_appautoscaling_target.service["gateway"].service_namespace
  resource_id        = aws_appautoscaling_target.service["gateway"].resource_id
  scalable_dimension = aws_appautoscaling_target.service["gateway"].scalable_dimension
  target_tracking_scaling_policy_configuration {
    target_value = 500
    predefined_metric_specification {
      predefined_metric_type = "ALBRequestCountPerTarget"
      resource_label         = "${aws_lb.main.arn_suffix}/${aws_lb_target_group.gateway.arn_suffix}"
    }
  }
}

# --- migrations: one-off tasks CD runs before rolling the services ----------------------------------

resource "aws_ecs_task_definition" "migrate" {
  for_each                 = toset(local.db_services)
  family                   = "${local.name}-migrate-${each.key}"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = aws_iam_role.execution["migrate"].arn
  container_definitions = jsonencode([{
    name        = "migrate"
    image       = "${aws_ecr_repository.service[each.key].repository_url}:${var.image_tag}"
    essential   = true
    command     = ["python", "-m", "cappy_common.migrations", each.key]
    environment = [{ name = "APP_ENV", value = var.env }]
    secrets = [
      { name = "DATABASE_URL", valueFrom = aws_secretsmanager_secret.db_url[each.key].arn },
      { name = "ADMIN_DATABASE_URL", valueFrom = aws_secretsmanager_secret.db_admin_url.arn },
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.service["migrate"].name
        awslogs-region        = var.region
        awslogs-stream-prefix = each.key
      }
    }
  }])
}
