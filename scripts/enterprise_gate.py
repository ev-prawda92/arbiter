#!/usr/bin/env python3
"""Arbiter v0.10 enterprise boundary smoke test."""
from __future__ import annotations
import argparse, json, urllib.request, urllib.error


def request(base, path, method='GET', body=None, key=None):
    headers={'Accept':'application/json'}
    if key: headers['X-Arbiter-Key']=key
    data=None
    if body is not None:
        data=json.dumps(body).encode(); headers['Content-Type']='application/json'
    req=urllib.request.Request(base.rstrip('/')+path,data=data,headers=headers,method=method)
    try:
        with urllib.request.urlopen(req,timeout=10) as r:
            raw=r.read(); payload=json.loads(raw.decode()) if raw else {}
            return r.status,payload,dict(r.headers)
    except urllib.error.HTTPError as e:
        raw=e.read();
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

    st,ready,h=request(a.base_url,'/api/readiness',key=a.api_key)
    check('readiness endpoint passes', st==200 and ready.get('ready') is True, f'{st} {ready}')
    st,posture,h=request(a.base_url,'/api/security-posture',key=a.api_key)
    check('security posture endpoint loads', st==200, f'{st}')
    check('local configuration gate is explicit', posture.get('configuration_gate') in {'PASS','BLOCK'}, str(posture))
    hl={str(k).lower():v for k,v in h.items()}
    check('security header X-Content-Type-Options', hl.get('x-content-type-options')=='nosniff', str(h))
    check('security header X-Frame-Options', hl.get('x-frame-options')=='DENY', str(h))
    check('request correlation header', bool(hl.get('x-request-id')), str(h))

    st,p,h=request(a.base_url,'/api/exchange-profiles',key=a.api_key)
    ids={x.get('id') for x in p.get('profiles',[])} if st==200 else set()
    check('Kalshi/DCM profile registered','kalshi_dcm' in ids,str(ids))
    check('Polymarket/UMA profile registered','polymarket_uma' in ids,str(ids))

    base_case={
        'question':'Will U.S. CPI be above 3.0% on September 11, 2026?',
        'criteria':'This market resolves YES if the U.S. Bureau of Labor Statistics reports CPI above 3.0% on September 11, 2026 at 08:30 EDT. The first published release controls.',
        'use_llm':False,'actor':'test:enterprise-gate'
    }
    for profile,expected in [('kalshi_dcm','prepare_exchange_resolution_authorization'),('polymarket_uma','prepare_oracle_proposal_or_dispute_packet')]:
        body=dict(base_case); body['exchange_profile']=profile
        st,out,h=request(a.base_url,'/api/analyze','POST',body,a.api_key)
        b=out.get('integration_boundary',{}) if st==200 else {}
        # With no evidence READY remains PENDING, so both should monitor first.
        check(f'{profile}: boundary attached', b.get('exchange_profile')==profile, str(b))
        check(f'{profile}: awaiting evidence stays monitoring', b.get('arbiter_terminal_action')=='monitor_authoritative_evidence', str(b))
        check(f'{profile}: settlement authority declared', bool(b.get('settlement_authority')), str(b))

    total=passed+failed
    print('\n'+'='*64); print(f'RESULT: {passed}/{total} checks passed; {failed} failed'); print('ENTERPRISE GATE:', 'PASS' if failed==0 else 'FAIL')
    return 0 if failed==0 else 1
if __name__=='__main__': raise SystemExit(main())
