resource "aws_db_subnet_group" "this" {
  name       = "${var.name}-db-subnets"
  subnet_ids = [for s in aws_subnet.private : s.id]
  tags       = merge(local.common_tags, { Name = "${var.name}-db-subnets" })
}

resource "aws_db_instance" "postgres" {
  identifier = "${var.name}-postgres"

  engine         = "postgres"
  engine_version = "16"

  instance_class        = var.db_instance_class
  allocated_storage     = var.db_allocated_storage_gb
  max_allocated_storage = max(var.db_allocated_storage_gb, 50)

  db_name  = var.db_name
  username = var.db_username
  password = var.db_password

  db_subnet_group_name   = aws_db_subnet_group.this.name
  vpc_security_group_ids = [aws_security_group.rds.id]

  publicly_accessible = false
  multi_az            = true

  backup_retention_period   = 7
  deletion_protection       = true
  skip_final_snapshot       = false
  final_snapshot_identifier = "${var.name}-postgres-final"

  storage_encrypted = true

  tags = merge(local.common_tags, { Name = "${var.name}-postgres" })
}

locals {
  # SQLAlchemy URL format expected by platform-api.
  # IMPORTANT: URL-encode password so special chars (e.g. '#', ':') don't break URL parsing.
  database_url = "postgresql+psycopg://${var.db_username}:${urlencode(var.db_password)}@${aws_db_instance.postgres.address}:${aws_db_instance.postgres.port}/${var.db_name}"
}


