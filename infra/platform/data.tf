# Aurora PostgreSQL Serverless v2: a writer and a reader in different AZs,
# one database and one role per service (created by each migrate task).

locals {
  db_services = ["catalog", "booking", "payments", "notifications"]
  consumers = {
    catalog       = ["booking.rated", "payment.payouts_ready", "booking.renter_rated", "booking.owner_reliability", "moderation.person_flagged"]
    booking       = ["payment.authorised", "payment.failed", "listing.changed", "moderation.owner_suspended", "payment.identity_verified", "profile.deleted", "person.signed_out", "moderation.owner_reinstated"]
    payments      = ["booking.status_changed", "profile.deleted", "person.signed_out"]
    notifications = ["booking.status_changed", "payment.payout_sent", "profile.deleted", "person.signed_out", "booking.message", "moderation.report_received", "moderation.decision"]
  }
}

module "messaging" {
  source    = "../modules/messaging"
  name      = local.name
  consumers = local.consumers
}

resource "aws_db_subnet_group" "main" {
  name       = local.name
  subnet_ids = aws_subnet.private[*].id
}

resource "aws_security_group" "db" {
  name   = "${local.name}-db"
  vpc_id = aws_vpc.main.id
}

resource "aws_vpc_security_group_ingress_rule" "db_from_tasks" {
  security_group_id            = aws_security_group.db.id
  referenced_security_group_id = aws_security_group.tasks.id
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
}

resource "random_password" "db_admin" {
  length  = 40
  special = false
}

resource "aws_rds_cluster_parameter_group" "main" {
  name   = local.name
  family = "aurora-postgresql16"
  parameter {
    name  = "rds.force_ssl"
    value = "1"
  }
  parameter {
    name  = "log_min_duration_statement"
    value = "500"
  }
}

resource "aws_rds_cluster" "main" {
  cluster_identifier              = local.name
  engine                          = "aurora-postgresql"
  engine_mode                     = "provisioned"
  engine_version                  = "16.6"
  database_name                   = "cappy"
  master_username                 = "cappy_admin"
  master_password                 = random_password.db_admin.result
  db_subnet_group_name            = aws_db_subnet_group.main.name
  vpc_security_group_ids          = [aws_security_group.db.id]
  db_cluster_parameter_group_name = aws_rds_cluster_parameter_group.main.name
  storage_encrypted               = true
  backup_retention_period         = var.env == "prod" ? 14 : 3
  preferred_backup_window         = "02:00-03:00"
  copy_tags_to_snapshot           = true
  deletion_protection             = var.env == "prod"
  skip_final_snapshot             = var.env != "prod"
  final_snapshot_identifier       = "${local.name}-final"
  enabled_cloudwatch_logs_exports = ["postgresql"]

  serverlessv2_scaling_configuration {
    min_capacity = var.db_min_acu
    max_capacity = var.db_max_acu
  }
}

resource "aws_rds_cluster_instance" "main" {
  count = var.db_instances
  # Readers in tier 1 scale with the writer, so a failover lands on a warm one.
  promotion_tier               = 1
  identifier                   = "${local.name}-${count.index}"
  cluster_identifier           = aws_rds_cluster.main.id
  instance_class               = "db.serverless"
  engine                       = aws_rds_cluster.main.engine
  engine_version               = aws_rds_cluster.main.engine_version
  performance_insights_enabled = true
  auto_minor_version_upgrade   = true
}

resource "random_password" "db_service" {
  for_each = toset(local.db_services)
  length   = 40
  special  = false
}

# Services read DATABASE_URL from here; only the migrate task sees the admin one.
resource "aws_secretsmanager_secret" "db_url" {
  for_each = toset(local.db_services)
  name     = "${local.name}/${each.key}/database-url"
}

resource "aws_secretsmanager_secret_version" "db_url" {
  for_each      = toset(local.db_services)
  secret_id     = aws_secretsmanager_secret.db_url[each.key].id
  secret_string = "postgresql+asyncpg://${each.key}:${random_password.db_service[each.key].result}@${aws_rds_cluster.main.endpoint}:5432/${each.key}?ssl=require"
}

# The reader endpoint, for services whose public reads can lag a few ms.
locals {
  read_services = ["catalog", "booking"]
}

resource "aws_secretsmanager_secret" "db_read_url" {
  for_each = toset(local.read_services)
  name     = "${local.name}/${each.key}/database-read-url"
}

resource "aws_secretsmanager_secret_version" "db_read_url" {
  for_each      = toset(local.read_services)
  secret_id     = aws_secretsmanager_secret.db_read_url[each.key].id
  secret_string = "postgresql+asyncpg://${each.key}:${random_password.db_service[each.key].result}@${aws_rds_cluster.main.reader_endpoint}:5432/${each.key}?ssl=require"
}

resource "aws_secretsmanager_secret" "db_admin_url" {
  name = "${local.name}/database-admin-url"
}

resource "aws_secretsmanager_secret_version" "db_admin_url" {
  secret_id     = aws_secretsmanager_secret.db_admin_url.id
  secret_string = "postgresql+asyncpg://cappy_admin:${random_password.db_admin.result}@${aws_rds_cluster.main.endpoint}:5432/cappy?ssl=require"
}

# Who may call whom on /internal/* (P-10): the call graph, nothing more. Each
# service holds only its own token; the services it calls hold its hash.
locals {
  internal_callers = {
    catalog       = ["matching", "booking"]
    matching      = ["booking"]
    booking       = ["matching", "catalog"]
    payments      = ["booking", "catalog"]
    notifications = ["catalog"]
  }
}

resource "random_password" "internal_token" {
  for_each = local.internal_callers
  length   = 48
  special  = false
}

resource "aws_secretsmanager_secret" "internal_token" {
  for_each = local.internal_callers
  name     = "${local.name}/internal-token/${each.key}"
}

resource "aws_secretsmanager_secret_version" "internal_token" {
  for_each      = local.internal_callers
  secret_id     = aws_secretsmanager_secret.internal_token[each.key].id
  secret_string = "${each.key}:${random_password.internal_token[each.key].result}"
}

# Values are put in by an operator (docs/runbook.md), never by Terraform, so
# the keys never reach state or the repository.
resource "aws_secretsmanager_secret" "stripe" {
  name = "${local.name}/stripe"
}

# --- the connection budget (research: Aurora Serverless v2 max_connections is
# fixed by the maximum ACU, and ECS autoscaling is how it runs out) ---------------
locals {
  # Per task: SQLAlchemy pool 5 + overflow 10, for the writer and (where
  # configured) the reader. Deploys run up to 200% of tasks.
  connections_per_task = 15
  peak_connections = 2 * sum([
    for s in local.db_services : var.scale[s].max * local.connections_per_task * (contains(local.read_services, s) ? 2 : 1)
  ])
  # max_connections = min(5000, instance memory / 9531392); 1 ACU = 2 GiB.
  max_connections = min(5000, floor(var.db_max_acu * 2147483648 / 9531392))
}

check "connection_budget" {
  assert {
    condition     = local.peak_connections < 0.8 * local.max_connections
    error_message = "At full scale during a deploy the services could open ${local.peak_connections} connections, over 80% of the ${local.max_connections} Aurora allows at ${var.db_max_acu} ACU: raise db_max_acu, lower task maxima, or add RDS Proxy (T-24)."
  }
}

resource "aws_cloudwatch_metric_alarm" "replica_lag" {
  alarm_name          = "${local.name}-replica-lag"
  alarm_description   = "Reader more than 1 s behind: public reads are stale; check write load"
  namespace           = "AWS/RDS"
  metric_name         = "AuroraReplicaLag"
  dimensions          = { DBClusterIdentifier = aws_rds_cluster.main.cluster_identifier }
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 5
  threshold           = 1000
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions
}
