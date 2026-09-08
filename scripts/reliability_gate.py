#!/usr/bin/env python3
"""Arbiter v0.15 production reliability gate against a running local API."""
from __future__ import annotations
import argparse, json, urllib.request, urllib.error, uuid


def request(base,path,method='GET',body=None,key=None):
    headers={'Accept':'application/json'}
    if key: headers['X-Arbiter-Key']=key
    data=None
    if body is not None:
        data=json.dumps(body).encode(); headers['Content-Type']='application/json'
    req=urllib.request.Request(base.rstrip('/')+path,data=data,headers=headers,method=method)
    try:
        with urllib.request.urlopen(req,timeout=10) as r:
            raw=r.read(); return r.status,(json.loads(raw.decode()) if raw else {}),dict(r.headers)
    except urllib.error.HTTPError as e:
        raw=e.read()
        try: payload=json.loads(raw.decode())
        except Exception: payload=raw.decode(errors='replace')
        return e.code,payload,dict(e.headers)


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--base-url',default='http://127.0.0.1:8000'); ap.add_argument('--api-key',default=None)
    a=ap.parse_args(); passed=failed=0
    def check(label,cond,detail=''):
        nonlocal passed,failed
        if cond: passed+=1; print('[PASS]',label)
        else: failed+=1; print('[FAIL]',label,('— '+detail if detail else ''))

    st,h,_=request(a.base_url,'/api/health',key=a.api_key)
    try: ver=tuple(int(x) for x in str(h.get('version','0.0')).split('.')[:2])
    except Exception: ver=(0,0)
    check('API reachable and v0.15+',st==200 and ver>=(0,15),f'{st} {h}')

    st,p,_=request(a.base_url,'/api/reliability',key=a.api_key)
    check('reliability posture loads',st==200,f'{st} {p}')
    check('reliability schema migration recorded',any(m.get('migration_id')=='v0.15-reliability' for m in p.get('migrations',[])),str(p))
    check('local reliability configuration passes',p.get('configuration_gate')=='PASS',str(p))

    suffix=uuid.uuid4().hex[:8]
    # Idempotency
    idem={'key':'idem-'+suffix,'scope':'gate:create','request':{'x':1},'response':{'ok':True},'status_code':201,'ttl_seconds':600}
    st,i1,_=request(a.base_url,'/api/idempotency','POST',idem,a.api_key)
    check('idempotency record can be created',st==200 and i1.get('replayed') is False,f'{st} {i1}')
    st,i2,_=request(a.base_url,'/api/idempotency','POST',idem,a.api_key)
    check('same idempotency request replays deterministically',st==200 and i2.get('replayed') is True and i2.get('response')=={'ok':True},f'{st} {i2}')
    bad=dict(idem); bad['request']={'x':2}
    st,i3,_=request(a.base_url,'/api/idempotency','POST',bad,a.api_key)
    check('idempotency key cannot be reused with different request',st==409,f'{st} {i3}')

    # Happy-path job
    st,j,_=request(a.base_url,'/api/jobs','POST',{'job_type':'resolution.reevaluate','payload':{'contract_id':'C-'+suffix},'tenant_id':'local','max_attempts':3,'actor':'test:reliability-gate'},a.api_key)
    job=j.get('job',{}); jid=job.get('job_id')
    check('durable job can be enqueued',st==200 and job.get('status')=='queued' and bool(jid),f'{st} {j}')
    st,c,_=request(a.base_url,'/api/jobs/claim','POST',{'worker_id':'worker:A','tenant_id':'local','lease_seconds':60},a.api_key)
    claimed=c.get('job') or {}
    check('worker can claim due job',st==200 and claimed.get('job_id')==jid and claimed.get('status')=='running',f'{st} {c}')
    check('claim increments attempt count',claimed.get('attempts')==1,str(claimed))
    st,w,_=request(a.base_url,f'/api/jobs/{jid}/complete','POST',{'worker_id':'worker:B','result':{}},a.api_key)
    check('wrong worker cannot complete leased job',st==403,f'{st} {w}')
    st,d,_=request(a.base_url,f'/api/jobs/{jid}/complete','POST',{'worker_id':'worker:A','result':{'outcome':'ok'}},a.api_key)
    check('lease owner can complete job',st==200 and d.get('job',{}).get('status')=='completed',f'{st} {d}')

    # Dead-letter path
    st,j2,_=request(a.base_url,'/api/jobs','POST',{'job_type':'webhook.deliver','payload':{'delivery':'x'},'tenant_id':'local','max_attempts':1,'actor':'test:reliability-gate'},a.api_key)
    jid2=j2.get('job',{}).get('job_id')
    check('terminal-test job enqueued',st==200 and bool(jid2),f'{st} {j2}')
    st,c2,_=request(a.base_url,'/api/jobs/claim','POST',{'worker_id':'worker:DLQ','tenant_id':'local','lease_seconds':60},a.api_key)
    check('terminal-test job claimed',st==200 and (c2.get('job') or {}).get('job_id')==jid2,f'{st} {c2}')
    st,f2,_=request(a.base_url,f'/api/jobs/{jid2}/fail','POST',{'worker_id':'worker:DLQ','error':'simulated permanent failure','retry_delay_seconds':1},a.api_key)
    check('max-attempt failure moves job to dead letter',st==200 and f2.get('job',{}).get('status')=='dead_letter',f'{st} {f2}')
    check('dead-letter retains failure reason','simulated permanent failure' in (f2.get('job',{}).get('last_error') or ''),str(f2))

    st,listing,_=request(a.base_url,'/api/jobs?tenant_id=local',key=a.api_key)
    jobs=listing.get('jobs',[])
    check('job registry is queryable',st==200 and any(x.get('job_id')==jid for x in jobs),str(listing)[:800])
    check('completed and dead-letter states persist',any(x.get('job_id')==jid and x.get('status')=='completed' for x in jobs) and any(x.get('job_id')==jid2 and x.get('status')=='dead_letter' for x in jobs),str(jobs)[:800])

    # Webhook signed envelope and replay protection
    st,wh,_=request(a.base_url,'/api/webhook-deliveries','POST',{'event_type':'resolution.completed','target_url':'http://localhost/test-hook','payload':{'run_id':'run-'+suffix,'outcome':'YES'},'tenant_id':'local','max_attempts':3,'actor':'test:reliability-gate'},a.api_key)
    delivery=wh.get('delivery',{})
    check('signed webhook envelope can be created',st==200 and str(delivery.get('signature','')).startswith('sha256=') and bool(delivery.get('nonce')),f'{st} {wh}')
    verify={'timestamp':delivery.get('timestamp'),'nonce':delivery.get('nonce'),'payload':delivery.get('payload'),'signature':delivery.get('signature'),'tolerance_seconds':300}
    st,v1,_=request(a.base_url,'/api/webhook-verify','POST',verify,a.api_key)
    check('valid webhook signature verifies',st==200 and v1.get('valid') is True,f'{st} {v1}')
    st,v2,_=request(a.base_url,'/api/webhook-verify','POST',verify,a.api_key)
    check('webhook replay is rejected',st==200 and v2.get('valid') is False and v2.get('reason')=='replay detected',f'{st} {v2}')
    badsig=dict(verify); badsig['nonce']='new-'+suffix; badsig['signature']='sha256:'+'0'*64
    st,v3,_=request(a.base_url,'/api/webhook-verify','POST',badsig,a.api_key)
    check('invalid webhook signature is rejected',st==200 and v3.get('valid') is False and v3.get('reason')=='signature mismatch',f'{st} {v3}')

    st,p2,_=request(a.base_url,'/api/reliability',key=a.api_key)
    check('reliability posture exposes dead letters',st==200 and p2.get('jobs',{}).get('dead_letter',0)>=1,str(p2))
    check('reliability posture counts completed work',p2.get('jobs',{}).get('completed',0)>=1,str(p2))

    st,audit,_=request(a.base_url,'/api/audit?limit=200',key=a.api_key)
    events=audit.get('events',[]) if isinstance(audit,dict) else []
    actions={e.get('action') for e in events}
    check('reliability operations are audited',st==200 and {'job.enqueued','job.claimed','job.completed','job.dead_lettered','webhook.queued'}.issubset(actions),str(actions))
    chain=audit.get('chain',{}) if isinstance(audit,dict) else {}
    check('audit chain remains valid after reliability operations',chain.get('ok') is True,str(chain))
    st,ready,_=request(a.base_url,'/api/readiness',key=a.api_key)
    check('readiness remains healthy after reliability operations',st==200 and ready.get('ready') is True,f'{st} {ready}')

    total=passed+failed
    print('\n'+'='*64); print(f'RESULT: {passed}/{total} checks passed; {failed} failed'); print('PRODUCTION RELIABILITY GATE:', 'PASS' if failed==0 else 'FAIL')
    return 0 if failed==0 else 1

if __name__=='__main__': raise SystemExit(main())
