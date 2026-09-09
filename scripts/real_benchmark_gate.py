#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app import compiler, engine, policy, semantic_contract
from app.real_benchmark.collectors import normalize_kalshi_market, normalize_polymarket_market
from app.real_benchmark.dataset import freeze_candidates, stratified_select, verify_dataset
from app.real_benchmark.hashing import read_jsonl, sha256_text, canonical_json
from app.real_benchmark.report import score_run
from app.real_benchmark.runner import run_blind, verify_prediction_run

checks: list[tuple[str, bool]] = []

def chk(name: str, cond) -> None:
    ok = bool(cond)
    checks.append((name, ok))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}")


def api_get(base: str, path: str) -> dict:
    with urllib.request.urlopen(base + path, timeout=10) as r:
        return json.loads(r.read())


def candidates() -> list[dict]:
    rows=[]
    for i in range(8):
        venue = "kalshi" if i % 2 == 0 else "polymarket"
        category = ["economics", "weather", "politics", "sports"][i % 4]
        row = {
            "case_id": f"fixture-{i+1}",
            "venue": venue,
            "external_market_id": f"MKT-{i+1}",
            "event_id": f"EVT-{i+1}",
            "title": f"Will the official value be above {10+i} on September {10+i}, 2026?",
            "rules": f"This fixture resolves YES if the official published value is above {10+i} on September {10+i}, 2026 at 12:00 UTC. Official results govern.",
            "known_outcome": "YES" if i % 2 == 0 else "NO",
            "settlement_value": str(11+i),
            "resolution_source": "Official results",
            "category": category,
            "opened_at": "2026-08-01T00:00:00Z",
            "closed_at": "2026-09-30T00:00:00Z",
            "settled_at": "2026-10-01T00:00:00Z",
            "source_url": f"https://example.test/{venue}/MKT-{i+1}",
            "collected_at": "2026-10-02T00:00:00Z",
            "raw_sha256": sha256_text(canonical_json({"i":i,"venue":venue})),
            "metadata": {"fixture": True},
            "gold_status": "REVIEW",  # fixture scoring coverage only; not a product claim
            "gold_unresolved_fields": ["source.authority"],
        }
        if i == 0:
            row["rules"] = "This fixture resolves YES if the Bureau of Labor Statistics reports CPI above 10 on September 10, 2026 at 12:00 UTC."
            row["resolution_source"] = "U.S. Bureau of Labor Statistics"
            row["gold_status"] = "READY"
            row["gold_unresolved_fields"] = []
            row["benchmark_evidence"] = {
                "observed_value": 11,
                "unit": "index-points",
                "authority": "AUTH-BLS-CPI",
                "source_url": "https://example.test/evidence/bls-cpi",
                "retrieved_at": "2026-10-02T00:00:00Z",
                "raw_sha256": sha256_text(canonical_json({"evidence": "fixture-1", "value": 11})),
            }
        rows.append(row)
    return rows


def main() -> None:
    ap=argparse.ArgumentParser(); ap.add_argument('--base-url',default='http://127.0.0.1:8000'); ap.add_argument('--api-key'); args=ap.parse_args()
    try:
        posture=api_get(args.base_url,'/api/real-benchmark')
        chk('v0.27 benchmark posture endpoint loads', posture.get('version')=='0.27.0')
        chk('real holdout target is explicit', posture.get('target_cases')==75)
        chk('production certification remains false', posture.get('production_settlement_certified') is False)
        chk('holdout tuning is prohibited', posture.get('tune_on_holdout') is False)
    except Exception as exc:
        print('API posture check failed:',exc)
        for name in ('v0.27 benchmark posture endpoint loads','real holdout target is explicit','production certification remains false','holdout tuning is prohibited'): chk(name,False)

    # Collector normalizers are exercised without network.
    kraw={"ticker":"KTEST","event_ticker":"EV","title":"Will CPI exceed 3%?","rules_primary":"Resolves YES if the Bureau of Labor Statistics reports CPI above 3.0% on September 11, 2026 at 08:30 EDT. The first published release controls.","rules_secondary":"Official BLS data governs.","result":"yes","settlement_ts":"2026-09-11T13:00:00Z","market_type":"binary"}
    k=normalize_kalshi_market(kraw,'https://example.test/kalshi')
    chk('Kalshi settled binary normalizes', bool(k and k.get('known_outcome')=='YES'))
    chk('Kalshi raw source is hash pinned', bool(k and str(k.get('raw_sha256','')).startswith('sha256:')))
    praw={"id":"123","question":"Will official total exceed 10?","description":"This market resolves YES if official results show a total above 10 by September 12, 2026 at 12:00 UTC.","resolutionSource":"Official results","outcomes":"[\"Yes\",\"No\"]","outcomePrices":"[\"1\",\"0\"]","closed":True,"umaResolutionStatus":"resolved","closedTime":"2026-09-12T13:00:00Z"}
    p=normalize_polymarket_market(praw,'https://example.test/poly')
    chk('Polymarket resolved binary normalizes', bool(p and p.get('known_outcome')=='YES'))
    chk('Polymarket nonterminal price is rejected', normalize_polymarket_market({**praw,"outcomePrices":"[\"0.7\",\"0.3\"]"},'https://example.test/poly') is None)

    with tempfile.TemporaryDirectory(prefix='arbiter-real-bench-') as td:
        root=Path(td)
        d1=root/'holdout1'
        frozen=freeze_candidates(candidates(),d1,target=6,seed='fixed-seed')
        chk('holdout freezes requested case count', frozen.get('case_count')==6)
        chk('holdout aggregate hash is pinned', str(frozen.get('hashes',{}).get('dataset_sha256','')).startswith('sha256:'))
        chk('labels are declared separated', frozen.get('benchmark_controls',{}).get('labels_separated_from_inputs') is True)
        chk('frozen evidence is separately hash pinned', str(frozen.get('hashes',{}).get('evidence_sha256','')).startswith('sha256:'))
        verify=verify_dataset(d1)
        chk('fresh frozen holdout verifies', verify.get('ok') is True)
        contracts=read_jsonl(d1/'contracts.jsonl')
        labels=read_jsonl(d1/'labels.jsonl')
        evidence=read_jsonl(d1/'evidence.jsonl')
        chk('blind inputs contain no known_outcome', all('known_outcome' not in x for x in contracts))
        chk('evidence contains no venue outcome labels', all('known_outcome' not in x and 'settlement_value' not in x for x in evidence))
        chk('labels retain frozen outcomes', all(x.get('known_outcome') in {'YES','NO'} for x in labels))
        chk('contract and label case IDs align', [x['case_id'] for x in contracts]==[x['case_id'] for x in labels])
        # deterministic selection
        ids1=[x['case_id'] for x in stratified_select(candidates(),6,'fixed-seed')]
        ids2=[x['case_id'] for x in stratified_select(candidates(),6,'fixed-seed')]
        chk('stratified selection is deterministic', ids1==ids2)
        try:
            freeze_candidates(candidates(),d1,target=6,seed='fixed-seed')
            overwrite_blocked=False
        except FileExistsError:
            overwrite_blocked=True
        chk('frozen dataset overwrite is blocked', overwrite_blocked)

        authorities=[
            {"authority_id":"AUTH-BLS-CPI","name":"U.S. Bureau of Labor Statistics","organization":"Bureau of Labor Statistics"},
            {"authority_id":"AUTH-FED-FOMC","name":"Federal Reserve","organization":"Federal Reserve"},
            {"authority_id":"AUTH-NOAA-WEATHER","name":"NOAA","organization":"National Weather Service"},
        ]
        run_dir=root/'run'
        blind=run_blind(d1,run_dir,engine_module=engine,compiler_module=compiler,semantic_module=semantic_contract,policy=policy.load_policy(),authorities=authorities,run_name='gate')
        chk('blind run covers every frozen case', blind.get('manifest',{}).get('case_count')==6)
        chk('blind run attests labels not loaded', blind.get('manifest',{}).get('labels_loaded_during_run') is False)
        chk('blind predictions are hash pinned', str(blind.get('manifest',{}).get('predictions_sha256','')).startswith('sha256:'))
        chk('blind run pins the frozen evidence hash', blind.get('manifest',{}).get('evidence_sha256')==frozen.get('hashes',{}).get('evidence_sha256'))
        preds=read_jsonl(run_dir/'predictions.jsonl')
        chk('blind prediction rows contain no venue labels', all('known_outcome' not in x and 'settlement_value' not in x for x in preds))
        p1=next((x for x in preds if x.get('case_id')=='fixture-1'),{})
        chk('READY numeric contract resolves from frozen evidence', p1.get('predicted_outcome')=='YES' and p1.get('resolution_method')=='numeric-threshold-v1')
        chk('non-READY contracts abstain with HOLD', all(x.get('predicted_outcome')=='HOLD' for x in preds if x.get('case_id')!='fixture-1'))
        rverify=verify_prediction_run(d1,run_dir)
        chk('prediction run verifies against dataset hash', rverify.get('ok') is True)
        report=score_run(d1,run_dir,root/'report')
        chk('post-run report is hash pinned', str(report.get('report',{}).get('report_sha256','')).startswith('sha256:'))
        oq=report.get('report',{}).get('metrics',{}).get('outcome_metrics',{})
        chk('report scores only evidence-backed deterministic outcomes', oq.get('scored_cases')==1 and oq.get('agreement')==1.0)
        chk('report exposes governed hold rate', oq.get('held_cases')==5 and oq.get('hold_rate') is not None)
        chk('report exposes gold coverage separately', report.get('report',{}).get('metrics',{}).get('gold_contract_quality',{}).get('gold_status_coverage')==6)

        # Tamper detection after a completed benchmark.
        with (d1/'labels.jsonl').open('a',encoding='utf-8') as f: f.write('{"tamper":true}\n')
        tampered=verify_dataset(d1)
        chk('label tampering invalidates dataset', tampered.get('ok') is False and any('hash mismatch' in x for x in tampered.get('errors',[])))

    total=len(checks); passed=sum(v for _,v in checks)
    print('\n'+'='*64); print(f'RESULT: {passed}/{total} checks passed; {total-passed} failed')
    if passed!=total: raise SystemExit(1)
    print('REAL-WORLD BENCHMARK GATE: PASS')

if __name__=='__main__': main()
