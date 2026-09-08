"""Arbiter v0.23 resilience validation lab.

Provides deterministic local stress/failure scenarios and a registry for deployed
load/DR/failover evidence. Local scenarios are not substitutes for cloud exercises.
"""
from __future__ import annotations
import json, time
from typing import Any
from .resolution_infra import gen_id, utcnow, canonical_hash
from . import compiler, semantic_contract

VERSION="0.23.0"
LOCAL_SCENARIOS={"compiler_stress","audit_integrity","duplicate_write_guard"}
EXTERNAL_SCENARIOS={"production_load","backup_restore","multi_zone_failover","worker_recovery","dependency_outage"}

class ResilienceLabService:
    def __init__(self,store): self.store=store; self._init_db()
    def _init_db(self):
        with self.store.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS resilience_runs(
              resilience_run_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, scenario TEXT NOT NULL,
              environment TEXT NOT NULL, started_at TEXT NOT NULL, completed_at TEXT NOT NULL,
              status TEXT NOT NULL, metrics_json TEXT NOT NULL, evidence_hash TEXT NOT NULL,
              actor TEXT NOT NULL, external INTEGER NOT NULL DEFAULT 0
            );
            """)
    def run_local(self,tenant_id:str,scenario:str,actor:str,iterations:int=25):
        if scenario not in LOCAL_SCENARIOS: raise ValueError("unsupported local resilience scenario")
        iterations=max(1,min(int(iterations),500)); start=utcnow(); t0=time.perf_counter(); details=[]
        if scenario=="compiler_stress":
            authorities=self.store.list_authorities(); title="Will U.S. CPI be above 3.0% on September 11, 2026?"; rules="This market resolves YES if the U.S. Bureau of Labor Statistics reports CPI above 3.0% on September 11, 2026 at 08:30 EDT. The first published release controls."
            for i in range(iterations):
                sem=semantic_contract.analyze_contract(title,rules); comp=compiler.compile_rules(f"stress_{i}",title,rules,authorities,metadata={"resilience":True}); details.append({"i":i,"semantic":sem.get("status"),"compiler":comp.get("status")})
            ok=all(d["compiler"] in {"READY","REVIEW","BLOCK"} for d in details)
        elif scenario=="audit_integrity":
            for i in range(iterations): self.store._audit(actor,"resilience.synthetic_event","resilience_run","pending",{"tenant_id":tenant_id,"i":i})
            chain=self.store.verify_audit_chain(); details=[chain]; ok=bool(chain.get("ok"))
        else:
            # Canonical hashing must remain stable for duplicate request bodies.
            sample={"tenant_id":tenant_id,"op":"settlement_authorization","contract":"synthetic","amount":0}
            hashes=[canonical_hash(sample) for _ in range(iterations)]; details=[{"unique_hashes":len(set(hashes)),"hash":hashes[0]}]; ok=len(set(hashes))==1
        elapsed=max(time.perf_counter()-t0,1e-9); metrics={"iterations":iterations,"elapsed_seconds":round(elapsed,6),"ops_per_second":round(iterations/elapsed,2),"details":details[:10]}
        return self._record(tenant_id,scenario,"local",start,utcnow(),"PASS" if ok else "FAIL",metrics,actor,False)
    def record_external(self,tenant_id:str,scenario:str,environment:str,status:str,metrics:dict[str,Any],actor:str):
        if scenario not in EXTERNAL_SCENARIOS: raise ValueError("unsupported external resilience scenario")
        if environment.lower() in {"local","development","dev"}: raise ValueError("external evidence requires a deployed non-local environment")
        status=status.upper()
        if status not in {"PASS","FAIL"}: raise ValueError("status must be PASS or FAIL")
        now=utcnow(); return self._record(tenant_id,scenario,environment,now,now,status,metrics,actor,True)
    def _record(self,tenant_id,scenario,environment,start,end,status,metrics,actor,external):
        rid=gen_id("resilience"); payload={"scenario":scenario,"environment":environment,"status":status,"metrics":metrics,"started_at":start,"completed_at":end,"external":external}; eh=canonical_hash(payload)
        with self.store.connect() as db: db.execute("INSERT INTO resilience_runs(resilience_run_id,tenant_id,scenario,environment,started_at,completed_at,status,metrics_json,evidence_hash,actor,external) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(rid,tenant_id,scenario,environment,start,end,status,json.dumps(metrics,sort_keys=True),eh,actor,1 if external else 0))
        self.store._audit(actor,"resilience.run.recorded","resilience_run",rid,{"tenant_id":tenant_id,"scenario":scenario,"status":status,"external":external,"evidence_hash":eh})
        return {"resilience_run_id":rid,**payload,"evidence_hash":eh}
    def list_runs(self,tenant_id:str,limit:int=100):
        with self.store.connect() as db: rows=db.execute("SELECT * FROM resilience_runs WHERE tenant_id=? ORDER BY completed_at DESC LIMIT ?",(tenant_id,min(limit,500))).fetchall()
        out=[]
        for r in rows:
            d=dict(r); d["metrics"]=json.loads(d.pop("metrics_json")); d["external"]=bool(d["external"]); out.append(d)
        return out
    def posture(self,tenant_id:str="local"):
        runs=self.list_runs(tenant_id,500); passed_external={r["scenario"] for r in runs if r["external"] and r["status"]=="PASS"}
        return {"version":VERSION,"local_scenarios":sorted(LOCAL_SCENARIOS),"external_scenarios":sorted(EXTERNAL_SCENARIOS),"external_passed":sorted(passed_external),"production_resilience_proven":EXTERNAL_SCENARIOS.issubset(passed_external),"run_count":len(runs),"boundary":"Local resilience scenarios validate mechanics; production claims require deployed-environment evidence."}
    def self_test(self,tenant_id="local",actor="system:v0.23-self-test"):
        a=self.run_local(tenant_id,"compiler_stress",actor,5); b=self.run_local(tenant_id,"duplicate_write_guard",actor,5); c=self.run_local(tenant_id,"audit_integrity",actor,3)
        return {"ok":all(x["status"]=="PASS" for x in [a,b,c]),"runs":[a,b,c],"production_resilience_proven":False,"settlement_authority":False}

_SERVICE=None
def get_service(store):
    global _SERVICE
    if _SERVICE is None or _SERVICE.store is not store:_SERVICE=ResilienceLabService(store)
    return _SERVICE
