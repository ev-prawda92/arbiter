#!/usr/bin/env python3
"""Arbiter v0.13 Semantic Contract Intelligence release gate."""
from __future__ import annotations
import argparse, json, os, urllib.error, urllib.request, uuid


def request(base, path, method='GET', body=None, key=None):
    headers={'Accept':'application/json'}
    if key: headers['X-Arbiter-Key']=key
    data=None
    if body is not None:
        data=json.dumps(body).encode(); headers['Content-Type']='application/json'
    req=urllib.request.Request(base.rstrip('/')+path,data=data,headers=headers,method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            raw=r.read(); return r.status,(json.loads(raw.decode()) if raw else {})
    except urllib.error.HTTPError as e:
        raw=e.read()
        try: payload=json.loads(raw.decode())
        except Exception: payload=raw.decode(errors='replace')
        return e.code,payload


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--base-url',default='http://127.0.0.1:8000'); ap.add_argument('--api-key',default=os.environ.get('ARBITER_API_KEY'))
    a=ap.parse_args(); passed=failed=0
    def check(label,cond,detail=''):
        nonlocal passed,failed
        if cond: passed+=1; print('[PASS]',label)
        else: failed+=1; print('[FAIL]',label,('— '+detail if detail else ''))
    def post(p,b): return request(a.base_url,p,'POST',b,a.api_key)
    def get(p): return request(a.base_url,p,'GET',None,a.api_key)

    st,h=get('/api/health'); check('API reachable and v0.13',st==200 and str(h.get('version','')).startswith('0.13'),f'{st} {h}')
    check('product identifies semantic contract intelligence', 'Semantic Contract Intelligence' in str(h.get('product','')), str(h))

    base={'contract_id':'SEM-'+uuid.uuid4().hex[:8], 'contract_version':1, 'exchange_profile':'generic'}
    vague_title='Will U.S. CPI be above 3.0% on September 11, 2026?'
    vague_rules='This market resolves YES if the U.S. Bureau of Labor Statistics reports CPI above 3.0% on September 11, 2026 at 08:30 EDT. The first published release controls.'
    st,v=post('/api/semantic-analyze',{**base,'title':vague_title,'rules':vague_rules})
    check('semantic endpoint responds',st==200,f'{st} {v}')
    check('CPI concept recognized',v.get('concepts',[{}])[0].get('concept_id')=='MACRO.CPI',str(v))
    check('CPI explained in plain language','price index' in v.get('concepts',[{}])[0].get('plain_language','').lower(),str(v))
    check('vague CPI is semantic REVIEW',v.get('status')=='REVIEW',str(v))
    u=set(v.get('unresolved_semantic_fields') or [])
    check('vague CPI flags metric series','semantic.metric_series' in u,str(u))
    check('vague CPI flags measurement basis','semantic.measurement_basis' in u,str(u))
    check('vague CPI flags reference period','semantic.reference_period' in u,str(u))
    check('publisher extracted',v.get('extracted_semantics',{}).get('publisher')=='U.S. Bureau of Labor Statistics',str(v))
    check('revision semantics extracted',v.get('extracted_semantics',{}).get('revision_semantics')=='first_release',str(v))
    check('semantic analysis has stable hash',str(v.get('semantic_hash','')).startswith('sha256:'),str(v))
    check('semantic layer states non-settlement boundary','does not itself determine settlement' in v.get('boundary',''),str(v))

    precise_title='Will U.S. CPI-U All Items year-over-year be above 3.0%?'
    precise_rules='Resolves YES if BLS CPI-U All Items for August 2026, not seasonally adjusted, year-over-year is above 3.0% in the September 2026 release at 08:30 EDT. The first release controls.'
    st,p=post('/api/semantic-analyze',{**base,'contract_id':'SEM-'+uuid.uuid4().hex[:8],'title':precise_title,'rules':precise_rules})
    check('precise CPI semantic analysis responds',st==200,f'{st} {p}')
    check('precise CPI is semantic READY',p.get('status')=='READY',str(p))
    ex=p.get('extracted_semantics') or {}
    check('CPI-U series extracted',ex.get('series')=='CPI-U',str(ex))
    check('YoY basis extracted',ex.get('measurement_basis')=='year_over_year_percent_change',str(ex))
    check('reference period extracted','August 2026' in str(ex.get('reference_period_text','')),str(ex))
    check('seasonal basis extracted',ex.get('seasonal_adjustment')=='not_seasonally_adjusted',str(ex))

    fed_title='Will the Federal Reserve cut interest rates by September 30, 2026?'
    fed_rules='Resolves YES if the FOMC lowers the federal funds target range by September 30, 2026 at 11:59 PM ET based on the official FOMC statement.'
    st,f=post('/api/semantic-analyze',{**base,'contract_id':'SEM-'+uuid.uuid4().hex[:8],'title':fed_title,'rules':fed_rules})
    check('Fed concept recognized',st==200 and f.get('concepts',[{}])[0].get('concept_id')=='MONETARY_POLICY.FOMC_RATE_ACTION',str(f))
    check('Fed target range extracted',f.get('extracted_semantics',{}).get('rate_instrument')=='federal_funds_target_range',str(f))
    check('Fed governing publication extracted',f.get('extracted_semantics',{}).get('governing_publication')=='FOMC statement',str(f))
    check('precise Fed is semantic READY',f.get('status')=='READY',str(f))

    st,c=post('/api/compile',{**base,'contract_id':'SEM-'+uuid.uuid4().hex[:8],'title':vague_title,'rules':vague_rules})
    check('compiler embeds semantic analysis',st==200 and isinstance(c.get('semantic'),dict),f'{st} {c}')
    check('semantic gate is advisory in v0.13',c.get('semantic_gate_mode')=='advisory',str(c))
    check('legacy compiler gate remains backwards-compatible',c.get('status')=='READY',str(c))
    check('embedded semantic gate still catches CPI ambiguity',c.get('semantic',{}).get('status')=='REVIEW',str(c))
    check('compiler version advanced',c.get('compiler_version')=='0.1.3',str(c))

    st,d=get('/api/developer')
    check('developer manifest exposes semantic endpoint',st==200 and d.get('semantic_contract_intelligence',{}).get('endpoint')=='/api/semantic-analyze',str(d))

    print('\n'+'='*64)
    print(f'RESULT: {passed}/{passed+failed} checks passed; {failed} failed')
    print('SEMANTIC CONTRACT GATE:', 'PASS' if failed==0 else 'FAIL')
    raise SystemExit(1 if failed else 0)

if __name__=='__main__': main()
