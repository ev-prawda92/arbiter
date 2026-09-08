#!/usr/bin/env python3
import argparse,json,urllib.request,urllib.error
checks=[]
def chk(name,cond):checks.append((name,bool(cond)));print(f"[{'PASS' if cond else 'FAIL'}] {name}")
def req(base,path,method='GET',body=None,key=None,expect=None):
 data=json.dumps(body).encode() if body is not None else None;h={'Content-Type':'application/json'}
 if key:h['X-Arbiter-Key']=key
 r=urllib.request.Request(base+path,data=data,headers=h,method=method)
 try:
  with urllib.request.urlopen(r,timeout=20) as x:return x.status,json.loads(x.read().decode())
 except urllib.error.HTTPError as e:
  payload=json.loads(e.read() or b'{}')
  if expect and e.code==expect:return e.code,payload
  raise

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--base-url',default='http://127.0.0.1:8000');ap.add_argument('--api-key');a=ap.parse_args()
 _,p=req(a.base_url,'/api/reference-exchange',key=a.api_key);chk('reference exchange posture loads',p.get('version')=='0.26.0');chk('reference exchange is sandbox mode',p.get('mode')=='reference-sandbox');chk('play money only is explicit',p.get('play_money_only') is True);chk('real-money custody is disabled',p.get('real_money_custody') is False);chk('sandbox matching engine is declared',isinstance(p.get('matching_engine'),str) and 'matcher' in p.get('matching_engine'))
 _,st=req(a.base_url,'/api/reference-exchange/self-test','POST',{},a.api_key);chk('end-to-end self-test completes',st.get('ok') is True);chk('self-test has zero real-money path',st.get('zero_real_money') is True);chk('self-test returns market identity',bool(st.get('market_id')));chk('self-test either exercises matching or safely holds',st.get('matching_exercised') is True or st.get('held_safely') is True)
 title='Will U.S. CPI be above 3.0% on September 11, 2026?';rules='This market resolves YES if the U.S. Bureau of Labor Statistics reports CPI above 3.0% on September 11, 2026 at 08:30 EDT. The first published release controls.'
 _,mr=req(a.base_url,'/api/reference-exchange/markets','POST',{'title':title,'rules':rules},a.api_key);m=mr['market'];chk('precise reference contract opens for sandbox trading',m.get('state')=='OPEN')
 _,ar=req(a.base_url,'/api/reference-exchange/accounts','POST',{'display_name':'Gate YES Trader'},a.api_key);yes=ar['account'];_,br=req(a.base_url,'/api/reference-exchange/accounts','POST',{'display_name':'Gate NO Trader'},a.api_key);no=br['account'];chk('YES account receives play-money balance',yes.get('cash')==10000.0);chk('NO account receives play-money balance',no.get('cash')==10000.0)
 _,o1=req(a.base_url,'/api/reference-exchange/orders','POST',{'market_id':m['market_id'],'account_id':yes['account_id'],'side':'YES','quantity':5,'limit_price':0.62},a.api_key);chk('first limit order rests without counterparty',o1.get('order',{}).get('state')=='OPEN' and len(o1.get('trades',[]))==0)
 _,o2=req(a.base_url,'/api/reference-exchange/orders','POST',{'market_id':m['market_id'],'account_id':no['account_id'],'side':'NO','quantity':5,'limit_price':0.40},a.api_key);trades=o2.get('trades',[]);chk('complementary orders match',len(trades)==1);trade=trades[0] if trades else {};chk('matched trade quantity is correct',trade.get('quantity')==5);chk('YES/NO execution prices sum to one',abs(float(trade.get('yes_price',0))+float(trade.get('no_price',0))-1.0)<1e-9)
 _,book=req(a.base_url,f"/api/reference-exchange/markets/{m['market_id']}/order-book",key=a.api_key);chk('fully filled orders leave empty book',len(book.get('yes',[]))==0 and len(book.get('no',[]))==0)
 _,md=req(a.base_url,f"/api/reference-exchange/markets/{m['market_id']}",key=a.api_key);market=md['market'];chk('matched trade creates two positions',len(market.get('positions',[]))==2);chk('trade ledger is attached to market',len(market.get('trades',[]))==1)
 _,sett=req(a.base_url,f"/api/reference-exchange/markets/{m['market_id']}/resolve",'POST',{'outcome':'YES','evidence_summary':{'authority':'BLS','gate':True}},a.api_key);s=sett['settlement'];chk('sandbox settlement is hash pinned',str(s.get('settlement_hash','')).startswith('sha256:'))
 _,final=req(a.base_url,f"/api/reference-exchange/markets/{m['market_id']}",key=a.api_key);chk('market enters SETTLED state',final['market'].get('state')=='SETTLED')
 _,ya=req(a.base_url,f"/api/reference-exchange/accounts/{yes['account_id']}",key=a.api_key);_,na=req(a.base_url,f"/api/reference-exchange/accounts/{no['account_id']}",key=a.api_key);total=float(ya['account']['cash'])+float(na['account']['cash']);chk('play-money cash is conserved across matched settlement',abs(total-20000.0)<1e-6)
 code,_=req(a.base_url,f"/api/reference-exchange/markets/{m['market_id']}/resolve",'POST',{'outcome':'YES','evidence_summary':{}},a.api_key,expect=422);chk('duplicate settlement attempt is rejected',code==422)
 _,amb=req(a.base_url,'/api/reference-exchange/markets','POST',{'title':'Will inflation be above 3%?','rules':'Resolve YES if inflation is above 3%.'},a.api_key);chk('ambiguous contract is safely held',amb['market'].get('state')=='HELD')
 _,dev=req(a.base_url,'/api/developer',key=a.api_key);chk('developer manifest exposes reference exchange v2',dev.get('reference_exchange',{}).get('version')=='0.26.0' and dev.get('reference_exchange',{}).get('sandbox_matching_engine') is True)
 _,aud=req(a.base_url,'/api/audit?limit=1',key=a.api_key);chk('audit chain remains valid',aud.get('chain',{}).get('ok') is True)
 total=len(checks);passed=sum(v for _,v in checks);print('\n'+'='*64);print(f'RESULT: {passed}/{total} checks passed; {total-passed} failed')
 if passed!=total:raise SystemExit(1)
 print('REFERENCE EXCHANGE GATE: PASS')
if __name__=='__main__':main()
