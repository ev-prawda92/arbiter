#!/usr/bin/env python3
"""Arbiter v0.11 Active Evidence API regression gate.

Requires a running local Arbiter API. Creates uniquely named test authorities,
contracts, monitors, evidence, exceptions, and reevaluation requests.
"""
from __future__ import annotations
import argparse, json, os, time, urllib.request, urllib.error, uuid


def request(base, path, method='GET', body=None, key=None):
    headers={'Accept':'application/json'}
    if key: headers['X-Arbiter-Key']=key
    data=None
    if body is not None:
        data=json.dumps(body).encode(); headers['Content-Type']='application/json'
    req=urllib.request.Request(base.rstrip('/')+path,data=data,headers=headers,method=method)
    try:
        with urllib.request.urlopen(req,timeout=15) as r:
            raw=r.read(); payload=json.loads(raw.decode()) if raw else {}
            return r.status,payload
    except urllib.error.HTTPError as e:
        raw=e.read()
        try: payload=json.loads(raw.decode())
        except Exception: payload=raw.decode(errors='replace')
        return e.code,payload


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--base-url',default='http://127.0.0.1:8000'); ap.add_argument('--api-key',default=os.environ.get('ARBITER_API_KEY'))
    a=ap.parse_args(); passed=failed=0
    def check(label, cond, detail=''):
        nonlocal passed,failed
        if cond: passed+=1; print('[PASS]',label)
        else: failed+=1; print('[FAIL]',label,('— '+detail if detail else ''))
    def post(path, body): return request(a.base_url,path,'POST',body,a.api_key)
    def get(path): return request(a.base_url,path,'GET',None,a.api_key)

    suffix=uuid.uuid4().hex[:8]
    auth1=f'AUTH-V011-A-{suffix}'; auth2=f'AUTH-V011-B-{suffix}'; contract=f'V011-EVID-{suffix}'

    st,h=get('/api/health'); check('API reachable and v0.11+', st==200 and tuple(int(x) for x in str(h.get('version','0.0')).split('.')[:2]) >= (0,11), f'{st} {h}')

    for aid,name in [(auth1,'Evidence Gate Primary'),(auth2,'Evidence Gate Secondary')]:
        st,out=post('/api/authorities',{
            'authority_id':aid,'version':1,'name':name,'organization':'Arbiter Test Authority','source_type':'test_fixture',
            'endpoint':f'https://example.invalid/{aid}','status':'approved','actor':'test:evidence-gate'
        })
        check(f'authority created: {aid}', st==200 and out.get('authority',{}).get('authority_id')==aid, f'{st} {out}')

    st,out=post('/api/contracts',{
        'contract_id':contract,'contract_version':1,'title':'v0.11 evidence gate contract',
        'definition':{'type':'numeric_threshold','operator':'>','threshold':3.0},
        'timing':{'observation':'test-window','timezone':'UTC'},
        'authority_ids':[auth1,auth2],'source_precedence':[auth1,auth2],
        'revision_policy':{'policy':'latest_test_observation'},'approval_policy':{'auto_if_all_controls_pass':True},
        'metadata':{'test':True},'actor':'test:evidence-gate','status':'approved'
    })
    check('multi-authority governed contract created', st==200 and out.get('contract',{}).get('contract_id')==contract, f'{st} {out}')

    monitors=[]
    for aid,val in [(auth1,3.2),(auth2,3.2)]:
        st,out=post('/api/evidence-monitors',{
            'contract_id':contract,'authority_id':aid,'authority_version':1,'adapter_type':'static',
            'config':{'value':val,'raw':{'value':val,'release':'initial'}},'schedule_seconds':300,'enabled':True,'actor':'test:evidence-gate'
        })
        mid=(out.get('monitor') or {}).get('monitor_id'); monitors.append(mid)
        check(f'monitor created for {aid}', st==200 and bool(mid), f'{st} {out}')
    m1,m2=monitors

    st,out=post(f'/api/evidence-monitors/{m1}/poll',{})
    first_evidence=(out.get('evidence') or {}).get('evidence_id')
    first_reeval=out.get('reevaluation_request_id')
    check('first poll appends evidence', st==200 and out.get('status')=='appended' and bool(first_evidence), f'{st} {out}')
    check('first evidence change requests reevaluation', bool(first_reeval), str(out))

    st,out=post(f'/api/evidence-monitors/{m1}/poll',{})
    check('duplicate poll is idempotently ignored', st==200 and out.get('status')=='duplicate' and out.get('changed') is False, f'{st} {out}')
    check('duplicate does not request reevaluation', out.get('reevaluation_request_id') is None, str(out))

    st,out=post(f'/api/evidence-monitors/{m1}',{'config':{'value':3.4,'raw':{'value':3.4,'release':'revision-2'}},'actor':'test:evidence-gate'})
    check('monitor configuration can be governed-updated', st==200 and out.get('monitor',{}).get('config',{}).get('value')==3.4, f'{st} {out}')
    st,out=post(f'/api/evidence-monitors/{m1}/poll',{})
    revised=(out.get('evidence') or {})
    check('changed observation becomes append-only revision', st==200 and out.get('status')=='revision' and revised.get('revision_number')==2 and revised.get('supersedes')==first_evidence, f'{st} {out}')
    check('revision requests fresh reevaluation', bool(out.get('reevaluation_request_id')), str(out))

    # Secondary source observes a conflicting governed value.
    st,out=post(f'/api/evidence-monitors/{m2}/observe',{
        'normalized_value':2.8,'raw_payload':{'value':2.8,'release':'conflict'},'source_locator':'static://secondary',
        'parser_version':'active-evidence.v1','actor':'test:evidence-gate'
    })
    conflict_exception=out.get('exception_id')
    check('cross-authority conflict detected', st==200 and out.get('status')=='conflict' and out.get('conflict') is True, f'{st} {out}')
    check('conflict creates operational exception', bool(conflict_exception), str(out))

    st,ex=get('/api/evidence-exceptions?active_only=true')
    exceptions=ex.get('exceptions',[]) if st==200 else []
    check('exception registry exposes conflict', any(x.get('exception_id')==conflict_exception and x.get('severity')=='critical' for x in exceptions), str(ex))

    st,q=get('/api/work-queue')
    items=q.get('items',[]) if st==200 else []
    check('conflict automatically appears in Work Queue', any(x.get('kind')=='evidence_conflict' and x.get('subject')==contract for x in items), str(q)[:1000])

    # Simulate a source outage to validate fail-closed health/backoff behavior.
    st,out=post(f'/api/evidence-monitors/{m2}',{'config':{'simulate_error':'test source unavailable'},'actor':'test:evidence-gate'})
    st,out=post(f'/api/evidence-monitors/{m2}/poll',{})
    outage_exception=out.get('exception_id')
    check('source outage detected without crashing API', st==200 and out.get('status')=='outage' and out.get('consecutive_failures')==1, f'{st} {out}')
    check('outage schedules retry/backoff', bool(out.get('next_poll_at')), str(out))
    check('outage creates operational exception', bool(outage_exception), str(out))

    st,health=get('/api/source-health')
    check('source health reports unhealthy state', st==200 and health.get('healthy') is False and health.get('states',{}).get('outage',0)>=1, f'{st} {health}')

    st,re=get('/api/resolution-reevaluations?status=pending')
    reqs=re.get('requests',[]) if st==200 else []
    contract_reqs=[r for r in reqs if r.get('contract_id')==contract]
    check('changed governed evidence creates durable reevaluation requests', len(contract_reqs)>=3, str(contract_reqs))

    st,ev=get(f'/api/evidence?contract_id={contract}&limit=100')
    records=ev.get('evidence',[]) if st==200 else []
    check('evidence ledger is append-only and queryable', len(records)>=3, str(records))
    hashes=[r.get('record_hash') for r in records]
    check('captured evidence retains provenance hashes', all(h and str(h).startswith('sha256:') for h in hashes), str(hashes))

    st,infra=get('/api/infrastructure')
    ae=infra.get('active_evidence',{}) if st==200 else {}
    check('infrastructure summary includes active evidence layer', st==200 and ae.get('monitors',0)>=2 and 'source_health' in ae, f'{st} {infra}')

    st,audit=get('/api/audit?limit=500')
    events=audit.get('events',[]) if st==200 else []
    actions={e.get('action') for e in events}
    check('active evidence activity is audited', {'evidence.monitor.created','evidence.appended','resolution.reevaluation.requested'}.issubset(actions), str(sorted(actions))[:1000])
    check('audit chain remains valid after evidence operations', st==200 and audit.get('chain',{}).get('ok') is True, str(audit.get('chain')))

    total=passed+failed
    print('\n'+'='*64); print(f'RESULT: {passed}/{total} checks passed; {failed} failed'); print('ACTIVE EVIDENCE GATE:', 'PASS' if failed==0 else 'FAIL')
    return 0 if failed==0 else 1

if __name__=='__main__': raise SystemExit(main())
