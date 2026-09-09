"""Arbiter v0.18 enterprise secrets, provider administration, and key custody.

Design goals:
- raw provider secrets are write-only through the API and never returned
- tenant-scoped model-provider configuration
- local development uses Fernet encryption with a local master key outside git
- production uses AWS Secrets Manager/KMS references; database stores only metadata/ref
- all secret/provider administration is audited
- model providers remain advisory only and receive no settlement authority
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet

from .resolution_infra import canonical_hash, gen_id, utcnow

VERSION = "0.18.0"
SUPPORTED_PROVIDERS = {"openai", "anthropic"}
ALLOWED_PURPOSES = {"contract_triage", "semantic_review", "case_copilot"}


def _mask(secret: str) -> str:
    if not secret:
        return ""
    tail = secret[-4:] if len(secret) >= 4 else "****"
    return f"••••••••{tail}"


def _fingerprint(secret: str) -> str:
    return "sha256:" + hashlib.sha256(secret.encode()).hexdigest()


@dataclass(frozen=True)
class SecretRuntimeConfig:
    backend: str
    local_key_path: str
    aws_region: str
    kms_key_id: str
    production: bool


def load_config() -> SecretRuntimeConfig:
    production = os.environ.get("ARBITER_ENV", "local").strip().lower() == "production"
    backend = os.environ.get("ARBITER_SECRET_BACKEND", "aws-secrets-manager" if production else "local-fernet").strip().lower()
    return SecretRuntimeConfig(
        backend=backend,
        local_key_path=os.environ.get(
            "ARBITER_LOCAL_SECRET_KEY_PATH",
            str(Path(__file__).resolve().parent.parent / "data" / ".local_secret_master_key"),
        ),
        aws_region=os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "us-east-1")),
        kms_key_id=os.environ.get("ARBITER_KMS_KEY_ID", "").strip(),
        production=production,
    )



def configuration_findings() -> list[dict[str, str]]:
    cfg=load_config(); findings=[]
    if cfg.production and cfg.backend != "aws-secrets-manager":
        findings.append({"severity":"BLOCK","code":"PRODUCTION_SECRET_BACKEND_UNSAFE","detail":"Production requires AWS Secrets Manager or an approved external secrets backend."})
    if cfg.production and not cfg.kms_key_id:
        findings.append({"severity":"WARN","code":"KMS_KEY_NOT_EXPLICIT","detail":"Configure ARBITER_KMS_KEY_ID to use a customer-managed KMS key for secret custody."})
    return findings

class _LocalFernetBackend:
    def __init__(self, key_path: str):
        self.path = Path(key_path)

    def _fernet(self) -> Fernet:
        env_key = os.environ.get("ARBITER_LOCAL_SECRET_MASTER_KEY", "").strip()
        if env_key:
            return Fernet(env_key.encode())
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_bytes(Fernet.generate_key())
            try:
                os.chmod(self.path, 0o600)
            except OSError:
                pass
        return Fernet(self.path.read_bytes().strip())

    def put(self, secret_id: str, value: str) -> str:
        return self._fernet().encrypt(value.encode()).decode()

    def get(self, ref: str) -> str:
        return self._fernet().decrypt(ref.encode()).decode()

    def delete(self, ref: str) -> None:
        return None


class _AWSSecretsBackend:
    def __init__(self, cfg: SecretRuntimeConfig):
        self.cfg = cfg

    def _client(self):
        try:
            import boto3
        except ImportError as exc:
            raise RuntimeError("AWS secret backend selected but boto3 is not installed") from exc
        return boto3.client("secretsmanager", region_name=self.cfg.aws_region)

    def put(self, secret_id: str, value: str) -> str:
        name = f"arbiter/{secret_id}"
        client = self._client()
        kwargs: dict[str, Any] = {"Name": name, "SecretString": value}
        if self.cfg.kms_key_id:
            kwargs["KmsKeyId"] = self.cfg.kms_key_id
        try:
            result = client.create_secret(**kwargs)
            return result.get("ARN") or name
        except client.exceptions.ResourceExistsException:
            result = client.put_secret_value(SecretId=name, SecretString=value)
            # put_secret_value does not always return ARN; stable name is a valid reference.
            return result.get("ARN") or name

    def get(self, ref: str) -> str:
        result = self._client().get_secret_value(SecretId=ref)
        value = result.get("SecretString")
        if not isinstance(value, str):
            raise RuntimeError("provider credential is not a string secret")
        return value

    def delete(self, ref: str) -> None:
        self._client().delete_secret(SecretId=ref, RecoveryWindowInDays=7)


class EnterpriseSecretsService:
    def __init__(self, store):
        self.store = store
        self._init_db()

    def _backend(self):
        cfg = load_config()
        if cfg.backend == "local-fernet" and not cfg.production:
            return _LocalFernetBackend(cfg.local_key_path)
        if cfg.backend == "aws-secrets-manager":
            return _AWSSecretsBackend(cfg)
        raise RuntimeError(f"unsupported secret backend: {cfg.backend}")

    def _init_db(self) -> None:
        with self.store.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS secret_records (
                    secret_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    purpose TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    backend TEXT NOT NULL,
                    secret_ref TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    masked_value TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    rotated_at TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS ix_secret_records_tenant ON secret_records(tenant_id, status);
                CREATE TABLE IF NOT EXISTS model_provider_configs (
                    config_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    secret_id TEXT NOT NULL,
                    default_model TEXT NOT NULL,
                    fast_model TEXT NOT NULL,
                    allowed_purposes_json TEXT NOT NULL,
                    daily_max_calls INTEGER NOT NULL DEFAULT 500,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    UNIQUE(tenant_id, provider)
                );
                CREATE INDEX IF NOT EXISTS ix_model_provider_tenant ON model_provider_configs(tenant_id, enabled);
                """
            )
            row = db.execute("SELECT 1 FROM schema_migrations WHERE migration_id=?", ("v0.18-enterprise-secrets",)).fetchone()
            if not row:
                db.execute(
                    "INSERT INTO schema_migrations(migration_id,applied_at,checksum,description) VALUES(?,?,?,?)",
                    ("v0.18-enterprise-secrets", utcnow(), canonical_hash({"migration":"v0.18-enterprise-secrets","tables":2}), "enterprise secrets and tenant model-provider administration"),
                )

    def _public_secret(self, row: Any) -> dict[str, Any]:
        d = dict(row)
        d.pop("secret_ref", None)
        d["metadata"] = json.loads(d.pop("metadata_json") or "{}")
        return d

    def _provider_row(self, row: Any) -> dict[str, Any]:
        d = dict(row)
        d["enabled"] = bool(d["enabled"])
        d["allowed_purposes"] = json.loads(d.pop("allowed_purposes_json") or "[]")
        d["metadata"] = json.loads(d.pop("metadata_json") or "{}")
        return d

    def configure_provider(self, *, tenant_id: str, provider: str, api_key: str, default_model: str, fast_model: str,
                           actor: str, allowed_purposes: list[str] | None = None, daily_max_calls: int = 500,
                           metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        provider = provider.strip().lower()
        if provider not in SUPPORTED_PROVIDERS:
            raise ValueError("unsupported provider")
        if not api_key or len(api_key.strip()) < 8:
            raise ValueError("provider API key is required")
        purposes = sorted(set(allowed_purposes or ALLOWED_PURPOSES))
        invalid = [p for p in purposes if p not in ALLOWED_PURPOSES]
        if invalid:
            raise ValueError("unsupported model purpose: " + ", ".join(invalid))
        if daily_max_calls < 1:
            raise ValueError("daily_max_calls must be >= 1")
        cfg = load_config(); backend = self._backend(); now = utcnow()
        with self.store.connect() as db:
            old = db.execute("SELECT * FROM model_provider_configs WHERE tenant_id=? AND provider=?", (tenant_id, provider)).fetchone()
        secret_id = old["secret_id"] if old else gen_id("secret")
        secret_ref = backend.put(secret_id, api_key.strip())
        fp = _fingerprint(api_key.strip()); masked = _mask(api_key.strip())
        with self.store.connect() as db:
            existing_secret = db.execute("SELECT 1 FROM secret_records WHERE secret_id=?", (secret_id,)).fetchone()
            if existing_secret:
                db.execute("UPDATE secret_records SET backend=?,secret_ref=?,fingerprint=?,masked_value=?,status='active',updated_at=?,rotated_at=?,metadata_json=? WHERE secret_id=?",
                           (cfg.backend, secret_ref, fp, masked, now, now, json.dumps(metadata or {}, sort_keys=True), secret_id))
            else:
                db.execute("INSERT INTO secret_records(secret_id,tenant_id,purpose,provider,backend,secret_ref,fingerprint,masked_value,status,created_at,updated_at,created_by,metadata_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                           (secret_id, tenant_id, "model-provider", provider, cfg.backend, secret_ref, fp, masked, "active", now, now, actor, json.dumps(metadata or {}, sort_keys=True)))
            if old:
                db.execute("UPDATE model_provider_configs SET secret_id=?,default_model=?,fast_model=?,allowed_purposes_json=?,daily_max_calls=?,enabled=1,updated_at=?,metadata_json=? WHERE tenant_id=? AND provider=?",
                           (secret_id, default_model, fast_model, json.dumps(purposes), int(daily_max_calls), now, json.dumps(metadata or {}, sort_keys=True), tenant_id, provider))
                config_id = old["config_id"]
            else:
                config_id = gen_id("modelcfg")
                db.execute("INSERT INTO model_provider_configs(config_id,tenant_id,provider,secret_id,default_model,fast_model,allowed_purposes_json,daily_max_calls,enabled,created_at,updated_at,created_by,metadata_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                           (config_id, tenant_id, provider, secret_id, default_model, fast_model, json.dumps(purposes), int(daily_max_calls), 1, now, now, actor, json.dumps(metadata or {}, sort_keys=True)))
        self.store._audit(actor, "model.provider.configured", "model_provider", config_id, {"tenant_id":tenant_id,"provider":provider,"secret_id":secret_id,"fingerprint":fp,"default_model":default_model,"fast_model":fast_model,"allowed_purposes":purposes,"raw_secret_logged":False,"settlement_authority":False})
        return self.get_provider(tenant_id, provider)

    def get_provider(self, tenant_id: str, provider: str) -> dict[str, Any]:
        with self.store.connect() as db:
            row = db.execute("SELECT * FROM model_provider_configs WHERE tenant_id=? AND provider=?", (tenant_id, provider)).fetchone()
            if not row:
                raise KeyError("model provider not configured")
            secret = db.execute("SELECT * FROM secret_records WHERE secret_id=?", (row["secret_id"],)).fetchone()
        result = self._provider_row(row)
        result["credential"] = self._public_secret(secret) if secret else None
        result["settlement_authority"] = False
        return result

    def list_providers(self, tenant_id: str) -> list[dict[str, Any]]:
        with self.store.connect() as db:
            rows = db.execute("SELECT provider FROM model_provider_configs WHERE tenant_id=? ORDER BY provider", (tenant_id,)).fetchall()
        return [self.get_provider(tenant_id, r["provider"]) for r in rows]

    def disable_provider(self, tenant_id: str, provider: str, actor: str) -> dict[str, Any]:
        with self.store.connect() as db:
            row = db.execute("SELECT config_id,secret_id FROM model_provider_configs WHERE tenant_id=? AND provider=?", (tenant_id, provider)).fetchone()
            if not row: raise KeyError("model provider not configured")
            now=utcnow()
            db.execute("UPDATE model_provider_configs SET enabled=0,updated_at=? WHERE tenant_id=? AND provider=?", (now,tenant_id,provider))
            db.execute("UPDATE secret_records SET status='disabled',updated_at=? WHERE secret_id=?", (now,row["secret_id"]))
        self.store._audit(actor, "model.provider.disabled", "model_provider", row["config_id"], {"tenant_id":tenant_id,"provider":provider,"secret_id":row["secret_id"],"settlement_authority":False})
        return self.get_provider(tenant_id, provider)

    def resolve_provider(self, tenant_id: str, preferred_provider: str | None = None) -> dict[str, Any] | None:
        with self.store.connect() as db:
            if preferred_provider:
                row = db.execute("SELECT * FROM model_provider_configs WHERE tenant_id=? AND provider=? AND enabled=1", (tenant_id, preferred_provider)).fetchone()
            else:
                row = db.execute("SELECT * FROM model_provider_configs WHERE tenant_id=? AND enabled=1 ORDER BY provider LIMIT 1", (tenant_id,)).fetchone()
            if not row: return None
            secret = db.execute("SELECT * FROM secret_records WHERE secret_id=? AND status='active'", (row["secret_id"],)).fetchone()
        if not secret: return None
        value = self._backend().get(secret["secret_ref"])
        d=self._provider_row(row)
        d["api_key"] = value
        return d

    def self_test(self, tenant_id: str = "local", actor: str = "system:secret-self-test") -> dict[str, Any]:
        cfg=load_config()
        sample="sk-arbiter-self-test-1234567890"
        # Use an isolated synthetic tenant so the test can never overwrite a customer's active provider configuration.
        test_tenant=f"__secret_selftest__:{tenant_id}"
        result=self.configure_provider(tenant_id=test_tenant,provider="openai",api_key=sample,default_model="gpt-5.6-sol",fast_model="gpt-5.6-terra",actor=actor,allowed_purposes=["semantic_review","case_copilot"],daily_max_calls=25,metadata={"self_test":True})
        resolved=self.resolve_provider(test_tenant,"openai")
        raw_leaked = sample in json.dumps(result, sort_keys=True)
        ok = bool(resolved and resolved.get("api_key")==sample and not raw_leaked)
        self.disable_provider(test_tenant,"openai",actor)
        return {"ok":ok,"version":VERSION,"backend":cfg.backend,"masked_credential":result["credential"]["masked_value"],"raw_secret_exposed":raw_leaked,"tenant_id":test_tenant,"provider":"openai","allowed_purposes":result["allowed_purposes"],"settlement_authority":False}

    def posture(self, tenant_id: str = "local") -> dict[str, Any]:
        cfg=load_config(); findings=configuration_findings()
        return {"version":VERSION,"backend":cfg.backend,"production":cfg.production,"kms_key_configured":bool(cfg.kms_key_id),"providers":self.list_providers(tenant_id),"raw_secret_read_api":False,"settlement_authority":False,"findings":findings}


_SERVICE: EnterpriseSecretsService | None = None

def get_service(store) -> EnterpriseSecretsService:
    global _SERVICE
    if _SERVICE is None or _SERVICE.store is not store:
        _SERVICE = EnterpriseSecretsService(store)
    return _SERVICE
