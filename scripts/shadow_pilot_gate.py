#!/usr/bin/env python3
import argparse,json,urllib.request
checks=[]
def chk(n,c):checks.append((n,bool(c)));print(f"[{'PASS' if c else 'FAIL'}] {n}")
def req(b,p,m='GET',body=None,key=None):
 h={'Content-Type':'application/json'};data=json.dumps(body).encode() if body is not None else None
 if key:h['X-Arbiter-Key']=key
 with urllib.request.urlopen(urllib.request.Request(b+p,data=data,headers=h,method=m),timeout=20) as r:return json.loads(r.read())
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--base-url',default='http://127.0.0.1:8000');ap.add_argument('--api-key');a=ap.parse_args()
 p=req(a.base_url,'/api/shadow-pilots/posture',key=a.api_key);chk('shadow pilot posture loads',p.get('version')=='0.25.0');chk('shadow-only mode is explicit',p.get('mode')=='shadow-only');chk('shadow pilot has zero settlement authority',p.get('settlement_authority') is False);chk('shadow pilot cannot mutate venue settlement',p.get('venue_settlement_mutation') is False)
 st=req(a.base_url,'/api/shadow-pilots/self-test/run','POST',{},a.api_key);chk('shadow pilot self-test passes',st.get('ok') is True);pilot=st.get('pilot',{});chk('self-test contains one analyzed contract',pilot.get('metrics',{}).get('contracts')==1);chk('self-test reconciliation agrees',pilot.get('metrics',{}).get('agreement_count')==1)
 created=req(a.base_url,'/api/shadow-pilots','POST',{'venue':'Synthetic Design Partner','name':'Gate shadow pilot','contract_target':50,'metadata':{'gate':True}},a.api_key)['pilot'];pid=created['pilot_id'];chk('shadow pilot can be created',created.get('status')=='ACTIVE');chk('created pilot remains shadow mode',created.get('mode')=='shadow')
 c=req(a.base_url,f'/api/shadow-pilots/{pid}/contracts','POST',{'venue_contract_id':'GATE-1','title':'Will inflation exceed 3%?','rules':'Resolve YES if inflation is above 3%.'},a.api_key)['contract'];chk('venue contract is analyzed',c.get('compiler_status') in {'READY','REVIEW','BLOCK'});chk('semantic analysis is hash pinned',str(c.get('semantic_hash','')).startswith('sha256:'));chk('compiler analysis is hash pinned',str(c.get('compilation_hash','')).startswith('sha256:'))
 r=req(a.base_url,f"/api/shadow-contracts/{c['shadow_contract_id']}/resolution",'POST',{'venue_outcome':'YES','arbiter_outcome':'HELD','evidence':{'synthetic_gate':True}},a.api_key)['contract'];chk('shadow resolution can record a disagreement',r.get('agreement') is False);after=req(a.base_url,f'/api/shadow-pilots/{pid}',key=a.api_key)['pilot'];m=after.get('metrics',{});chk('pilot metrics count imported contracts',m.get('contracts')==1);chk('pilot metrics count disagreements',m.get('disagreement_count')==1);chk('pilot agreement rate reflects disagreement',m.get('agreement_rate')==0.0);chk('official settlement authority remains false',after.get('settlement_authority') is False)
 dev=req(a.base_url,'/api/developer',key=a.api_key);chk('developer manifest exposes shadow pilot',dev.get('shadow_pilot',{}).get('version')=='0.25.0');infra=req(a.base_url,'/api/infrastructure',key=a.api_key);chk('infrastructure exposes shadow pilot',infra.get('shadow_pilot',{}).get('version')=='0.25.0');aud=req(a.base_url,'/api/audit?limit=1',key=a.api_key);chk('audit chain remains valid',aud.get('chain',{}).get('ok') is True)
 total=len(checks);passed=sum(v for _,v in checks);print('\n'+'='*64);print(f'RESULT: {passed}/{total} checks passed; {total-passed} failed');
 if passed!=total:raise SystemExit(1)
 print('SHADOW PILOT GATE: PASS')
if __name__=='__main__':main()
