# Aurora PostgreSQL Serverless v2: a writer and a reader in different AZs,
# one database and one role per service (created by each migrate task).

locals {
  db_services = ["catalog", "booking", "payments", "notifications"]
  consumers = {
    catalog       = ["booking.rated", "payment.payouts_ready"]
    booking       = ["payment.authorised", "payment.failed"]
    payments      = ["booking.status_changed", "profile.deleted"]
    notifications = ["booking.status_changed", "payment.payout_sent"]
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
  count                        = var.db_instances
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

resource "aws_secretsmanager_secret" "db_admin_url" {
  name = "${local.name}/database-admin-url"
}

resource "aws_secretsmanager_secret_version" "db_admin_url" {
  secret_id     = aws_secretsmanager_secret.db_admin_url.id
  secret_string = "postgresql+asyncpg://cappy_admin:${random_password.db_admin.result}@${aws_rds_cluster.main.endpoint}:5432/cappy?ssl=require"
}

resource "random_password" "internal_token" {
  length  = 48
  special = false
}

resource "aws_secretsmanager_secret" "internal_token" {
  name = "${local.name}/internal-token"
}

resource "aws_secretsmanager_secret_version" "internal_token" {
  secret_id     = aws_secretsmanager_secret.internal_token.id
  secret_string = random_password.internal_token.result
}

# Values are put in by an operator (docs/runbook.md), never by Terraform, so
# the keys never reach state or the repository.
resource "aws_secretsmanager_secret" "stripe" {
  name = "${local.name}/stripe"
}
