#!/usr/bin/env python3
"""Arbiter v0.14 enterprise identity/tenant gate against a running local API."""
from __future__ import annotations
import argparse, json, urllib.request, urllib.error, uuid

def request(base,path,method='GET',body=None,key=None,tenant=None):
    headers={'Accept':'application/json'}
    if key: headers['X-Arbiter-Key']=key
    if tenant: headers['X-Arbiter-Tenant']=tenant
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
    check('API reachable and v0.14+',st==200 and tuple(int(x) for x in str(h.get('version','0.0')).split('.')[:2]) >= (0,14),f'{st} {h}')
    st,w,_=request(a.base_url,'/api/identity/whoami',key=a.api_key)
    p=w.get('principal',{}) if st==200 else {}
    check('whoami endpoint loads',st==200,str(w))
    check('local principal has tenant context',p.get('tenant_id')=='local',str(p))
    check('local principal has principal id',bool(p.get('principal_id')),str(p))
    check('local principal type is declared',p.get('principal_type') in {'human','service'},str(p))
    st,posture,_=request(a.base_url,'/api/identity/posture',key=a.api_key)
    check('identity posture endpoint loads',st==200,str(posture))
    check('tenant boundary declared',posture.get('tenant_boundary')=='principal-bound tenant context',str(posture))
    st,tenants,_=request(a.base_url,'/api/tenants',key=a.api_key)
    check('tenant registry loads',st==200,str(tenants))
    ids={t.get('tenant_id') for t in tenants.get('tenants',[])} if st==200 else set()
    check('local tenant seeded','local' in ids,str(ids))
    suffix=uuid.uuid4().hex[:8]; tid='tenant-test-'+suffix
    st,out,_=request(a.base_url,'/api/tenants','POST',{'tenant_id':tid,'name':'Gate Tenant','actor':'test:identity-gate'},a.api_key)
    check('tenant can be governed-created',st==200 and out.get('tenant',{}).get('tenant_id')==tid,f'{st} {out}')
    st,out2,_=request(a.base_url,'/api/tenants','POST',{'tenant_id':tid,'name':'Duplicate','actor':'test:identity-gate'},a.api_key)
    check('duplicate tenant rejected',st==409,f'{st} {out2}')
    pid='svc:test:'+suffix
    st,pr,_=request(a.base_url,'/api/principals','POST',{'principal_id':pid,'tenant_id':tid,'principal_type':'service','display_name':'Evidence Service','actor':'test:identity-gate'},a.api_key)
    check('service principal can be registered',st==200 and pr.get('principal',{}).get('principal_type')=='service',f'{st} {pr}')
    st,prs,_=request(a.base_url,f'/api/principals?tenant_id={tid}',key=a.api_key)
    check('principals can be tenant-filtered',st==200 and any(x.get('principal_id')==pid for x in prs.get('principals',[])),str(prs))
    st,bad,_=request(a.base_url,'/api/principals','POST',{'principal_id':'bad:'+suffix,'tenant_id':'missing','principal_type':'service','display_name':'Bad','actor':'test:identity-gate'},a.api_key)
    check('principal cannot bind unknown tenant',st==422,f'{st} {bad}')
    st,bad2,_=request(a.base_url,'/api/principals','POST',{'principal_id':'bad2:'+suffix,'tenant_id':tid,'principal_type':'robot','display_name':'Bad','actor':'test:identity-gate'},a.api_key)
    check('principal type is constrained',st==422,f'{st} {bad2}')
    st,audit,_=request(a.base_url,'/api/audit?limit=100',key=a.api_key)
    events=audit.get('events',audit if isinstance(audit,list) else [])
    if isinstance(events,dict): events=events.get('events',[])
    check('identity changes are audited',st==200 and any((e.get('action') in {'tenant.created','principal.registered'}) for e in (events or [])),str(audit)[:800])
    st,ready,_=request(a.base_url,'/api/readiness',key=a.api_key)
    check('readiness remains healthy after identity operations',st==200 and ready.get('ready') is True,f'{st} {ready}')
    total=passed+failed
    print('\n'+'='*64); print(f'RESULT: {passed}/{total} checks passed; {failed} failed'); print('IDENTITY & TENANT GATE:', 'PASS' if failed==0 else 'FAIL')
    return 0 if failed==0 else 1
if __name__=='__main__': raise SystemExit(main())
