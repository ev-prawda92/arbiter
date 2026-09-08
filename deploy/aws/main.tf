terraform {
  required_version = ">= 1.7.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

provider "aws" {
  region = var.region
}

data "aws_caller_identity" "current" {}

resource "aws_kms_key" "arbiter" {
  description             = "Arbiter evidence and secret encryption"
  deletion_window_in_days = 30
  enable_key_rotation     = true
}

resource "aws_kms_alias" "arbiter" {
  name          = "alias/${var.name}-${var.environment}"
  target_key_id = aws_kms_key.arbiter.key_id
}

resource "aws_s3_bucket" "evidence" {
  bucket_prefix = "${var.name}-${var.environment}-evidence-"
  force_destroy = false
}

resource "aws_s3_bucket_versioning" "evidence" {
  bucket = aws_s3_bucket.evidence.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "evidence" {
  bucket = aws_s3_bucket.evidence.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.arbiter.arn
    }

    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "evidence" {
  bucket = aws_s3_bucket.evidence.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "random_password" "db" {
  length  = 32
  special = false
}

resource "aws_security_group" "db" {
  name_prefix = "${var.name}-${var.environment}-db-"
  vpc_id      = var.vpc_id
}

resource "aws_security_group" "service" {
  name_prefix = "${var.name}-${var.environment}-svc-"
  vpc_id      = var.vpc_id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group_rule" "db_from_service" {
  type                     = "ingress"
  security_group_id        = aws_security_group.db.id
  source_security_group_id = aws_security_group.service.id
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
}

resource "aws_db_subnet_group" "arbiter" {
  name       = "${var.name}-${var.environment}"
  subnet_ids = var.private_subnet_ids
}

resource "aws_db_instance" "arbiter" {
  identifier_prefix            = "${var.name}-${var.environment}-"
  engine                       = "postgres"
  engine_version               = "16"
  instance_class               = var.db_instance_class
  allocated_storage            = var.db_allocated_storage
  max_allocated_storage        = max(var.db_allocated_storage * 4, 200)
  storage_encrypted            = true
  kms_key_id                   = aws_kms_key.arbiter.arn
  username                     = "arbiter"
  password                     = random_password.db.result
  db_name                      = "arbiter"
  port                         = 5432
  multi_az                     = true
  backup_retention_period      = 14
  deletion_protection          = true
  auto_minor_version_upgrade   = true
  performance_insights_enabled = true
  db_subnet_group_name         = aws_db_subnet_group.arbiter.name
  vpc_security_group_ids       = [aws_security_group.db.id]
  skip_final_snapshot          = false
}

resource "aws_secretsmanager_secret" "database_url" {
  name_prefix = "${var.name}/${var.environment}/database-url-"
  kms_key_id  = aws_kms_key.arbiter.arn
}

resource "aws_secretsmanager_secret_version" "database_url" {
  secret_id     = aws_secretsmanager_secret.database_url.id
  secret_string = "postgresql://arbiter:${random_password.db.result}@${aws_db_instance.arbiter.address}:5432/arbiter?sslmode=require"
}

resource "aws_cloudwatch_log_group" "app" {
  name              = "/ecs/${var.name}-${var.environment}"
  retention_in_days = 30
  kms_key_id        = aws_kms_key.arbiter.arn
}

resource "aws_ecs_cluster" "arbiter" {
  name = "${var.name}-${var.environment}"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

resource "aws_iam_role" "execution" {
  name_prefix = "${var.name}-${var.environment}-exec-"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "execution" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role" "task" {
  name_prefix        = "${var.name}-${var.environment}-task-"
  assume_role_policy = aws_iam_role.execution.assume_role_policy
}

resource "aws_iam_role_policy" "task" {
  role = aws_iam_role.task.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject", "s3:HeadObject"]
        Resource = ["${aws_s3_bucket.evidence.arn}/*"]
      },
      {
        Effect   = "Allow"
        Action   = ["kms:Encrypt", "kms:Decrypt", "kms:GenerateDataKey", "kms:Sign", "kms:GetPublicKey"]
        Resource = [aws_kms_key.arbiter.arn]
      },
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue",
          "secretsmanager:PutSecretValue",
          "secretsmanager:CreateSecret",
          "secretsmanager:DescribeSecret"
        ]
        Resource = [
          "arn:aws:secretsmanager:${var.region}:${data.aws_caller_identity.current.account_id}:secret:${var.name}/${var.environment}/*"
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy" "execution_secrets" {
  role = aws_iam_role.execution.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = [
          aws_secretsmanager_secret.database_url.arn,
          var.api_key_secret_arn,
          var.settlement_signing_secret_arn,
          var.webhook_signing_secret_arn
        ]
      },
      {
        Effect   = "Allow"
        Action   = ["kms:Decrypt"]
        Resource = [aws_kms_key.arbiter.arn]
      }
    ]
  })
}

resource "aws_security_group" "alb" {
  name_prefix = "${var.name}-${var.environment}-alb-"
  vpc_id      = var.vpc_id

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_lb" "arbiter" {
  name_prefix        = "arb-"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = var.public_subnet_ids
}

resource "aws_security_group_rule" "service_from_alb" {
  type                     = "ingress"
  security_group_id        = aws_security_group.service.id
  source_security_group_id = aws_security_group.alb.id
  from_port                = 8000
  to_port                  = 8000
  protocol                 = "tcp"
}

resource "aws_lb_target_group" "arbiter" {
  name_prefix = "arb-"
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip"

  health_check {
    path                = "/api/readiness"
    matcher             = "200"
    interval            = 30
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }
}

resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.arbiter.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = var.certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.arbiter.arn
  }
}

locals {
  common_environment = [
    { name = "ARBITER_ENV", value = "production" },
    { name = "ARBITER_DATABASE_BACKEND", value = "postgresql" },
    { name = "ARBITER_DATABASE_SSLMODE", value = "require" },
    { name = "ARBITER_OBJECT_STORE_BACKEND", value = "s3" },
    { name = "ARBITER_S3_BUCKET", value = aws_s3_bucket.evidence.bucket },
    { name = "ARBITER_S3_KMS_KEY_ID", value = aws_kms_key.arbiter.arn },
    { name = "ARBITER_SECRET_BACKEND", value = "aws-secrets-manager" },
    { name = "ARBITER_OIDC_ISSUER", value = var.oidc_issuer },
    { name = "ARBITER_OIDC_AUDIENCE", value = var.oidc_audience },
    { name = "ARBITER_OIDC_JWKS_URL", value = var.oidc_jwks_url }
  ]
}

resource "aws_ecs_task_definition" "arbiter" {
  family                   = "${var.name}-${var.environment}"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "1024"
  memory                   = "2048"
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([
    {
      name      = "arbiter"
      image     = var.container_image
      essential = true
      portMappings = [
        {
          containerPort = 8000
          protocol      = "tcp"
        }
      ]
      environment = local.common_environment
      secrets = [
        {
          name      = "ARBITER_DATABASE_URL"
          valueFrom = aws_secretsmanager_secret.database_url.arn
        },
        {
          name      = "ARBITER_API_KEYS"
          valueFrom = var.api_key_secret_arn
        },
        {
          name      = "ARBITER_SETTLEMENT_SIGNING_SECRET"
          valueFrom = var.settlement_signing_secret_arn
        },
        {
          name      = "ARBITER_WEBHOOK_SIGNING_SECRET"
          valueFrom = var.webhook_signing_secret_arn
        }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.app.name
          "awslogs-region"        = var.region
          "awslogs-stream-prefix" = "arbiter"
        }
      }
      healthCheck = {
        command = [
          "CMD-SHELL",
          "python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health',timeout=3)\" || exit 1"
        ]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 20
      }
    }
  ])
}

resource "aws_ecs_service" "arbiter" {
  name            = "${var.name}-${var.environment}"
  cluster         = aws_ecs_cluster.arbiter.id
  task_definition = aws_ecs_task_definition.arbiter.arn
  desired_count   = max(var.desired_count, 2)
  launch_type     = "FARGATE"

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [aws_security_group.service.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.arbiter.arn
    container_name   = "arbiter"
    container_port   = 8000
  }

  depends_on = [aws_lb_listener.https]
}

resource "aws_appautoscaling_target" "service" {
  max_capacity       = var.max_count
  min_capacity       = max(var.min_count, 2)
  resource_id        = "service/${aws_ecs_cluster.arbiter.name}/${aws_ecs_service.arbiter.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

resource "aws_appautoscaling_policy" "cpu" {
  name               = "cpu"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.service.resource_id
  scalable_dimension = aws_appautoscaling_target.service.scalable_dimension
  service_namespace  = aws_appautoscaling_target.service.service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }

    target_value       = 60
    scale_in_cooldown  = 120
    scale_out_cooldown = 60
  }
}

resource "aws_cloudwatch_metric_alarm" "unhealthy" {
  alarm_name          = "${var.name}-${var.environment}-unhealthy-targets"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "UnHealthyHostCount"
  namespace           = "AWS/ApplicationELB"
  period              = 60
  statistic           = "Maximum"
  threshold           = 0
  alarm_description   = "Arbiter has unhealthy ALB targets"

  dimensions = {
    TargetGroup  = aws_lb_target_group.arbiter.arn_suffix
    LoadBalancer = aws_lb.arbiter.arn_suffix
  }
}
