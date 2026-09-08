# Arbiter AWS reference deployment

This is a production-shaped **reference architecture**, not evidence that a production environment exists.

It provisions ECS Fargate behind an HTTPS ALB, Multi-AZ RDS PostgreSQL, S3 evidence storage with versioning and KMS encryption, Secrets Manager integration, CloudWatch logs/alarms, and service autoscaling. The service runs at least two tasks.

## Required before apply

Use an existing VPC with at least two private and two public subnets in separate AZs, an ACM certificate, a container image in ECR, and Secrets Manager values for API keys and temporary HMAC signing secrets. Live settlement additionally requires replacing HMAC settlement signing with independently reviewed asymmetric KMS/HSM signing.

```bash
terraform init
terraform fmt -check
terraform validate
terraform plan -var-file=terraform.tfvars
```

Start in a dedicated **staging** AWS account. Do not point a first deployment at live settlement flows.

## Validation boundary

Arbiter's release gate includes an offline HCL shape check so malformed compact
Terraform cannot silently ship again. The authoritative check remains Terraform
itself. Before any plan or apply, run:

```bash
terraform init
terraform fmt -check
terraform validate
```

Do not run `terraform apply` until validation succeeds and the staging inputs have
been reviewed.
