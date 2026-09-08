#!/usr/bin/env python3
import argparse,json,urllib.request,hashlib
checks=[]
def chk(n,c):checks.append((n,bool(c)));print(f"[{'PASS' if c else 'FAIL'}] {n}")
def req(b,p,m='GET',body=None,key=None):
 h={'Content-Type':'application/json'};data=json.dumps(body).encode() if body is not None else None
 if key:h['X-Arbiter-Key']=key
 with urllib.request.urlopen(urllib.request.Request(b+p,data=data,headers=h,method=m),timeout=15) as r:return json.loads(r.read())
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--base-url',default='http://127.0.0.1:8000');ap.add_argument('--api-key');a=ap.parse_args()
 p=req(a.base_url,'/api/external-assurance/posture',key=a.api_key);chk('external assurance posture loads',p.get('version')=='0.24.0');chk('external assurance does not self-certify',p.get('production_settlement_certified') is False);chk('external assurance is incomplete without independent evidence',p.get('external_assurance_complete') is False);chk('security review remains a missing evidence class','security_architecture_review' in p.get('missing_independent_evidence',[]))
 st=req(a.base_url,'/api/external-assurance/self-test','POST',{},a.api_key);chk('external assurance self-test passes',st.get('ok') is True);art=st.get('artifact',{});chk('self-test artifact is explicitly non-independent',art.get('independent') is False);chk('self-test evidence digest is SHA-256 shaped',len(str(art.get('evidence_sha256','')))==64)
 digest=hashlib.sha256(b'gate-penetration-test-report').hexdigest();body={'artifact_type':'penetration_test','provider':'Synthetic Gate Reviewer','performed_at':'2026-09-08T00:00:00Z','result':'PASS','scope':{'synthetic_gate':True},'evidence_uri':'synthetic://gate/pen-test','evidence_sha256':digest,'independent':True,'metadata':{'gate':True}};rec=req(a.base_url,'/api/external-assurance','POST',body,a.api_key)['artifact'];chk('independent PASS artifact can be registered',rec.get('result')=='PASS');chk('artifact type is preserved',rec.get('artifact_type')=='penetration_test');chk('reviewer/provider identity is preserved',rec.get('provider')=='Synthetic Gate Reviewer');chk('independent flag is preserved',rec.get('independent') is True)
 ls=req(a.base_url,'/api/external-assurance',key=a.api_key).get('artifacts',[]);chk('external assurance registry is queryable',any(x.get('artifact_id')==rec.get('artifact_id') for x in ls));after=req(a.base_url,'/api/external-assurance/posture',key=a.api_key);chk('passed evidence updates posture','penetration_test' in after.get('independent_passed',[]));chk('one artifact does not complete assurance',after.get('external_assurance_complete') is False);chk('production certification remains false after evidence registration',after.get('production_settlement_certified') is False)
 dev=req(a.base_url,'/api/developer',key=a.api_key);chk('developer manifest exposes external assurance',dev.get('external_assurance',{}).get('version')=='0.24.0');infra=req(a.base_url,'/api/infrastructure',key=a.api_key);chk('infrastructure exposes external assurance',infra.get('external_assurance',{}).get('version')=='0.24.0');aud=req(a.base_url,'/api/audit?limit=1',key=a.api_key);chk('audit chain remains valid',aud.get('chain',{}).get('ok') is True)
 total=len(checks);passed=sum(v for _,v in checks);print('\n'+'='*64);print(f'RESULT: {passed}/{total} checks passed; {total-passed} failed');
 if passed!=total:raise SystemExit(1)
 print('EXTERNAL ASSURANCE GATE: PASS')
if __name__=='__main__':main()
