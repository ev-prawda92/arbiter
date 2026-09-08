"""Arbiter v0.21 settlement assurance and validation harness.

This module turns assurance requirements into executable, hash-pinned evidence.
It does not claim independent certification. External security review, penetration
testing, production DR/load evidence, and an untouched real-contract holdout remain
required before production settlement certification.
"""
from __future__ import annotations
import json
from typing import Any
from .resolution_infra import gen_id, utcnow, canonical_hash
from . import compiler, semantic_contract

ADVERSARIAL_CASES=[
 {"id":"ready-cpi","title":"Will U.S. CPI be above 3.0% on September 11, 2026?","rules":"This market resolves YES if the U.S. Bureau of Labor Statistics reports CPI above 3.0% on September 11, 2026 at 08:30 EDT. The first published release controls.","expected":"READY"},
 {"id":"review-fed-cutoff","title":"Will the Federal Reserve cut interest rates by the end of September 2026?","rules":"This market resolves YES if the Federal Reserve announces an interest rate cut by the end of September 2026, based on official Federal Reserve reporting.","expected":"REVIEW"},
 {"id":"block-title-rules-mismatch","title":"Will U.S. CPI be above 3.0% on September 11, 2026?","rules":"This market resolves YES if the federal government is in a shutdown due to a lapse in appropriations as of January 31, 2026, based on the Office of Personnel Management operating status.","expected":"BLOCK"},
 {"id":"block-vague-inflation","title":"Will inflation exceed 3%?","rules":"Resolve YES if inflation is above 3%.","expected":"BLOCK"},
 {"id":"review-weather-location","title":"Will Pittsburgh exceed 80°F?","rules":"Resolve YES if NOAA reports the daily maximum temperature in Pittsburgh above 80°F on September 8, 2026.","expected":"REVIEW"},
]

class SettlementAssuranceService:
    def __init__(self,store): self.store=store; self._init_db()
    def _init_db(self):
        with self.store.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS assurance_runs(
              assurance_run_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, suite_name TEXT NOT NULL,
              started_at TEXT NOT NULL, completed_at TEXT NOT NULL, status TEXT NOT NULL,
              report_json TEXT NOT NULL, report_hash TEXT NOT NULL, actor TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS holdout_datasets(
              dataset_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, name TEXT NOT NULL,
              created_at TEXT NOT NULL, created_by TEXT NOT NULL, case_count INTEGER NOT NULL,
              dataset_hash TEXT NOT NULL, cases_json TEXT NOT NULL, frozen INTEGER NOT NULL DEFAULT 1
            );
            """)
    def requirements(self):
        return {
          "internal_release_gates":{"required":True,"status":"implemented"},
          "adversarial_contract_suite":{"required":True,"status":"implemented"},
          "untouched_real_contract_holdout":{"required":True,"status":"not_yet_externally_supplied"},
          "external_security_architecture_review":{"required":True,"status":"not_yet_completed"},
          "penetration_test":{"required":True,"status":"not_yet_completed"},
          "production_load_and_concurrency_test":{"required":True,"status":"requires_deployed_environment"},
          "production_backup_restore_drill":{"required":True,"status":"requires_deployed_environment"},
          "multi_zone_failover_drill":{"required":True,"status":"requires_deployed_environment"},
          "incident_response_exercise":{"required":True,"status":"requires_production_team"},
        }
    def posture(self):
        req=self.requirements(); blockers=[k for k,v in req.items() if v['required'] and v['status'] not in {'implemented','completed','passed'}]
        with self.store.connect() as db:
            runs=int(db.execute('SELECT COUNT(*) n FROM assurance_runs').fetchone()['n']); datasets=int(db.execute('SELECT COUNT(*) n FROM holdout_datasets').fetchone()['n'])
        return {"version":"0.21.0","internal_assurance_harness":True,"production_settlement_certified":False,"certification_state":"NOT_CERTIFIED","requirements":req,"open_certification_blockers":blockers,"assurance_runs":runs,"holdout_datasets":datasets,"principle":"internal evidence is not independent certification"}
    def run_adversarial_suite(self,tenant_id:str,actor:str):
        start=utcnow(); results=[]; authorities=self.store.list_authorities()
        for c in ADVERSARIAL_CASES:
            sem=semantic_contract.analyze_contract(c['title'],c['rules']); comp=compiler.compile_rules('assure_'+c['id'],c['title'],c['rules'],authorities,metadata={'assurance_case_id':c['id']}); actual=str(comp.get('status') or 'UNKNOWN')
            results.append({"case_id":c['id'],"expected":c['expected'],"actual":actual,"pass":actual==c['expected'],"semantic_status":sem.get('status'),"semantic_hash":sem.get('semantic_hash'),"compilation_hash":canonical_hash(comp)})
        passed=sum(1 for r in results if r['pass']); end=utcnow(); report={"suite":"ARB-ADVERSARIAL-v0.21","case_count":len(results),"passed":passed,"failed":len(results)-passed,"results":results,"started_at":start,"completed_at":end,"production_certification":False}; rh=canonical_hash(report); rid=gen_id('assure')
        status='PASS' if passed==len(results) else 'FAIL'
        with self.store.connect() as db: db.execute("INSERT INTO assurance_runs(assurance_run_id,tenant_id,suite_name,started_at,completed_at,status,report_json,report_hash,actor) VALUES(?,?,?,?,?,?,?,?,?)",(rid,tenant_id,report['suite'],start,end,status,json.dumps(report,sort_keys=True),rh,actor))
        self.store._audit(actor,'assurance.run.completed','assurance_run',rid,{"tenant_id":tenant_id,"suite":report['suite'],"status":status,"report_hash":rh,"independent_certification":False})
        return {"assurance_run_id":rid,"status":status,"report":report,"report_hash":rh,"independent_certification":False}
    def create_holdout(self,tenant_id:str,name:str,cases:list[dict[str,Any]],actor:str):
        if not cases: raise ValueError('holdout cases are required')
        canonical=[]
        for i,c in enumerate(cases):
            if not c.get('title') or not c.get('rules'): raise ValueError(f'case {i} requires title and rules')
            canonical.append({"case_id":str(c.get('case_id') or f'case-{i+1}'),"title":str(c['title']),"rules":str(c['rules']),"known_outcome":c.get('known_outcome'),"source_provenance":c.get('source_provenance'),"label_frozen":bool(c.get('label_frozen',False))})
        did=gen_id('holdout'); now=utcnow(); dh=canonical_hash({"name":name,"cases":canonical})
        with self.store.connect() as db: db.execute("INSERT INTO holdout_datasets(dataset_id,tenant_id,name,created_at,created_by,case_count,dataset_hash,cases_json,frozen) VALUES(?,?,?,?,?,?,?,?,1)",(did,tenant_id,name,now,actor,len(canonical),dh,json.dumps(canonical,sort_keys=True)))
        self.store._audit(actor,'holdout.dataset.frozen','holdout_dataset',did,{"tenant_id":tenant_id,"name":name,"case_count":len(canonical),"dataset_hash":dh})
        return {"dataset_id":did,"name":name,"case_count":len(canonical),"dataset_hash":dh,"frozen":True,"created_at":now}
    def list_holdouts(self,tenant_id:str):
        with self.store.connect() as db: rows=db.execute("SELECT dataset_id,name,created_at,created_by,case_count,dataset_hash,frozen FROM holdout_datasets WHERE tenant_id=? ORDER BY created_at DESC",(tenant_id,)).fetchall()
        return [dict(r) for r in rows]
    def evaluate_holdout(self,tenant_id:str,dataset_id:str,actor:str):
        with self.store.connect() as db: row=db.execute("SELECT * FROM holdout_datasets WHERE dataset_id=? AND tenant_id=?",(dataset_id,tenant_id)).fetchone()
        if not row: raise KeyError('unknown holdout dataset')
        cases=json.loads(row['cases_json']); authorities=self.store.list_authorities(); results=[]
        for c in cases:
            comp=compiler.compile_rules('holdout_'+c['case_id'],c['title'],c['rules'],authorities,metadata={'holdout_dataset_id':dataset_id}); results.append({"case_id":c['case_id'],"compiler_status":comp.get('status'),"compilation_hash":canonical_hash(comp),"known_outcome":c.get('known_outcome'),"label_frozen":c.get('label_frozen'),"source_provenance":c.get('source_provenance')})
        report={"dataset_id":dataset_id,"dataset_hash":row['dataset_hash'],"case_count":len(results),"results":results,"note":"Compiler evaluation only; known outcome comparison requires evidence-backed resolution labels.","production_certification":False}; rh=canonical_hash(report)
        self.store._audit(actor,'holdout.dataset.evaluated','holdout_dataset',dataset_id,{"report_hash":rh,"case_count":len(results)})
        return {"report":report,"report_hash":rh,"independent_certification":False}
    def self_test(self,tenant_id='local',actor='system:v0.21-self-test'):
        adv=self.run_adversarial_suite(tenant_id,actor)
        h=self.create_holdout(tenant_id,'Synthetic self-test holdout',[{"case_id":"h1","title":ADVERSARIAL_CASES[0]['title'],"rules":ADVERSARIAL_CASES[0]['rules'],"known_outcome":None,"source_provenance":"synthetic:self-test","label_frozen":True}],actor)
        ev=self.evaluate_holdout(tenant_id,h['dataset_id'],actor)
        return {"ok":adv['status']=='PASS' and h['frozen'] and bool(ev['report_hash']),"adversarial":adv,"holdout":h,"holdout_evaluation":ev,"production_settlement_certified":False}

_SERVICE=None
def get_service(store):
    global _SERVICE
    if _SERVICE is None or _SERVICE.store is not store:_SERVICE=SettlementAssuranceService(store)
    return _SERVICE
