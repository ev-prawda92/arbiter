#!/usr/bin/env python3
import argparse,json,urllib.request
checks=[]
def chk(n,c): checks.append((n,bool(c))); print(f"[{'PASS' if c else 'FAIL'}] {n}")
def req(b,p,m='GET',body=None,key=None):
 h={'Content-Type':'application/json'}; data=json.dumps(body).encode() if body is not None else None
 if key:h['X-Arbiter-Key']=key
 with urllib.request.urlopen(urllib.request.Request(b+p,data=data,headers=h,method=m),timeout=10) as r:return json.loads(r.read())
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--base-url',default='http://127.0.0.1:8000');ap.add_argument('--api-key');a=ap.parse_args()
 p=req(a.base_url,'/api/operations/posture',key=a.api_key)
 chk('operations posture loads',p.get('version')=='0.20.0');chk('required dependencies represented',len(p.get('dependencies',[]))>=2);chk('database dependency healthy',any(d.get('name')=='database' and d.get('status')=='healthy' for d in p['dependencies']));chk('audit chain dependency healthy',any(d.get('name')=='audit_chain' and d.get('status')=='healthy' for d in p['dependencies']));chk('backpressure state declared',p.get('backpressure') in {'NORMAL','WARN','BLOCK'});chk('rate limiting declared',p.get('rate_limiting')=='sliding-window-admission');chk('external observability requirement explicit',p.get('external_observability_required_for_production') is True)
 st=req(a.base_url,'/api/operations/self-test','POST',{},a.api_key);chk('resilience self-test passes',st.get('ok') is True);chk('self-test settlement authority false',st.get('settlement_authority') is False);chk('self-test admission succeeds',st.get('admission',{}).get('admitted') is True);chk('recovery drills pass',all(d.get('result')=='PASS' for d in st.get('drills',[])));chk('incident lifecycle closes',st.get('incident',{}).get('status')=='closed')
 inc=req(a.base_url,'/api/operations/incidents','POST',{'severity':'SEV3','title':'Gate synthetic incident','details':{'synthetic':True}},a.api_key)['incident'];chk('incident can be opened',inc.get('status')=='open'); lis=req(a.base_url,'/api/operations/incidents',key=a.api_key)['incidents'];chk('incident registry is queryable',any(i.get('incident_id')==inc.get('incident_id') for i in lis));cl=req(a.base_url,f"/api/operations/incidents/{inc['incident_id']}/close",'POST',{},a.api_key)['incident'];chk('incident can be closed',cl.get('status')=='closed')
 dr=req(a.base_url,'/api/operations/recovery-drills','POST',{'drill_type':'queue-recovery'},a.api_key)['drill'];chk('queue recovery drill executes',dr.get('result')=='PASS');chk('drill has deterministic result hash',str(dr.get('result_hash','')).startswith('sha256:'));chk('drill settlement authority false',dr.get('settlement_authority') is False)
 dev=req(a.base_url,'/api/developer',key=a.api_key);chk('developer manifest exposes resilience',dev.get('operations_resilience',{}).get('version')=='0.20.0');infra=req(a.base_url,'/api/infrastructure',key=a.api_key);chk('infrastructure exposes operations',infra.get('operations_resilience',{}).get('version')=='0.20.0');chk('health reports v0.20+',req(a.base_url,'/api/health',key=a.api_key).get('version','')>='0.20.0');chk('audit chain remains valid',req(a.base_url,'/api/audit?limit=1',key=a.api_key).get('chain',{}).get('ok') is True)
 total=len(checks);passed=sum(v for _,v in checks);print('\n'+'='*64);print(f'RESULT: {passed}/{total} checks passed; {total-passed} failed');
 if passed!=total:raise SystemExit(1)
 print('OPERATIONS & RESILIENCE GATE: PASS')
if __name__=='__main__':main()
