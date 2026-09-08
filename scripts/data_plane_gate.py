#!/usr/bin/env python3
"""Arbiter v0.17 production data-plane deterministic release gate."""
from __future__ import annotations
import argparse, json, urllib.error, urllib.request


def request(base, path, method='GET', body=None, key=None):
    headers={'Accept':'application/json'}
    if key: headers['X-Arbiter-Key']=key
    data=None
    if body is not None:
        data=json.dumps(body).encode(); headers['Content-Type']='application/json'
    req=urllib.request.Request(base.rstrip('/')+path,data=data,headers=headers,method=method)
    try:
        with urllib.request.urlopen(req,timeout=20) as r:
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
    check('API reachable and v0.17+',st==200 and ver >= (0,17),f'{st} {h}')

    st,p,_=request(a.base_url,'/api/data-plane',key=a.api_key)
    check('data-plane posture loads',st==200,f'{st} {p}')
    check('data-plane reports v0.17',p.get('version')=='0.17.0',str(p))
    check('local data-plane configuration passes',p.get('configuration_gate')=='PASS',str(p.get('configuration_findings')))
    db=p.get('database') or {}; tenant=p.get('tenant_isolation') or {}; obj=p.get('object_storage') or {}; backup=p.get('backup_restore') or {}
    check('local reference backend is SQLite',db.get('backend')=='sqlite',str(db))
    check('production backend is explicitly PostgreSQL',db.get('production_required_backend')=='postgresql',str(db))
    check('transaction posture includes advisory-lock serialization','advisory lock' in str(db.get('transaction_model','')).lower(),str(db))
    check('PostgreSQL tenant RLS is declared',tenant.get('postgres_rls') is True,str(tenant))
    check('PostgreSQL FORCE RLS is declared',tenant.get('force_rls') is True,str(tenant))
    check('tenant-scoped table registry is substantial',int(tenant.get('tenant_scoped_table_count',0)) >= 20,str(tenant))
    check('object storage is content-addressed',obj.get('content_addressed') is True,str(obj))
    check('object storage uses SHA-256',str(obj.get('algorithm','')).lower()=='sha256',str(obj))
    check('backup/restore posture is declared',bool(backup.get('strategy')),str(backup))

    st,t,_=request(a.base_url,'/api/data-plane/self-test','POST',{},a.api_key)
    check('data-plane self-test completes',st==200 and t.get('status')=='completed',f'{st} {t}')
    o=(t.get('object_store') or {}); ref=o.get('ref') or {}; verification=o.get('verification') or {}
    check('content-addressed object round-trip verifies',verification.get('ok') is True,str(o))
    check('object verification preserves exact digest',bool(ref.get('digest')) and verification.get('actual_digest')==ref.get('digest'),str(o))
    sql=t.get('sql_translation') or {}
    check('qmark SQL parameters translate for psycopg',sql.get('ok') is True and str(sql.get('sql','')).count('%s')==2,str(sql))
    check('SQL translator preserves literal question marks',"'?'" in str(sql.get('sql','')),str(sql))
    rls=t.get('rls') or {}
    check('RLS self-test includes FORCE ROW LEVEL SECURITY',rls.get('force_rls') is True,str(rls))
    check('RLS self-test includes WITH CHECK write isolation',rls.get('with_check') is True,str(rls))
    ctx=t.get('context') or {}
    check('request/worker context can switch tenant',((ctx.get('during') or {}).get('tenant_id')=='tenant-self-test'),str(ctx))
    check('temporary data-plane context restores cleanly',ctx.get('before')==ctx.get('after'),str(ctx))
    authority=t.get('authority') or {}
    check('data-plane self-test has zero settlement authority',authority.get('binding') is False and authority.get('settlement_authority') is False,str(authority))

    st,b,_=request(a.base_url,'/api/data-plane/backup','POST',{},a.api_key)
    backup_result=b.get('backup') or {}
    check('local online backup can be created',st==200 and b.get('executed') is True and bool(backup_result.get('manifest_file')),f'{st} {b}')
    check('backup manifest pins SHA-256 and size',backup_result.get('schema')=='arbiter.backup-manifest.v1' and len(str(backup_result.get('sha256','')))==64 and int(backup_result.get('size_bytes',0))>0,str(backup_result))
    manifest=backup_result.get('manifest_file')
    st,v,_=request(a.base_url,'/api/data-plane/backup/verify','POST',{'manifest_file':manifest},a.api_key) if manifest else (0,{}, {})
    check('backup verification passes checksum and SQLite integrity',st==200 and v.get('ok') is True and v.get('sqlite_integrity')=='ok',f'{st} {v}')

    st,infra,_=request(a.base_url,'/api/infrastructure',key=a.api_key)
    check('infrastructure summary includes v0.17 data plane',st==200 and (infra.get('data_plane') or {}).get('version')=='0.17.0',f'{st} {infra}')
    st,dev,_=request(a.base_url,'/api/developer',key=a.api_key)
    check('developer manifest exposes production data plane',st==200 and (dev.get('production_data_plane') or {}).get('version')=='0.17.0' and (dev.get('production_data_plane') or {}).get('tenant_rls') is True,f'{st} {dev}')

    total=passed+failed
    print('\n'+'='*64); print(f'RESULT: {passed}/{total} checks passed; {failed} failed'); print('PRODUCTION DATA PLANE GATE:', 'PASS' if failed==0 else 'FAIL')
    return 0 if failed==0 else 1

if __name__=='__main__': raise SystemExit(main())
