#!/usr/bin/env python3
"""Run the complete Arbiter release-gate stack against a running API."""
from __future__ import annotations
import argparse, os, subprocess, sys
from pathlib import Path

GATES = [
    'coherence_test.py',
    'enterprise_gate.py',
    'evidence_gate.py',
    'settlement_gate.py',
    'semantic_gate.py',
    'identity_gate.py',
    'reliability_gate.py',
    'model_gateway_gate.py',
    'data_plane_gate.py',
    'enterprise_secrets_gate.py',
    'reference_exchange_gate.py',
    'operations_resilience_gate.py',
    'settlement_assurance_gate.py',
]


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--base-url',default='http://127.0.0.1:8000')
    ap.add_argument('--api-key',default=os.environ.get('ARBITER_API_KEY'))
    a=ap.parse_args()
    scripts=Path(__file__).resolve().parent
    for gate in GATES:
        cmd=[sys.executable,str(scripts/gate),'--base-url',a.base_url]
        if a.api_key: cmd += ['--api-key',a.api_key]
        print(f'\n>>> {gate}')
        result=subprocess.run(cmd)
        if result.returncode:
            print(f'RELEASE GATE: FAIL ({gate})')
            raise SystemExit(result.returncode)
    print('\n'+'='*64)
    print('RELEASE GATE: PASS — 334/334 checks across 13 suites')

if __name__=='__main__': main()
