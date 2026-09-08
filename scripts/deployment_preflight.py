#!/usr/bin/env python3
"""Static + runtime preflight for Arbiter cloud deployment."""
import argparse, json, os, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app import deployment_readiness, production_data, enterprise, enterprise_secrets, identity_federation

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--json',action='store_true');a=ap.parse_args()
    p=deployment_readiness.posture(); findings=enterprise.configuration_findings()+production_data.configuration_findings()+enterprise_secrets.configuration_findings()+identity_federation.posture().get('findings',[])
    result={'artifacts_ok':p['deployment_iac_complete'],'environment':os.environ.get('ARBITER_ENV','development'),'findings':findings,'production_proven':False}
    if a.json: print(json.dumps(result,indent=2))
    else:
        print('Arbiter deployment preflight');print('IaC artifacts:', 'PASS' if result['artifacts_ok'] else 'FAIL');print('Runtime findings:',len(findings));[print(f"- {x['severity']} {x['code']}: {x['detail']}") for x in findings];print('Production proof: NOT YET')
    raise SystemExit(0 if result['artifacts_ok'] else 1)
if __name__=='__main__':main()
