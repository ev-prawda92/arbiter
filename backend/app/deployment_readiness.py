"""Arbiter v0.22 cloud deployment readiness controls.

This module turns the production deployment checklist into executable posture.
It deliberately distinguishes deployable infrastructure-as-code from a deployment
that has actually been provisioned and exercised.
"""
from __future__ import annotations
import os
from pathlib import Path
from typing import Any
from . import production_data, enterprise_secrets, identity_federation, enterprise

VERSION = "0.22.0"
ROOT = Path(__file__).resolve().parents[2]
REQUIRED_ARTIFACTS = (
    "Dockerfile",
    "deploy/aws/main.tf",
    "deploy/aws/variables.tf",
    "deploy/aws/outputs.tf",
    "deploy/aws/README.md",
    "deploy/aws/terraform.tfvars.example",
    "scripts/deployment_preflight.py",
    "scripts/terraform_static_check.py",
)


def artifact_inventory() -> list[dict[str, Any]]:
    out=[]
    for rel in REQUIRED_ARTIFACTS:
        p=ROOT / rel
        out.append({"path":rel,"present":p.exists(),"size":p.stat().st_size if p.exists() else 0})
    return out


def production_requirements() -> dict[str, dict[str, Any]]:
    return {
        "managed_postgresql":{"required":True,"target":"Amazon RDS PostgreSQL Multi-AZ","externally_verified":False},
        "managed_object_storage":{"required":True,"target":"Amazon S3 with versioning + KMS","externally_verified":False},
        "secret_custody":{"required":True,"target":"AWS Secrets Manager + KMS","externally_verified":False},
        "container_runtime":{"required":True,"target":"ECS Fargate behind ALB","externally_verified":False},
        "multi_instance_service":{"required":True,"target":"ECS desired_count >= 2","externally_verified":False},
        "central_logs_metrics":{"required":True,"target":"CloudWatch logs/metrics/alarms","externally_verified":False},
        "tls_ingress":{"required":True,"target":"ALB HTTPS listener with ACM certificate","externally_verified":False},
        "oidc_federation":{"required":True,"target":"enterprise IdP OIDC/JWKS","externally_verified":False},
    }


def posture() -> dict[str, Any]:
    artifacts=artifact_inventory()
    findings=(enterprise.configuration_findings()+production_data.configuration_findings()+enterprise_secrets.configuration_findings()+identity_federation.posture().get("findings",[]))
    return {
        "version":VERSION,
        "deployment_iac_complete":all(a["present"] and a["size"]>0 for a in artifacts),
        "deployment_proven":False,
        "production_environment_detected":os.environ.get("ARBITER_ENV", "development").lower() in {"prod","production"},
        "artifacts":artifacts,
        "runtime_findings":findings,
        "requirements":production_requirements(),
        "boundary":"Infrastructure-as-code and preflight checks are implementation evidence, not proof that cloud resources have been provisioned or validated.",
    }


def self_test() -> dict[str, Any]:
    p=posture()
    return {
        "ok":p["deployment_iac_complete"],
        "artifact_count":len(p["artifacts"]),
        "all_artifacts_present":p["deployment_iac_complete"],
        "production_proven":False,
        "settlement_authority":False,
    }
