# Arbiter v0.26.1 — Terraform Validation Fix

Patch release for the v0.22–v0.26 enterprise validation program.

- Rewrote AWS Terraform into canonical multi-line HCL.
- Fixed invalid single-line resource, nested block, variable, and output syntax.
- Added subnet/storage validation constraints.
- Added KMS decrypt permission for the ECS execution role against the Arbiter KMS key.
- Added `scripts/terraform_static_check.py` so malformed compact HCL fails the release gate even when Terraform is unavailable in the packaging environment.
- Kept the deployment boundary unchanged: IaC is a reference deployment until provisioned and exercised in a real staging environment.
