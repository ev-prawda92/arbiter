output "alb_dns_name" {
  value = aws_lb.arbiter.dns_name
}

output "rds_endpoint" {
  value     = aws_db_instance.arbiter.address
  sensitive = true
}

output "evidence_bucket" {
  value = aws_s3_bucket.evidence.bucket
}

output "kms_key_arn" {
  value = aws_kms_key.arbiter.arn
}

output "ecs_cluster" {
  value = aws_ecs_cluster.arbiter.name
}

output "ecs_service" {
  value = aws_ecs_service.arbiter.name
}
