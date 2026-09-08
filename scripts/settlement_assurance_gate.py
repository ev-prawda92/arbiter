#!/usr/bin/env python3
import argparse,json,urllib.request
checks=[]
def chk(n,c):checks.append((n,bool(c)));print(f"[{'PASS' if c else 'FAIL'}] {n}")
def req(b,p,m='GET',body=None,key=None):
 h={'Content-Type':'application/json'};data=json.dumps(body).encode() if body is not None else None
 if key:h['X-Arbiter-Key']=key
 with urllib.request.urlopen(urllib.request.Request(b+p,data=data,headers=h,method=m),timeout=15) as r:return json.loads(r.read())
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--base-url',default='http://127.0.0.1:8000');ap.add_argument('--api-key');a=ap.parse_args()
 p=req(a.base_url,'/api/assurance/posture',key=a.api_key);chk('assurance posture loads',p.get('version')=='0.21.0');chk('internal assurance harness declared',p.get('internal_assurance_harness') is True);chk('production certification remains false',p.get('production_settlement_certified') is False);chk('certification state is NOT_CERTIFIED',p.get('certification_state')=='NOT_CERTIFIED');chk('external security review remains explicit requirement','external_security_architecture_review' in p.get('requirements',{}));chk('penetration test remains explicit requirement','penetration_test' in p.get('requirements',{}));chk('real holdout remains explicit requirement','untouched_real_contract_holdout' in p.get('requirements',{}));chk('open certification blockers are exposed',len(p.get('open_certification_blockers',[]))>=3)
 st=req(a.base_url,'/api/assurance/self-test','POST',{},a.api_key);chk('assurance self-test passes',st.get('ok') is True);chk('self-test does not certify production',st.get('production_settlement_certified') is False);adv=st.get('adversarial',{});chk('adversarial suite passes',adv.get('status')=='PASS');chk('adversarial suite is hash pinned',str(adv.get('report_hash','')).startswith('sha256:'));chk('adversarial suite has five cases',adv.get('report',{}).get('case_count')==5);chk('all adversarial expectations match',adv.get('report',{}).get('failed')==0);chk('assurance explicitly not independent',adv.get('independent_certification') is False);h=st.get('holdout',{});chk('holdout fixture freezes labels',h.get('frozen') is True);chk('holdout dataset hash pinned',str(h.get('dataset_hash','')).startswith('sha256:'));chk('holdout evaluation hash pinned',str(st.get('holdout_evaluation',{}).get('report_hash','')).startswith('sha256:'))
 ls=req(a.base_url,'/api/assurance/holdouts',key=a.api_key)['datasets'];chk('holdout registry queryable',any(x.get('dataset_id')==h.get('dataset_id') for x in ls));dev=req(a.base_url,'/api/developer',key=a.api_key);chk('developer manifest exposes assurance',dev.get('settlement_assurance',{}).get('version')=='0.21.0');infra=req(a.base_url,'/api/infrastructure',key=a.api_key);chk('infrastructure exposes assurance',infra.get('settlement_assurance',{}).get('version')=='0.21.0');chk('health reports v0.21+',req(a.base_url,'/api/health',key=a.api_key).get('version','')>='0.21.0');chk('audit chain remains valid',req(a.base_url,'/api/audit?limit=1',key=a.api_key).get('chain',{}).get('ok') is True)
 total=len(checks);passed=sum(v for _,v in checks);print('\n'+'='*64);print(f'RESULT: {passed}/{total} checks passed; {total-passed} failed');
 if passed!=total:raise SystemExit(1)
 print('SETTLEMENT ASSURANCE GATE: PASS')
if __name__=='__main__':main()
