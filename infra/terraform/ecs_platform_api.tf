resource "aws_ecr_repository" "platform_api" {
  name                 = "${var.name}/platform-api"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = merge(local.common_tags, { Name = "${var.name}-ecr-platform-api" })
}

resource "aws_cloudwatch_log_group" "platform_api" {
  name              = "/ecs/${var.name}/platform-api"
  retention_in_days = 14
  tags              = merge(local.common_tags, { Name = "${var.name}-lg-platform-api" })
}

resource "aws_ecs_cluster" "this" {
  name = "${var.name}-cluster"
  tags = merge(local.common_tags, { Name = "${var.name}-cluster" })
}

data "aws_iam_policy_document" "ecs_task_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ecs_task_execution" {
  name               = "${var.name}-ecs-task-exec"
  assume_role_policy = data.aws_iam_policy_document.ecs_task_assume.json
  tags               = local.common_tags
}

resource "aws_iam_role_policy_attachment" "ecs_task_execution_policy" {
  role       = aws_iam_role.ecs_task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role" "ecs_task" {
  name               = "${var.name}-ecs-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_task_assume.json
  tags               = local.common_tags
}

resource "aws_lb" "api" {
  name               = "${var.name}-api-alb"
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = [for s in aws_subnet.public : s.id]
  tags               = merge(local.common_tags, { Name = "${var.name}-api-alb" })
}

resource "aws_lb_target_group" "api" {
  name        = "${var.name}-api-tg"
  port        = var.platform_api_container_port
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

  tags = merge(local.common_tags, { Name = "${var.name}-api-tg" })
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.api.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
}

resource "aws_ecs_task_definition" "platform_api" {
  family                   = "${var.name}-platform-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = tostring(var.platform_api_cpu)
  memory                   = tostring(var.platform_api_memory)

  execution_role_arn = aws_iam_role.ecs_task_execution.arn
  task_role_arn      = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([
    {
      name      = "platform-api"
      image     = "${aws_ecr_repository.platform_api.repository_url}:latest"
      essential = true
      portMappings = [
        {
          containerPort = var.platform_api_container_port
          hostPort      = var.platform_api_container_port
          protocol      = "tcp"
        }
      ]
      environment = [
        { name = "ENV", value = var.platform_api_env },
        { name = "APP_NAME", value = "eleride-platform-api" },
        { name = "JWT_SECRET", value = var.jwt_secret },
        { name = "JWT_ISSUER", value = "eleride" },
        { name = "JWT_AUDIENCE", value = "eleride-rider" },
        { name = "DATABASE_URL", value = local.database_url },
        { name = "REDIS_URL", value = "" }, # add ElastiCache later
        { name = "CORS_ALLOW_ORIGINS", value = local.cors_allow_origins_effective },
        { name = "OTP_DEV_MODE", value = tostring(var.otp_dev_mode) },

        { name = "MSG91_API_KEY", value = var.msg91_api_key },
        { name = "MSG91_SENDER_ID", value = var.msg91_sender_id },
        { name = "MSG91_OTP_TEMPLATE_ID", value = var.msg91_otp_template_id },
        { name = "MSG91_WHATSAPP_FLOW_ID", value = var.msg91_whatsapp_flow_id },
        { name = "MSG91_WHATSAPP_OTP_VAR", value = var.msg91_whatsapp_otp_var },
        { name = "MSG91_OTP_CHANNEL_ORDER", value = var.msg91_otp_channel_order },
        { name = "CASHFLOW_DATA_DIR", value = "/app/cashflow_data" },
        { name = "CONTRACT_SERVICE_URL", value = "http://${aws_lb.api.dns_name}/contracts" },
        { name = "CONTRACT_SERVICE_URL_EXTERNAL", value = local.enable_custom_domain && local.domain_api != null ? "https://${local.domain_api}/contracts" : "https://${aws_cloudfront_distribution.api.domain_name}/contracts" }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.platform_api.name
          awslogs-region        = data.aws_region.current.name
          awslogs-stream-prefix = "ecs"
        }
      }
    }
  ])

  tags = merge(local.common_tags, { Name = "${var.name}-taskdef-platform-api" })
}

resource "aws_ecs_service" "platform_api" {
  name            = "${var.name}-platform-api"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.platform_api.arn
  desired_count   = var.platform_api_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = [for s in aws_subnet.private : s.id]
    security_groups  = [aws_security_group.ecs.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "platform-api"
    container_port   = var.platform_api_container_port
  }

  deployment_minimum_healthy_percent = 50
  deployment_maximum_percent         = 200
  health_check_grace_period_seconds  = 60

  depends_on = [aws_lb_listener.http]

  tags = merge(local.common_tags, { Name = "${var.name}-svc-platform-api" })
}


