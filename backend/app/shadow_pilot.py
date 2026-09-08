"""Arbiter v0.25 design-partner shadow pilot harness.

Runs Arbiter against real venue contracts without changing venue settlement. It captures
semantic/compiler posture and, when supplied after resolution, compares Arbiter's
shadow outcome with the venue outcome.
"""
from __future__ import annotations
import json
from typing import Any
from .resolution_infra import gen_id, utcnow, canonical_hash
from . import semantic_contract, compiler

VERSION="0.25.0"

class ShadowPilotService:
    def __init__(self,store):self.store=store;self._init_db()
    def _init_db(self):
        with self.store.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS shadow_pilots(
              pilot_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, venue TEXT NOT NULL, name TEXT NOT NULL,
              status TEXT NOT NULL, created_at TEXT NOT NULL, created_by TEXT NOT NULL,
              contract_target INTEGER NOT NULL, metadata_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS shadow_contracts(
              shadow_contract_id TEXT PRIMARY KEY, pilot_id TEXT NOT NULL, tenant_id TEXT NOT NULL,
              venue_contract_id TEXT NOT NULL, title TEXT NOT NULL, rules TEXT NOT NULL,
              semantic_status TEXT NOT NULL, compiler_status TEXT NOT NULL,
              semantic_hash TEXT NOT NULL, compilation_hash TEXT NOT NULL,
              venue_outcome TEXT, arbiter_outcome TEXT, agreement INTEGER,
              evidence_json TEXT NOT NULL, created_at TEXT NOT NULL, resolved_at TEXT,
              UNIQUE(pilot_id, venue_contract_id)
            );
            """)
    def create_pilot(self,tenant_id,venue,name,contract_target,actor,metadata=None):
        if not venue.strip() or not name.strip():raise ValueError("venue and pilot name are required")
        pid=gen_id("pilot");now=utcnow();target=max(1,min(int(contract_target),10000));meta=metadata or {}
        with self.store.connect() as db:db.execute("INSERT INTO shadow_pilots(pilot_id,tenant_id,venue,name,status,created_at,created_by,contract_target,metadata_json) VALUES(?,?,?,?,?,?,?,?,?)",(pid,tenant_id,venue,name,"ACTIVE",now,actor,target,json.dumps(meta,sort_keys=True)))
        self.store._audit(actor,"shadow_pilot.created","shadow_pilot",pid,{"tenant_id":tenant_id,"venue":venue,"contract_target":target,"mode":"shadow","settlement_authority":False})
        return self.get_pilot(tenant_id,pid)
    def add_contract(self,tenant_id,pilot_id,venue_contract_id,title,rules,actor):
        self.get_pilot(tenant_id,pilot_id);sem=semantic_contract.analyze_contract(title,rules);comp=compiler.compile_rules("shadow_"+venue_contract_id,title,rules,self.store.list_authorities(),metadata={"pilot_id":pilot_id,"venue_contract_id":venue_contract_id,"shadow_mode":True});sid=gen_id("shadow");now=utcnow();sh=sem.get("semantic_hash") or canonical_hash(sem);ch=canonical_hash(comp)
        with self.store.connect() as db:
            try:db.execute("INSERT INTO shadow_contracts(shadow_contract_id,pilot_id,tenant_id,venue_contract_id,title,rules,semantic_status,compiler_status,semantic_hash,compilation_hash,evidence_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",(sid,pilot_id,tenant_id,venue_contract_id,title,rules,str(sem.get("status")),str(comp.get("status")),sh,ch,"{}",now))
            except Exception as e:raise ValueError("duplicate or invalid venue contract") from e
        self.store._audit(actor,"shadow_contract.analyzed","shadow_contract",sid,{"pilot_id":pilot_id,"venue_contract_id":venue_contract_id,"semantic_status":sem.get("status"),"compiler_status":comp.get("status"),"settlement_authority":False})
        return self.get_contract(tenant_id,sid)
    def record_resolution(self,tenant_id,shadow_contract_id,venue_outcome,arbiter_outcome,evidence,actor):
        venue_outcome=venue_outcome.upper();arbiter_outcome=arbiter_outcome.upper()
        if venue_outcome not in {"YES","NO","INVALID"} or arbiter_outcome not in {"YES","NO","HELD","INVALID"}:raise ValueError("unsupported outcome")
        agreement=1 if venue_outcome==arbiter_outcome else 0;now=utcnow()
        with self.store.connect() as db:
            row=db.execute("SELECT * FROM shadow_contracts WHERE tenant_id=? AND shadow_contract_id=?",(tenant_id,shadow_contract_id)).fetchone()
            if not row:raise KeyError("unknown shadow contract")
            db.execute("UPDATE shadow_contracts SET venue_outcome=?,arbiter_outcome=?,agreement=?,evidence_json=?,resolved_at=? WHERE shadow_contract_id=?",(venue_outcome,arbiter_outcome,agreement,json.dumps(evidence or {},sort_keys=True),now,shadow_contract_id))
        self.store._audit(actor,"shadow_contract.reconciled","shadow_contract",shadow_contract_id,{"venue_outcome":venue_outcome,"arbiter_outcome":arbiter_outcome,"agreement":bool(agreement),"settlement_authority":False})
        return self.get_contract(tenant_id,shadow_contract_id)
    def get_contract(self,tenant_id,sid):
        with self.store.connect() as db:r=db.execute("SELECT * FROM shadow_contracts WHERE tenant_id=? AND shadow_contract_id=?",(tenant_id,sid)).fetchone()
        if not r:raise KeyError("unknown shadow contract")
        d=dict(r);d["evidence"]=json.loads(d.pop("evidence_json"));d["agreement"]=None if d["agreement"] is None else bool(d["agreement"]);return d
    def get_pilot(self,tenant_id,pid):
        with self.store.connect() as db:
            p=db.execute("SELECT * FROM shadow_pilots WHERE tenant_id=? AND pilot_id=?",(tenant_id,pid)).fetchone()
            if not p:raise KeyError("unknown shadow pilot")
            rows=db.execute("SELECT * FROM shadow_contracts WHERE tenant_id=? AND pilot_id=? ORDER BY created_at",(tenant_id,pid)).fetchall()
        d=dict(p);d["metadata"]=json.loads(d.pop("metadata_json"));contracts=[]
        for r in rows:
            x=dict(r);x["evidence"]=json.loads(x.pop("evidence_json"));x["agreement"]=None if x["agreement"] is None else bool(x["agreement"]);contracts.append(x)
        d["contracts"]=contracts;d["metrics"]=self.metrics_from(contracts);d["mode"]="shadow";d["settlement_authority"]=False;return d
    def metrics_from(self,contracts):
        n=len(contracts);resolved=[c for c in contracts if c.get("resolved_at")];agreements=[c for c in resolved if c.get("agreement") is not None]
        count=lambda s:sum(1 for c in contracts if c.get("compiler_status")==s)
        return {"contracts":n,"ready":count("READY"),"review":count("REVIEW"),"block":count("BLOCK"),"resolved":len(resolved),"agreement_count":sum(1 for c in agreements if c["agreement"]),"disagreement_count":sum(1 for c in agreements if not c["agreement"]),"agreement_rate":round(sum(1 for c in agreements if c["agreement"])/len(agreements),4) if agreements else None}
    def posture(self,tenant_id="local"):
        with self.store.connect() as db:pilots=int(db.execute("SELECT COUNT(*) n FROM shadow_pilots WHERE tenant_id=?",(tenant_id,)).fetchone()["n"]);contracts=int(db.execute("SELECT COUNT(*) n FROM shadow_contracts WHERE tenant_id=?",(tenant_id,)).fetchone()["n"])
        return {"version":VERSION,"mode":"shadow-only","pilots":pilots,"contracts":contracts,"venue_settlement_mutation":False,"settlement_authority":False,"boundary":"A shadow pilot observes and compares; it never changes the venue's official resolution or settlement."}
    def self_test(self,tenant_id="local",actor="system:v0.25-self-test"):
        p=self.create_pilot(tenant_id,"synthetic-venue","Self-test pilot",3,actor,{"synthetic":True});c=self.add_contract(tenant_id,p["pilot_id"],"SYN-1","Will U.S. CPI be above 3.0% on September 11, 2026?","This market resolves YES if the U.S. Bureau of Labor Statistics reports CPI above 3.0% on September 11, 2026 at 08:30 EDT. The first published release controls.",actor);r=self.record_resolution(tenant_id,c["shadow_contract_id"],"YES","YES",{"synthetic":True},actor);after=self.get_pilot(tenant_id,p["pilot_id"])
        return {"ok":after["metrics"]["contracts"]==1 and r["agreement"] is True,"pilot":after,"settlement_authority":False}

_SERVICE=None
def get_service(store):
    global _SERVICE
    if _SERVICE is None or _SERVICE.store is not store:_SERVICE=ShadowPilotService(store)
    return _SERVICE
