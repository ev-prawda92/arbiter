"""Governed policy version workflow for v0.12.

The active policy remains the engine input in policy.json for backwards compatibility,
but changes can now be staged and approved before activation.
"""
from __future__ import annotations
import json
from . import policy
from .resolution_infra import canonical_hash, gen_id, utcnow

class GovernedPolicyService:
    def __init__(self, store):
        self.store=store; self._init_db()
    def _init_db(self):
        with self.store.connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS policy_drafts (
              draft_id TEXT PRIMARY KEY,
              base_version TEXT NOT NULL,
              proposed_json TEXT NOT NULL,
              proposed_hash TEXT NOT NULL,
              status TEXT NOT NULL,
              created_by TEXT NOT NULL,
              created_at TEXT NOT NULL,
              note TEXT NOT NULL DEFAULT '',
              submitted_at TEXT,
              approved_by TEXT,
              approved_at TEXT,
              activated_at TEXT
            );
            CREATE INDEX IF NOT EXISTS ix_policy_drafts_status ON policy_drafts(status, created_at DESC);
            ''')
    def _decode(self,row):
        if not row:return None
        d=dict(row); d['proposed']=json.loads(d.pop('proposed_json')); return d
    def create_draft(self, *, weights=None, thresholds=None, actor='exchange.policy-admin', note=''):
        base=policy.load_policy(); proposed={"weights":dict(base['weights']),"thresholds":dict(base['thresholds'])}
        if weights: proposed['weights'].update(weights)
        if thresholds: proposed['thresholds'].update(thresholds)
        self._validate(proposed)
        did=gen_id('pol'); now=utcnow(); ph=canonical_hash(proposed)
        with self.store.connect() as db:
            db.execute('INSERT INTO policy_drafts(draft_id,base_version,proposed_json,proposed_hash,status,created_by,created_at,note) VALUES(?,?,?,?,?,?,?,?)',
                       (did,base['version'],json.dumps(proposed,sort_keys=True),ph,'draft',actor,now,note))
        self.store._audit(actor,'policy.draft.created','policy',did,{"base_version":base['version'],"proposed_hash":ph,"note":note})
        return self.get(did)
    def _validate(self,p):
        w=p['weights']; t=p['thresholds']
        if set(w)!={'source','timing','definition'}: raise ValueError('weights must contain source, timing, definition')
        if abs(sum(float(v) for v in w.values())-1.0)>0.0001: raise ValueError('policy weights must sum to 1.0')
        if any(float(v)<0 or float(v)>1 for v in w.values()): raise ValueError('policy weights must be between 0 and 1')
        if float(t.get('clean',-1))<0 or float(t.get('monitored',-1))<0: raise ValueError('thresholds must be non-negative')
        if float(t['clean'])>float(t['monitored']): raise ValueError('clean threshold cannot exceed monitored threshold')
    def get(self,did):
        with self.store.connect() as db: row=db.execute('SELECT * FROM policy_drafts WHERE draft_id=?',(did,)).fetchone()
        return self._decode(row)
    def list(self,status=None,limit=100):
        sql='SELECT * FROM policy_drafts'; args=[]
        if status: sql+=' WHERE status=?'; args.append(status)
        sql+=' ORDER BY created_at DESC LIMIT ?'; args.append(limit)
        with self.store.connect() as db: rows=db.execute(sql,args).fetchall()
        return [self._decode(r) for r in rows]
    def submit(self,did,actor):
        d=self.get(did)
        if not d: raise ValueError('policy draft not found')
        if d['status']!='draft': raise ValueError('only draft policy can be submitted')
        with self.store.connect() as db: db.execute('UPDATE policy_drafts SET status=?,submitted_at=? WHERE draft_id=?',('pending_approval',utcnow(),did))
        self.store._audit(actor,'policy.draft.submitted','policy',did,{"base_version":d['base_version']})
        return self.get(did)
    def approve(self,did,actor):
        d=self.get(did)
        if not d: raise ValueError('policy draft not found')
        if d['status']!='pending_approval': raise ValueError('policy draft is not pending approval')
        if actor==d['created_by']: raise ValueError('maker-checker violation: draft creator cannot approve own policy')
        with self.store.connect() as db: db.execute('UPDATE policy_drafts SET status=?,approved_by=?,approved_at=? WHERE draft_id=?',('approved',actor,utcnow(),did))
        self.store._audit(actor,'policy.draft.approved','policy',did,{"proposed_hash":d['proposed_hash']})
        return self.get(did)
    def activate(self,did,actor):
        d=self.get(did)
        if not d: raise ValueError('policy draft not found')
        if d['status']!='approved': raise ValueError('only approved policy draft may be activated')
        current=policy.load_policy()
        if current['version']!=d['base_version']: raise ValueError('stale policy draft: active base version changed')
        out=policy.update_policy(d['proposed']['weights'],d['proposed']['thresholds'],actor,d['note'] or f'Activated governed policy draft {did}')
        with self.store.connect() as db: db.execute('UPDATE policy_drafts SET status=?,activated_at=? WHERE draft_id=?',('active',utcnow(),did))
        self.store._audit(actor,'policy.version.activated','policy',did,{"new_version":out['version'],"proposed_hash":d['proposed_hash']})
        return {"draft":self.get(did),"active_policy":out}

_SERVICE=None
def get_service(store):
    global _SERVICE
    if _SERVICE is None or _SERVICE.store.path!=store.path:_SERVICE=GovernedPolicyService(store)
    return _SERVICE
