"""Arbiter v0.24 external assurance evidence registry.

Stores metadata and cryptographic fingerprints for independent reviews/tests.
It cannot manufacture third-party assurance and never marks Arbiter certified merely
because a record was entered.
"""
from __future__ import annotations
import json
from typing import Any
from .resolution_infra import gen_id, utcnow, canonical_hash

VERSION="0.24.0"
ARTIFACT_TYPES={
 "security_architecture_review","penetration_test","production_load_test",
 "backup_restore_drill","multi_zone_failover_drill","incident_response_exercise",
 "shadow_pilot_report","holdout_evaluation"
}

class ExternalAssuranceService:
    def __init__(self,store):self.store=store;self._init_db()
    def _init_db(self):
        with self.store.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS external_assurance_artifacts(
              artifact_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, artifact_type TEXT NOT NULL,
              provider TEXT NOT NULL, performed_at TEXT NOT NULL, recorded_at TEXT NOT NULL,
              result TEXT NOT NULL, scope_json TEXT NOT NULL, evidence_uri TEXT NOT NULL,
              evidence_sha256 TEXT NOT NULL, independent INTEGER NOT NULL, actor TEXT NOT NULL,
              metadata_json TEXT NOT NULL
            );
            """)
    def record(self,tenant_id:str,artifact_type:str,provider:str,performed_at:str,result:str,scope:dict[str,Any],evidence_uri:str,evidence_sha256:str,independent:bool,actor:str,metadata:dict[str,Any]|None=None):
        if artifact_type not in ARTIFACT_TYPES:raise ValueError("unsupported assurance artifact type")
        if not provider.strip():raise ValueError("provider/reviewer is required")
        result=result.upper()
        if result not in {"PASS","FAIL","OBSERVATIONS"}:raise ValueError("result must be PASS, FAIL, or OBSERVATIONS")
        digest=evidence_sha256.strip().lower()
        if len(digest)!=64 or any(c not in "0123456789abcdef" for c in digest):raise ValueError("evidence_sha256 must be a 64-character SHA-256 hex digest")
        aid=gen_id("assurance_ext"); now=utcnow(); meta=metadata or {}
        with self.store.connect() as db: db.execute("INSERT INTO external_assurance_artifacts(artifact_id,tenant_id,artifact_type,provider,performed_at,recorded_at,result,scope_json,evidence_uri,evidence_sha256,independent,actor,metadata_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",(aid,tenant_id,artifact_type,provider,performed_at,now,result,json.dumps(scope,sort_keys=True),evidence_uri,digest,1 if independent else 0,actor,json.dumps(meta,sort_keys=True)))
        self.store._audit(actor,"external_assurance.recorded","external_assurance_artifact",aid,{"tenant_id":tenant_id,"artifact_type":artifact_type,"provider":provider,"result":result,"independent":independent,"evidence_sha256":digest})
        return self.get(tenant_id,aid)
    def get(self,tenant_id,artifact_id):
        with self.store.connect() as db:r=db.execute("SELECT * FROM external_assurance_artifacts WHERE tenant_id=? AND artifact_id=?",(tenant_id,artifact_id)).fetchone()
        if not r:raise KeyError("unknown assurance artifact")
        d=dict(r);d["scope"]=json.loads(d.pop("scope_json"));d["metadata"]=json.loads(d.pop("metadata_json"));d["independent"]=bool(d["independent"]);return d
    def list(self,tenant_id):
        with self.store.connect() as db:rows=db.execute("SELECT * FROM external_assurance_artifacts WHERE tenant_id=? ORDER BY performed_at DESC",(tenant_id,)).fetchall()
        out=[]
        for r in rows:
            d=dict(r);d["scope"]=json.loads(d.pop("scope_json"));d["metadata"]=json.loads(d.pop("metadata_json"));d["independent"]=bool(d["independent"]);out.append(d)
        return out
    def posture(self,tenant_id="local"):
        artifacts=self.list(tenant_id); passed={a["artifact_type"] for a in artifacts if a["result"]=="PASS" and a["independent"]}
        required={"security_architecture_review","penetration_test","production_load_test","backup_restore_drill","multi_zone_failover_drill","incident_response_exercise"}
        return {"version":VERSION,"artifact_count":len(artifacts),"independent_passed":sorted(passed),"missing_independent_evidence":sorted(required-passed),"external_assurance_complete":required.issubset(passed),"production_settlement_certified":False,"boundary":"Recorded evidence can support diligence; certification remains an external governance decision."}
    def self_test(self,tenant_id="local",actor="system:v0.24-self-test"):
        digest=canonical_hash({"synthetic":"security-review-self-test"}).replace("sha256:",""); a=self.record(tenant_id,"security_architecture_review","synthetic:self-test",utcnow(),"OBSERVATIONS",{"synthetic":True},"synthetic://self-test",digest,False,actor,{"self_test":True}); p=self.posture(tenant_id)
        return {"ok":a["evidence_sha256"]==digest and not p["production_settlement_certified"],"artifact":a,"posture":p,"settlement_authority":False}

_SERVICE=None
def get_service(store):
    global _SERVICE
    if _SERVICE is None or _SERVICE.store is not store:_SERVICE=ExternalAssuranceService(store)
    return _SERVICE
