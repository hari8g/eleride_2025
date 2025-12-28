resource "aws_ecr_repository" "contract_service" {
  name                 = "${var.name}/contract-service"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = merge(local.common_tags, { Name = "${var.name}-ecr-contract-service" })
}

resource "aws_cloudwatch_log_group" "contract_service" {
  name              = "/ecs/${var.name}/contract-service"
  retention_in_days = 14
  tags              = merge(local.common_tags, { Name = "${var.name}-lg-contract-service" })
}

resource "aws_lb_target_group" "contract_service" {
  name        = "${var.name}-contract-service-tg"
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = aws_vpc.this.id
  target_type = "ip"

  health_check {
    path                = "/health"
    interval            = 30
    timeout             = 10
    healthy_threshold   = 2
    unhealthy_threshold = 5
    matcher             = "200"
  }

  tags = merge(local.common_tags, { Name = "${var.name}-contract-service-tg" })
}

resource "aws_lb_listener_rule" "contract_service" {
  listener_arn = aws_lb_listener.http.arn
  priority     = 10  # Higher priority (lower number) to match before default rule

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.contract_service.arn
  }

  condition {
    path_pattern {
      values = ["/contracts/*"]
    }
  }

  depends_on = [aws_lb_listener.http]
}

resource "aws_ecs_task_definition" "contract_service" {
  family                   = "${var.name}-contract-service"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "256"
  memory                   = "512"

  execution_role_arn = aws_iam_role.ecs_task_execution.arn
  task_role_arn      = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([
    {
      name      = "contract-service"
      image     = "${aws_ecr_repository.contract_service.repository_url}:latest"
      essential = true
      portMappings = [
        {
          containerPort = 8000
          hostPort      = 8000
          protocol      = "tcp"
        }
      ]
      environment = [
        { name = "ENV", value = var.platform_api_env },
        { name = "APP_NAME", value = "eleride-contract-service" },
        { name = "TEMPLATE_DIR", value = "/app/templates" },
        { name = "GENERATED_DIR", value = "/app/generated" },
        { name = "LIBREOFFICE_PATH", value = "/usr/bin/libreoffice" },
        { name = "ENABLE_PDF", value = "true" },
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.contract_service.name
          awslogs-region        = data.aws_region.current.name
          awslogs-stream-prefix = "ecs"
        }
      }
    }
  ])

  tags = merge(local.common_tags, { Name = "${var.name}-taskdef-contract-service" })
}

resource "aws_ecs_service" "contract_service" {
  name            = "${var.name}-contract-service"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.contract_service.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = [for s in aws_subnet.private : s.id]
    security_groups  = [aws_security_group.ecs.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.contract_service.arn
    container_name   = "contract-service"
    container_port   = 8000
  }

  deployment_minimum_healthy_percent = 50
  deployment_maximum_percent         = 200
  health_check_grace_period_seconds  = 60

  depends_on = [aws_lb_listener.http]

  tags = merge(local.common_tags, { Name = "${var.name}-svc-contract-service" })
}

