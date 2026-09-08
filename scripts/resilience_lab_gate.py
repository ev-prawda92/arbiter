#!/usr/bin/env python3
import argparse,json,urllib.request,urllib.error
checks=[]
def chk(n,c):checks.append((n,bool(c)));print(f"[{'PASS' if c else 'FAIL'}] {n}")
def req(b,p,m='GET',body=None,key=None,expect=None):
 h={'Content-Type':'application/json'};data=json.dumps(body).encode() if body is not None else None
 if key:h['X-Arbiter-Key']=key
 try:
  with urllib.request.urlopen(urllib.request.Request(b+p,data=data,headers=h,method=m),timeout=20) as r:return r.status,json.loads(r.read())
 except urllib.error.HTTPError as e:
  d=json.loads(e.read() or b'{}');
  if expect and e.code==expect:return e.code,d
  raise
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--base-url',default='http://127.0.0.1:8000');ap.add_argument('--api-key');a=ap.parse_args()
 _,p=req(a.base_url,'/api/resilience-lab/posture',key=a.api_key);chk('resilience lab posture loads',p.get('version')=='0.23.0');chk('three local scenarios are registered',len(p.get('local_scenarios',[]))==3);chk('five external scenarios are registered',len(p.get('external_scenarios',[]))==5);chk('production resilience is not inferred from local tests',p.get('production_resilience_proven') is False)
 _,st=req(a.base_url,'/api/resilience-lab/self-test','POST',{},a.api_key);chk('resilience lab self-test passes',st.get('ok') is True);chk('self-test executes three scenarios',len(st.get('runs',[]))==3);chk('all self-test scenarios pass',all(x.get('status')=='PASS' for x in st.get('runs',[])));chk('self-test has zero settlement authority',st.get('settlement_authority') is False)
 _,rr=req(a.base_url,'/api/resilience-lab/run','POST',{'scenario':'compiler_stress','iterations':7},a.api_key);run=rr['run'];chk('compiler stress run passes',run.get('status')=='PASS');chk('requested iteration count is preserved',run.get('metrics',{}).get('iterations')==7);chk('stress run reports positive throughput',run.get('metrics',{}).get('ops_per_second',0)>0);chk('stress evidence is hash pinned',str(run.get('evidence_hash','')).startswith('sha256:'))
 _,ls=req(a.base_url,'/api/resilience-lab/runs',key=a.api_key);chk('resilience run registry is queryable',any(x.get('resilience_run_id')==run.get('resilience_run_id') for x in ls.get('runs',[])))
 code,_=req(a.base_url,'/api/resilience-lab/external','POST',{'scenario':'production_load','environment':'local','status':'PASS','metrics':{}},a.api_key,expect=422);chk('local environment cannot masquerade as external evidence',code==422)
 _,ext=req(a.base_url,'/api/resilience-lab/external','POST',{'scenario':'production_load','environment':'staging-test','status':'PASS','metrics':{'synthetic_gate':True}},a.api_key);er=ext['run'];chk('deployed-environment evidence can be recorded',er.get('status')=='PASS');chk('external flag is explicit',er.get('external') is True)
 _,after=req(a.base_url,'/api/resilience-lab/posture',key=a.api_key);chk('external passed scenarios update posture','production_load' in after.get('external_passed',[]));_,dev=req(a.base_url,'/api/developer',key=a.api_key);chk('developer manifest exposes resilience lab',dev.get('resilience_lab',{}).get('version')=='0.23.0');_,infra=req(a.base_url,'/api/infrastructure',key=a.api_key);chk('infrastructure exposes resilience lab',infra.get('resilience_lab',{}).get('version')=='0.23.0');_,aud=req(a.base_url,'/api/audit?limit=1',key=a.api_key);chk('audit chain remains valid',aud.get('chain',{}).get('ok') is True)
 total=len(checks);passed=sum(v for _,v in checks);print('\n'+'='*64);print(f'RESULT: {passed}/{total} checks passed; {total-passed} failed');
 if passed!=total:raise SystemExit(1)
 print('RESILIENCE LAB GATE: PASS')
if __name__=='__main__':main()
