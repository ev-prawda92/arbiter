"""Arbiter v0.20 production operations and resilience controls.

Provides bounded-load admission, dependency/readiness telemetry, incident state,
recovery drill records, and deterministic resilience self-tests. External APM,
HA infrastructure, and managed failover remain deployment responsibilities.
"""
from __future__ import annotations
import json, os, time
from collections import defaultdict, deque
from threading import Lock
from typing import Any
from .resolution_infra import gen_id, utcnow, canonical_hash

class SlidingWindowLimiter:
    def __init__(self): self._events=defaultdict(deque); self._lock=Lock()
    def admit(self,key:str,limit:int,window_seconds:int=60)->dict[str,Any]:
        now=time.monotonic(); cutoff=now-window_seconds
        with self._lock:
            q=self._events[key]
            while q and q[0] < cutoff: q.popleft()
            if len(q)>=limit:
                return {"admitted":False,"remaining":0,"retry_after_seconds":max(1,int(window_seconds-(now-q[0])))}
            q.append(now)
            return {"admitted":True,"remaining":max(0,limit-len(q)),"retry_after_seconds":0}

class OperationsService:
    def __init__(self,store): self.store=store; self.limiter=SlidingWindowLimiter(); self._init_db()
    def _init_db(self):
        with self.store.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS operations_incidents(
              incident_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, severity TEXT NOT NULL,
              title TEXT NOT NULL, status TEXT NOT NULL, opened_at TEXT NOT NULL, opened_by TEXT NOT NULL,
              closed_at TEXT, closed_by TEXT, details_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS recovery_drills(
              drill_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, drill_type TEXT NOT NULL,
              started_at TEXT NOT NULL, completed_at TEXT NOT NULL, result TEXT NOT NULL,
              details_json TEXT NOT NULL, result_hash TEXT NOT NULL, actor TEXT NOT NULL
            );
            """)
    def config(self):
        return {
          "api_rate_limit_per_minute":int(os.environ.get('ARBITER_RATE_LIMIT_PER_MINUTE','600')),
          "worker_backlog_warn":int(os.environ.get('ARBITER_WORKER_BACKLOG_WARN','1000')),
          "worker_backlog_block":int(os.environ.get('ARBITER_WORKER_BACKLOG_BLOCK','5000')),
          "dependency_stale_seconds":int(os.environ.get('ARBITER_DEPENDENCY_STALE_SECONDS','300')),
        }
    def dependency_status(self)->list[dict[str,Any]]:
        # Local checks are intentionally side-effect free; external probes belong in deployment monitoring.
        deps=[]
        try:
            with self.store.connect() as db: db.execute('SELECT 1').fetchone()
            deps.append({"name":"database","status":"healthy","required":True})
        except Exception as e: deps.append({"name":"database","status":"unhealthy","required":True,"error":type(e).__name__})
        audit=self.store.verify_audit_chain(); deps.append({"name":"audit_chain","status":"healthy" if audit.get('ok') else 'unhealthy',"required":True})
        return deps
    def posture(self)->dict[str,Any]:
        deps=self.dependency_status(); required_ok=all(d['status']=='healthy' for d in deps if d['required'])
        with self.store.connect() as db:
            open_inc=int(db.execute("SELECT COUNT(*) n FROM operations_incidents WHERE status!='closed'").fetchone()['n'])
            drills=int(db.execute("SELECT COUNT(*) n FROM recovery_drills").fetchone()['n'])
            try: backlog=int(db.execute("SELECT COUNT(*) n FROM durable_jobs WHERE status IN ('queued','leased','running')").fetchone()['n'])
            except Exception: backlog=0
        cfg=self.config(); pressure='BLOCK' if backlog>=cfg['worker_backlog_block'] else ('WARN' if backlog>=cfg['worker_backlog_warn'] else 'NORMAL')
        return {"version":"0.20.0","ready":required_ok and pressure!='BLOCK',"dependencies":deps,"backlog":backlog,"backpressure":pressure,"open_incidents":open_inc,"recovery_drills":drills,"rate_limiting":"sliding-window-admission","config":cfg,"external_observability_required_for_production":True}
    def admit(self,tenant_id:str,principal_id:str)->dict[str,Any]:
        return self.limiter.admit(f'{tenant_id}:{principal_id}',self.config()['api_rate_limit_per_minute'],60)
    def open_incident(self,tenant_id:str,severity:str,title:str,details:dict,actor:str):
        severity=severity.upper()
        if severity not in {'SEV1','SEV2','SEV3','SEV4'}: raise ValueError('severity must be SEV1..SEV4')
        iid=gen_id('inc'); now=utcnow()
        with self.store.connect() as db: db.execute("INSERT INTO operations_incidents(incident_id,tenant_id,severity,title,status,opened_at,opened_by,details_json) VALUES(?,?,?,?,?,?,?,?)",(iid,tenant_id,severity,title,'open',now,actor,json.dumps(details,sort_keys=True)))
        self.store._audit(actor,'incident.opened','incident',iid,{"tenant_id":tenant_id,"severity":severity,"title":title})
        return {"incident_id":iid,"severity":severity,"title":title,"status":"open","opened_at":now}
    def close_incident(self,tenant_id:str,incident_id:str,actor:str):
        now=utcnow()
        with self.store.connect() as db:
            row=db.execute("SELECT * FROM operations_incidents WHERE incident_id=? AND tenant_id=?",(incident_id,tenant_id)).fetchone()
            if not row: raise KeyError('unknown incident')
            db.execute("UPDATE operations_incidents SET status='closed',closed_at=?,closed_by=? WHERE incident_id=?",(now,actor,incident_id))
        self.store._audit(actor,'incident.closed','incident',incident_id,{"tenant_id":tenant_id})
        return {"incident_id":incident_id,"status":"closed","closed_at":now}
    def list_incidents(self,tenant_id:str):
        with self.store.connect() as db: rows=db.execute("SELECT * FROM operations_incidents WHERE tenant_id=? ORDER BY opened_at DESC",(tenant_id,)).fetchall()
        return [{**dict(r),"details":json.loads(r['details_json'])} for r in rows]
    def run_recovery_drill(self,tenant_id:str,drill_type:str,actor:str):
        if drill_type not in {'audit-replay','database-read','queue-recovery','backup-posture'}: raise ValueError('unsupported drill type')
        start=utcnow(); details={"drill_type":drill_type}
        if drill_type=='audit-replay': details['audit_chain']=self.store.verify_audit_chain(); ok=details['audit_chain'].get('ok') is True
        elif drill_type=='database-read':
            try:
                with self.store.connect() as db: v=db.execute('SELECT 1 AS ok').fetchone()['ok']
                details['database_read']=v; ok=v==1
            except Exception as e: details['error']=type(e).__name__; ok=False
        elif drill_type=='queue-recovery':
            try:
                with self.store.connect() as db: n=db.execute("SELECT COUNT(*) n FROM durable_jobs").fetchone()['n']
                details['jobs_visible']=int(n); ok=True
            except Exception as e: details['error']=type(e).__name__; ok=False
        else:
            from . import production_data
            details['backup_posture']=production_data.get_service(self.store).posture().get('backup_restore'); ok=bool(details['backup_posture'])
        end=utcnow(); result='PASS' if ok else 'FAIL'; payload={"tenant_id":tenant_id,"drill_type":drill_type,"started_at":start,"completed_at":end,"result":result,"details":details}; rh=canonical_hash(payload); did=gen_id('drill')
        with self.store.connect() as db: db.execute("INSERT INTO recovery_drills(drill_id,tenant_id,drill_type,started_at,completed_at,result,details_json,result_hash,actor) VALUES(?,?,?,?,?,?,?,?,?)",(did,tenant_id,drill_type,start,end,result,json.dumps(details,sort_keys=True),rh,actor))
        self.store._audit(actor,'recovery_drill.completed','recovery_drill',did,{"tenant_id":tenant_id,"drill_type":drill_type,"result":result,"result_hash":rh})
        return {"drill_id":did,**payload,"result_hash":rh,"settlement_authority":False}
    def self_test(self,tenant_id='local',actor='system:v0.20-self-test'):
        admission=self.admit(tenant_id,actor); d1=self.run_recovery_drill(tenant_id,'audit-replay',actor); d2=self.run_recovery_drill(tenant_id,'database-read',actor)
        inc=self.open_incident(tenant_id,'SEV4','Self-test incident',{'synthetic':True},actor); closed=self.close_incident(tenant_id,inc['incident_id'],actor)
        return {"ok":admission['admitted'] and d1['result']=='PASS' and d2['result']=='PASS' and closed['status']=='closed',"admission":admission,"drills":[d1,d2],"incident":closed,"settlement_authority":False}

_SERVICE=None
def get_service(store):
    global _SERVICE
    if _SERVICE is None or _SERVICE.store is not store: _SERVICE=OperationsService(store)
    return _SERVICE
