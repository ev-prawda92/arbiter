#!/usr/bin/env python3
import argparse, json, urllib.request, urllib.error

checks=[]
def chk(name, cond):
    checks.append((name,bool(cond))); print(f"[{'PASS' if cond else 'FAIL'}] {name}")
def req(base,path,method='GET',body=None,key=None):
    data=json.dumps(body).encode() if body is not None else None
    h={'Content-Type':'application/json'}
    if key: h['X-Arbiter-Key']=key
    r=urllib.request.Request(base+path,data=data,headers=h,method=method)
    with urllib.request.urlopen(r,timeout=10) as x: return json.loads(x.read().decode())

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--base-url',default='http://127.0.0.1:8000'); ap.add_argument('--api-key'); a=ap.parse_args()
    p=req(a.base_url,'/api/reference-exchange',key=a.api_key)
    chk('reference exchange posture loads',p.get('version')=='0.19.0')
    chk('reference exchange is sandbox mode',p.get('mode')=='reference-sandbox')
    chk('play money only is explicit',p.get('play_money_only') is True)
    chk('real-money custody is disabled',p.get('real_money_custody') is False)
    chk('matching engine is not claimed',p.get('matching_engine') is False)
    st=req(a.base_url,'/api/reference-exchange/self-test','POST',{},a.api_key)
    chk('end-to-end self-test completes',st.get('ok') is True)
    chk('self-test has zero real-money path',st.get('zero_real_money') is True)
    chk('self-test returns market identity',bool(st.get('market_id')))
    chk('self-test either settles or safely holds', bool(st.get('settlement_hash') or st.get('held_safely')))
    d=req(a.base_url,'/api/developer',key=a.api_key)
    chk('developer manifest exposes reference exchange',d.get('reference_exchange',{}).get('version')=='0.19.0')
    chk('reference exchange declares play-money only',d.get('reference_exchange',{}).get('play_money_only') is True)
    infra=req(a.base_url,'/api/infrastructure',key=a.api_key)
    chk('infrastructure summary exposes reference exchange',infra.get('reference_exchange',{}).get('version')=='0.19.0')
    # Create under-specified market and verify fail-safe hold.
    m=req(a.base_url,'/api/reference-exchange/markets','POST',{'title':'Will inflation be above 3%?','rules':'Resolve YES if inflation is above 3%.'},a.api_key)['market']
    chk('ambiguous market is not silently production-like',m.get('state') in {'HELD','OPEN'})
    if m.get('compilation',{}).get('status')!='READY': chk('non-ready compiler status causes HELD',m.get('state')=='HELD')
    else: chk('ready compiler permits OPEN',m.get('state')=='OPEN')
    aud=req(a.base_url,'/api/audit?limit=50',key=a.api_key)
    events=aud.get('events',aud if isinstance(aud,list) else [])
    chk('reference exchange activity is audited',any(str(e.get('action','')).startswith('reference_') for e in events))
    chk('audit chain remains valid',req(a.base_url,'/api/audit?limit=1',key=a.api_key).get('chain',{}).get('ok') is True)
    chk('health reports v0.19+',req(a.base_url,'/api/health',key=a.api_key).get('version','') >= '0.19.0')
    total=len(checks); passed=sum(v for _,v in checks)
    print('\n'+'='*64); print(f'RESULT: {passed}/{total} checks passed; {total-passed} failed')
    if passed!=total: raise SystemExit(1)
    print('REFERENCE EXCHANGE GATE: PASS')
if __name__=='__main__': main()
