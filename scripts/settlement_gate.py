#!/usr/bin/env python3
"""Arbiter v0.12 approval, policy-governance, and settlement-handoff gate."""
from __future__ import annotations
import argparse, json, os, urllib.request, urllib.error, uuid


def request(base,path,method='GET',body=None,key=None):
    headers={'Accept':'application/json'}
    if key: headers['X-Arbiter-Key']=key
    data=None
    if body is not None:
        data=json.dumps(body).encode(); headers['Content-Type']='application/json'
    req=urllib.request.Request(base.rstrip('/')+path,data=data,headers=headers,method=method)
    try:
        with urllib.request.urlopen(req,timeout=15) as r:
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
    def get(p): return request(a.base_url,p,'GET',None,a.api_key)
    def post(p,b): return request(a.base_url,p,'POST',b,a.api_key)

    suffix=uuid.uuid4().hex[:8]; aid=f'AUTH-V012-{suffix}'; cid=f'V012-SETTLE-{suffix}'
    st,h=get('/api/health'); 
    def version_at_least(v, major, minor):
        try:
            parts=str(v).split('.')
            return (int(parts[0]), int(parts[1])) >= (major, minor)
        except Exception:
            return False
    check('API reachable and v0.12+',st==200 and version_at_least(h.get('version',''),0,12),f'{st} {h}')

    # Governed policy workflow.
    st,active=get('/api/policy'); base_version=active.get('version')
    check('active policy readable',st==200 and bool(base_version),str(active))
    st,out=post('/api/policy/drafts',{'weights':{'source':0.30,'timing':0.30,'definition':0.40},'thresholds':{'clean':20,'monitored':50},'actor':'maker:policy','note':'v0.12 settlement gate no-op policy version'})
    draft=(out.get('draft') or {}); did=draft.get('draft_id')
    check('policy change created as draft',st==200 and draft.get('status')=='draft' and bool(did),f'{st} {out}')
    st,out=post(f'/api/policy/drafts/{did}/submit',{'actor':'maker:policy'})
    check('policy draft submitted for approval',st==200 and out.get('draft',{}).get('status')=='pending_approval',f'{st} {out}')
    st,out=post(f'/api/policy/drafts/{did}/approve',{'actor':'maker:policy'})
    check('policy maker cannot self-approve',st==422,f'{st} {out}')
    st,out=post(f'/api/policy/drafts/{did}/approve',{'actor':'checker:compliance'})
    check('independent checker approves policy',st==200 and out.get('draft',{}).get('status')=='approved',f'{st} {out}')
    st,out=post(f'/api/policy/drafts/{did}/activate',{'actor':'admin:policy'})
    new_version=(out.get('active_policy') or {}).get('version')
    check('approved policy activates as new immutable version',st==200 and new_version and new_version!=base_version,f'{st} {out}')

    # Build a clean, completed resolution run eligible for authorization.
    st,out=post('/api/authorities',{'authority_id':aid,'version':1,'name':'v0.12 gate authority','organization':'Arbiter Test','source_type':'test_fixture','status':'approved','actor':'test:settlement-gate'})
    check('test authority created',st==200,f'{st} {out}')
    st,out=post('/api/contracts',{'contract_id':cid,'contract_version':1,'title':'v0.12 settlement gate contract','definition':{'type':'numeric_threshold','operator':'>','threshold':3.0},'timing':{'observation':'test','timezone':'UTC'},'authority_ids':[aid],'source_precedence':[aid],'revision_policy':{'policy':'first_print'},'approval_policy':{'auto_if_all_controls_pass':True},'metadata':{'exchange_profile':'kalshi_dcm'},'actor':'maker:market-ops','status':'approved'})
    check('governed contract created',st==200,f'{st} {out}')
    st,out=post('/api/evidence',{'authority_id':aid,'authority_version':1,'normalized_value':3.4,'raw_payload_hash':'sha256:'+('a'*64),'parser_version':'test.v1','contract_id':cid,'source_locator':'fixture://v012','actor':'system:evidence'})
    evid=(out.get('evidence') or {}).get('evidence_id'); check('evidence appended',st==200 and bool(evid),f'{st} {out}')
    st,out=post('/api/resolution-runs',{'contract_id':cid,'contract_version':1,'policy_version':new_version,'engine_version':'0.12.0','evidence_ids':[evid],'state':'completed','outcome':'YES','exceptions':[],'approvals':[],'result':{'test':True},'actor':'system:resolver'})
    run=(out.get('run') or {}); rid=run.get('run_id'); check('completed resolution run created',st==200 and bool(rid),f'{st} {out}')

    # A held run must never enter settlement approval.
    st,out=post('/api/resolution-runs',{'contract_id':cid,'contract_version':1,'policy_version':new_version,'engine_version':'0.12.0','evidence_ids':[evid],'state':'completed','outcome':'HELD','exceptions':[],'approvals':[],'result':{},'actor':'system:resolver'})
    held=(out.get('run') or {}).get('run_id'); check('held test run created',st==200 and bool(held),f'{st} {out}')
    st,out=post('/api/approvals',{'object_type':'resolution_run','object_id':held,'action':'authorize_settlement_handoff','exchange_profile':'kalshi_dcm','requested_by':'maker:settlement','rationale':'must fail'})
    check('HELD resolution cannot request settlement authorization',st==422,f'{st} {out}')

    # Maker-checker settlement approval.
    st,out=post('/api/approvals',{'object_type':'resolution_run','object_id':rid,'action':'authorize_settlement_handoff','exchange_profile':'kalshi_dcm','requested_by':'maker:settlement','rationale':'clean governed run','required_approvals':1,'metadata':{'test':True}})
    apr=(out.get('approval') or {}); apid=apr.get('approval_id')
    check('settlement authorization request created',st==200 and apr.get('status')=='pending' and bool(apid),f'{st} {out}')
    st,out=post(f'/api/approvals/{apid}/settlement-packet',{'actor':'system:packetizer'})
    check('packet cannot be created before approval',st==422,f'{st} {out}')
    st,out=post(f'/api/approvals/{apid}/decision',{'actor':'maker:settlement','decision':'approve','note':'self approval should fail'})
    check('settlement maker cannot self-approve',st==422,f'{st} {out}')
    st,out=post(f'/api/approvals/{apid}/decision',{'actor':'checker:compliance','decision':'approve','note':'independent checker'})
    check('independent checker authorizes handoff',st==200 and out.get('approval',{}).get('status')=='approved',f'{st} {out}')
    st,out=post(f'/api/approvals/{apid}/decision',{'actor':'checker:compliance','decision':'approve','note':'duplicate'})
    check('same checker cannot vote twice',st==422,f'{st} {out}')
    st,out=post(f'/api/approvals/{apid}/settlement-packet',{'actor':'system:packetizer'})
    pkt=(out.get('packet') or {}); pid=pkt.get('packet_id')
    check('approved run produces signed authorization packet',st==200 and bool(pid) and str(pkt.get('signature','')).startswith('hmac-sha256:'),f'{st} {out}')
    check('packet pins contract/policy/run',pkt.get('run_id')==rid and pkt.get('contract_id')==cid and pkt.get('policy_version')==new_version,str(pkt))
    check('Kalshi profile selects exchange authorization terminal action',pkt.get('terminal_action')=='prepare_exchange_resolution_authorization',str(pkt))
    check('local packet explicitly not production eligible',pkt.get('production_eligible') is False and pkt.get('signature_mode')=='local-development-hmac',str(pkt))
    st,out2=post(f'/api/approvals/{apid}/settlement-packet',{'actor':'system:packetizer'})
    check('packetization is idempotent per approval',st==200 and out2.get('packet',{}).get('packet_id')==pid,f'{st} {out2}')

    # Polymarket boundary gets its own terminal handoff semantics.
    st,out=post('/api/approvals',{'object_type':'resolution_run','object_id':rid,'action':'authorize_settlement_handoff','exchange_profile':'polymarket_uma','requested_by':'maker:oracle','rationale':'oracle handoff','required_approvals':1})
    umaid=(out.get('approval') or {}).get('approval_id'); check('UMA handoff approval can be requested',st==200 and bool(umaid),f'{st} {out}')
    st,out=post(f'/api/approvals/{umaid}/decision',{'actor':'checker:oracle-ops','decision':'approve'})
    st,out=post(f'/api/approvals/{umaid}/settlement-packet',{'actor':'system:packetizer'})
    upkt=out.get('packet',{}) if st==200 else {}
    check('Polymarket profile selects oracle proposal/dispute packet',st==200 and upkt.get('terminal_action')=='prepare_oracle_proposal_or_dispute_packet',f'{st} {out}')

    st,out=get('/api/approvals?status=approved')
    check('approval registry exposes approved authorizations',st==200 and len(out.get('approvals',[]))>=2,f'{st} {out}')
    st,out=get(f'/api/settlement-packets?run_id={rid}')
    check('settlement packet registry is queryable',st==200 and len(out.get('packets',[]))>=2,f'{st} {out}')
    st,out=get('/api/infrastructure'); ac=out.get('approval_control',{}) if st==200 else {}
    check('infrastructure reports approval control layer',st==200 and ac.get('settlement_packets',0)>=2,f'{st} {out}')
    st,out=get('/api/audit?limit=500'); actions={e.get('action') for e in out.get('events',[])} if st==200 else set()
    check('approval and settlement actions are audited',{'approval.requested','approval.approved','settlement.packet.created','policy.version.activated'}.issubset(actions),str(sorted(actions))[:1200])
    check('audit chain valid after authorization flow',st==200 and out.get('chain',{}).get('ok') is True,str(out.get('chain')))

    total=passed+failed
    print('\n'+'='*64); print(f'RESULT: {passed}/{total} checks passed; {failed} failed'); print('SETTLEMENT CONTROL GATE:', 'PASS' if failed==0 else 'FAIL')
    return 0 if failed==0 else 1
if __name__=='__main__': raise SystemExit(main())
