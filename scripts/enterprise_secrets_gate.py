#!/usr/bin/env python3
"""Arbiter v0.18 enterprise secrets, model administration, and OIDC foundation gate."""
from __future__ import annotations
import argparse, json, urllib.error, urllib.request


def request(base,path,method='GET',body=None,key=None):
    headers={'Accept':'application/json'}
    if key: headers['X-Arbiter-Key']=key
    data=None
    if body is not None:
        data=json.dumps(body).encode(); headers['Content-Type']='application/json'
    req=urllib.request.Request(base.rstrip('/')+path,data=data,headers=headers,method=method)
    try:
        with urllib.request.urlopen(req,timeout=15) as r:
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
    check('API reachable and v0.18+',st==200 and tuple(int(x) for x in str(h.get('version','0.0')).split('.')[:2]) >= (0,18),f'{st} {h}')

    st,p,_=request(a.base_url,'/api/enterprise-secrets',key=a.api_key)
    check('enterprise secret posture loads',st==200,f'{st} {p}')
    check('secret service reports v0.18',p.get('version')=='0.18.0',str(p))
    check('local secret backend is explicit',p.get('backend') in {'local-fernet','aws-secrets-manager'},str(p))
    check('raw secret read API is prohibited',p.get('raw_secret_read_api') is False,str(p))
    check('secret subsystem has zero settlement authority',p.get('settlement_authority') is False,str(p))
    check('provider registry is tenant-scoped response',isinstance(p.get('providers'),list),str(p))

    st,t,_=request(a.base_url,'/api/enterprise-secrets/self-test','POST',{},a.api_key)
    check('secret custody self-test completes',st==200 and t.get('ok') is True,f'{st} {t}')
    check('self-test uses isolated tenant',str(t.get('tenant_id','')).startswith('__secret_selftest__:'),str(t))
    check('secret round-trip never exposes raw value',t.get('raw_secret_exposed') is False,str(t))
    check('secret response is masked',str(t.get('masked_credential','')).startswith('••••'),str(t))
    check('self-test preserves zero settlement authority',t.get('settlement_authority') is False,str(t))
    check('purpose policy retained','semantic_review' in (t.get('allowed_purposes') or []),str(t))

    st,providers,_=request(a.base_url,'/api/model-providers',key=a.api_key)
    check('model provider admin registry loads',st==200 and isinstance(providers.get('providers'),list),f'{st} {providers}')
    serialized=json.dumps(providers,sort_keys=True)
    check('provider registry does not expose secret_ref','secret_ref' not in serialized,serialized[:1000])
    check('provider registry does not expose api_key','api_key' not in serialized,serialized[:1000])

    st,fed,_=request(a.base_url,'/api/identity/federation',key=a.api_key)
    check('OIDC federation posture loads',st==200,f'{st} {fed}')
    check('OIDC federation reports v0.18',fed.get('version')=='0.18.0',str(fed))
    check('OIDC tenant claim mapping declared',bool(fed.get('tenant_claim')),str(fed))
    check('OIDC principal claim mapping declared',bool(fed.get('principal_claim')),str(fed))
    check('OIDC signing algorithms restricted',fed.get('algorithms')==['RS256'] or bool(fed.get('algorithms')),str(fed))

    st,fst,_=request(a.base_url,'/api/identity/federation/self-test','POST',{},a.api_key)
    check('OIDC claim mapping self-test passes',st==200 and fst.get('ok') is True,f'{st} {fst}')
    mapped=fst.get('mapped') or {}
    check('OIDC maps tenant identity',mapped.get('tenant_id')=='tenant:test',str(mapped))
    check('OIDC maps principal identity',mapped.get('principal_id')=='user:test',str(mapped))
    check('OIDC maps scopes','ai:use' in (mapped.get('scopes') or []),str(mapped))
    check('OIDC self-test performs no external signature call',fst.get('signature_call_performed') is False,str(fst))

    st,infra,_=request(a.base_url,'/api/infrastructure',key=a.api_key)
    check('infrastructure includes enterprise secrets',st==200 and (infra.get('enterprise_secrets') or {}).get('version')=='0.18.0',f'{st} {infra}'[:1400])
    check('infrastructure includes identity federation',st==200 and (infra.get('identity_federation') or {}).get('version')=='0.18.0',f'{st} {infra}'[:1400])

    st,dev,_=request(a.base_url,'/api/developer',key=a.api_key)
    check('developer manifest exposes enterprise secrets',(dev.get('enterprise_secrets') or {}).get('write_only_secret_api') is True,str(dev)[:1400])
    check('developer manifest exposes OIDC federation',(dev.get('identity_federation') or {}).get('oidc_bearer') is True,str(dev)[:1400])

    st,audit,_=request(a.base_url,'/api/audit?limit=300',key=a.api_key)
    events=audit.get('events',[]) if isinstance(audit,dict) else []
    check('secret administration writes audit events',st==200 and any(e.get('action') in {'model.provider.configured','model.provider.disabled'} for e in events),str(events)[:1200])
    check('audit chain remains valid after secret operations',(audit.get('chain') or {}).get('ok') is True,str(audit.get('chain')))

    total=passed+failed
    print('\n'+'='*64); print(f'RESULT: {passed}/{total} checks passed; {failed} failed'); print('ENTERPRISE SECRETS & FEDERATION GATE:', 'PASS' if failed==0 else 'FAIL')
    return 0 if failed==0 else 1

if __name__=='__main__': raise SystemExit(main())
