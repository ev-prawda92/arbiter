#!/usr/bin/env python3
"""Simple dependency-light HTTP load probe for deployed Arbiter environments.

This is not a substitute for k6/Locust/Gatling, but gives a reproducible baseline and
JSON evidence artifact that can be registered in the resilience/assurance registry.
"""
import argparse, concurrent.futures, hashlib, json, statistics, time, urllib.request
from datetime import datetime, timezone

def once(url, headers, timeout):
    t=time.perf_counter(); code=None; err=None
    try:
        req=urllib.request.Request(url,headers=headers)
        with urllib.request.urlopen(req,timeout=timeout) as r:
            code=r.status; r.read(1)
    except Exception as e: err=type(e).__name__
    return {"latency_ms":(time.perf_counter()-t)*1000,"status":code,"error":err}

def pct(xs,p):
    if not xs:return None
    ys=sorted(xs);i=min(len(ys)-1,max(0,int(round((len(ys)-1)*p))));return round(ys[i],2)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--base-url',required=True);ap.add_argument('--path',default='/api/readiness');ap.add_argument('--requests',type=int,default=200);ap.add_argument('--concurrency',type=int,default=20);ap.add_argument('--api-key');ap.add_argument('--timeout',type=float,default=10);ap.add_argument('--out',default='arbiter_load_result.json');a=ap.parse_args()
    headers={};
    if a.api_key:headers['X-Arbiter-Key']=a.api_key
    n=max(1,a.requests);c=max(1,min(a.concurrency,n));started=datetime.now(timezone.utc).isoformat();t0=time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=c) as ex: results=list(ex.map(lambda _:once(a.base_url.rstrip('/')+a.path,headers,a.timeout),range(n)))
    elapsed=time.perf_counter()-t0;lats=[r['latency_ms'] for r in results];ok=[r for r in results if r['status'] and 200<=r['status']<300]
    report={"tool":"arbiter-load-probe-v1","base_url":a.base_url,"path":a.path,"requests":n,"concurrency":c,"started_at":started,"elapsed_seconds":round(elapsed,3),"requests_per_second":round(n/max(elapsed,1e-9),2),"success_count":len(ok),"error_count":n-len(ok),"success_rate":round(len(ok)/n,4),"latency_ms":{"min":round(min(lats),2),"median":round(statistics.median(lats),2),"p95":pct(lats,.95),"p99":pct(lats,.99),"max":round(max(lats),2)},"errors":{e:sum(1 for r in results if r['error']==e) for e in sorted({r['error'] for r in results if r['error']})}}
    payload=json.dumps(report,sort_keys=True,separators=(',',':')).encode();report['evidence_sha256']=hashlib.sha256(payload).hexdigest();open(a.out,'w').write(json.dumps(report,indent=2,sort_keys=True)+'\n');print(json.dumps(report,indent=2,sort_keys=True))
if __name__=='__main__':main()
