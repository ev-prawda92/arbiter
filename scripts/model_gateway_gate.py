#!/usr/bin/env python3
"""Arbiter v0.16 governed model intelligence gate.

No external model call is made. The gate exercises the internal self-test path so
release validation is deterministic, cost-free, and independent of provider uptime.
"""
from __future__ import annotations
import argparse, json, urllib.error, urllib.request


def request(base, path, method='GET', body=None, key=None):
    headers={'Accept':'application/json'}
    if key: headers['X-Arbiter-Key']=key
    data=None
    if body is not None:
        data=json.dumps(body).encode(); headers['Content-Type']='application/json'
    req=urllib.request.Request(base.rstrip('/')+path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            raw=r.read(); return r.status,(json.loads(raw.decode()) if raw else {}),dict(r.headers)
    except urllib.error.HTTPError as e:
        raw=e.read()
        try: payload=json.loads(raw.decode())
        except Exception: payload=raw.decode(errors='replace')
        return e.code,payload,dict(e.headers)


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--base-url',default='http://127.0.0.1:8000'); ap.add_argument('--api-key',default=None)
    a=ap.parse_args(); passed=failed=0
    def check(label, cond, detail=''):
        nonlocal passed,failed
        if cond: passed+=1; print('[PASS]',label)
        else: failed+=1; print('[FAIL]',label,('— '+detail if detail else ''))

    st,h,_=request(a.base_url,'/api/health',key=a.api_key)
    check('API reachable and v0.16+', st==200 and tuple(int(x) for x in str(h.get('version','0.0')).split('.')[:2]) >= (0,16), f'{st} {h}')

    st,p,_=request(a.base_url,'/api/model-gateway',key=a.api_key)
    check('model gateway posture loads', st==200, f'{st} {p}')
    check('gateway reports v0.16', p.get('gateway_version')=='0.16.0', str(p))
    check('gateway exposes provider readiness', isinstance(p.get('provider_ready'), bool), str(p))
    check('gateway exposes configured default model', bool(p.get('default_model')), str(p))
    check('gateway exposes configured fast model', bool(p.get('fast_model')), str(p))
    check('model tools are disabled in v0.16', p.get('tools_enabled') is False, str(p))
    check('gateway authority boundary is advisory', 'ADVISORY' in str(p.get('authority_boundary','')).upper(), str(p))

    st,selft,_=request(a.base_url,'/api/model-gateway/self-test','POST',{},a.api_key)
    check('governed model self-test completes', st==200 and selft.get('status')=='completed', f'{st} {selft}')
    authority=selft.get('authority') or {}
    check('self-test has zero settlement authority', authority.get('binding') is False and authority.get('settlement_authority') is False, str(authority))
    prov=selft.get('provenance') or {}
    check('self-test records prompt identity/version', bool(prov.get('prompt_id')) and bool(prov.get('prompt_version')), str(prov))
    check('self-test records input and output hashes', bool(prov.get('input_hash')) and bool(prov.get('output_hash')), str(prov))
    check('self-test structured validation passes', prov.get('validation_status')=='PASS', str(prov))
    check('self-test output labels itself advisory', (selft.get('output') or {}).get('advisory_only') is True, str(selft.get('output')))

    inv_id=selft.get('invocation_id')
    st,listing,_=request(a.base_url,'/api/model-invocations?limit=100',key=a.api_key)
    invocations=listing.get('invocations',[]) if isinstance(listing,dict) else []
    row=next((x for x in invocations if x.get('invocation_id')==inv_id),None)
    check('model invocation registry is queryable', st==200 and row is not None, str(listing)[:1200])
    check('registry persists non-binding metadata', bool(row) and (row.get('metadata') or {}).get('binding') is False, str(row))

    st,infra,_=request(a.base_url,'/api/infrastructure',key=a.api_key)
    check('infrastructure posture includes model gateway', st==200 and (infra.get('model_gateway') or {}).get('gateway_version')=='0.16.0', f'{st} {infra}')

    st,dev,_=request(a.base_url,'/api/developer',key=a.api_key)
    check('developer manifest exposes model intelligence', st==200 and (dev.get('model_intelligence_gateway') or {}).get('settlement_authority') is False, f'{st} {dev}')

    st,audit,_=request(a.base_url,'/api/audit?limit=200',key=a.api_key)
    events=audit.get('events',[]) if isinstance(audit,dict) else []
    check('model invocation is written to audit chain', st==200 and any(e.get('action')=='model.invocation.recorded' and e.get('object_id')==inv_id for e in events), str(events)[:1200])
    check('audit chain remains valid after model self-test', (audit.get('chain') or {}).get('ok') is True, str(audit.get('chain')))

    total=passed+failed
    print('\n'+'='*64); print(f'RESULT: {passed}/{total} checks passed; {failed} failed'); print('MODEL INTELLIGENCE GATE:', 'PASS' if failed==0 else 'FAIL')
    return 0 if failed==0 else 1

if __name__=='__main__': raise SystemExit(main())
