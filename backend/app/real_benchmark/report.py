from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import REPORT_SCHEMA, BENCHMARK_VERSION
from .dataset import verify_dataset
from .hashing import canonical_json, read_jsonl, sha256_file, sha256_text
from .metrics import summarize
from .runner import verify_prediction_run


def score_run(dataset_dir: str | Path, run_dir: str | Path, report_dir: str | Path) -> dict[str, Any]:
    dcheck = verify_dataset(dataset_dir)
    rcheck = verify_prediction_run(dataset_dir, run_dir)
    if not dcheck["ok"]:
        raise ValueError("dataset verification failed: " + "; ".join(dcheck["errors"]))
    if not rcheck["ok"]:
        raise ValueError("prediction verification failed: " + "; ".join(rcheck["errors"]))
    root = Path(dataset_dir)
    run_root = Path(run_dir)
    manifest = dcheck["manifest"]
    labels = read_jsonl(root / manifest["files"]["labels"])
    predictions = read_jsonl(run_root / "predictions.jsonl")
    metrics = summarize(predictions, labels)
    report = {
        "schema": REPORT_SCHEMA,
        "benchmark_version": BENCHMARK_VERSION,
        "dataset": manifest.get("name"),
        "dataset_sha256": manifest["hashes"]["dataset_sha256"],
        "prediction_run_sha256": rcheck["run_manifest"].get("run_sha256"),
        "case_count": manifest.get("case_count"),
        "metrics": metrics,
        "claims": {
            "blind_contract_analysis": True,
            "labels_loaded_during_prediction": False,
            "production_settlement_certified": False,
            "independent_certification": False,
        },
        "limitations": [
            "A resolved exchange market proves the venue outcome, not that Arbiter independently reconstructed the evidence unless an evidence pack is supplied.",
            "Contract-quality accuracy metrics require separately frozen human or independent gold labels; absent labels are reported as missing coverage, not inferred.",
            "The holdout must not be used to tune Arbiter. Any fixes prompted by this report require evaluation on a future holdout version.",
        ],
    }
    report["report_sha256"] = sha256_text(canonical_json(report))
    out = Path(report_dir)
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / "benchmark_report.json"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path = out / "BENCHMARK_REPORT.md"
    md_path.write_text(render_markdown(report, manifest), encoding="utf-8")
    return {"report": report, "json_path": str(json_path), "markdown_path": str(md_path), "markdown_sha256": sha256_file(md_path)}


def _fmt_rate(value: Any) -> str:
    return "not yet scored" if value is None else f"{float(value)*100:.1f}%"


def render_markdown(report: dict[str, Any], dataset_manifest: dict[str, Any]) -> str:
    m = report["metrics"]
    oq = m["outcome_metrics"]
    g = m["gold_contract_quality"]
    top = "\n".join(f"- `{name}` — {count}" for name, count in m.get("top_unresolved_fields", [])[:10]) or "- none"
    venue_rows = "\n".join(f"- **{k}:** {v}" for k, v in sorted(m.get("venues", {}).items())) or "- none"
    return f"""# Arbiter Resolution Benchmark v0.1

**Software:** Arbiter v{BENCHMARK_VERSION}  
**Dataset:** {report['dataset']}  
**Cases:** {report['case_count']}  
**Dataset SHA-256:** `{report['dataset_sha256']}`  
**Blind run SHA-256:** `{report['prediction_run_sha256']}`  
**Report SHA-256:** `{report['report_sha256']}`

## Benchmark control

This report is produced from a frozen real-contract dataset. Contract inputs and outcome labels are stored in separate hash-pinned files. The blind runner reads `contracts.jsonl` plus the separately frozen `evidence.jsonl`; it never opens `labels.jsonl` during prediction. Labels are opened only after the prediction artifact itself is hash-pinned.

This is **not** independent certification and does **not** claim production settlement certification.

## Corpus

{venue_rows}

Compiler status distribution: `{json.dumps(m.get('compiler_statuses', {}), sort_keys=True)}`  
Engine verdict distribution: `{json.dumps(m.get('engine_verdicts', {}), sort_keys=True)}`

## Outcome resolution

- Frozen evidence coverage: **{_fmt_rate(oq.get('evidence_coverage'))}** ({oq.get('evidence_cases', 0)} cases)
- Deterministic YES/NO resolution coverage: **{_fmt_rate(oq.get('resolution_coverage'))}** ({oq.get('scored_cases', 0)} cases)
- Governed HOLD rate: **{_fmt_rate(oq.get('hold_rate'))}** ({oq.get('held_cases', 0)} cases)
- Outcome agreement where deterministically resolved: **{_fmt_rate(oq.get('agreement'))}**

Arbiter does not guess a market outcome when a benchmark evidence pack is absent. A venue's settled outcome is retained as the label, but it is not leaked into the blind prediction phase.

## Contract-quality gold labels

- Gold status coverage: **{g.get('gold_status_coverage', 0)} cases**
- READY / REVIEW / BLOCK accuracy: **{_fmt_rate(g.get('gold_status_accuracy'))}**
- False-hold rate on gold READY: **{_fmt_rate(g.get('false_hold_rate_on_gold_ready'))}**
- Ambiguity recall: **{_fmt_rate(g.get('ambiguity_recall'))}**
- Source agreement: **{_fmt_rate(g.get('source_agreement'))}**
- Timing agreement: **{_fmt_rate(g.get('timing_agreement'))}**
- Definition agreement: **{_fmt_rate(g.get('definition_agreement'))}**

Metrics without frozen gold coverage remain explicitly unscored rather than being manufactured from Arbiter's own output.

## Most common unresolved fields

{top}

## Dataset immutability

- Contracts SHA-256: `{dataset_manifest['hashes']['contracts_sha256']}`
- Labels SHA-256: `{dataset_manifest['hashes']['labels_sha256']}`
- Provenance SHA-256: `{dataset_manifest['hashes']['provenance_sha256']}`
- Evidence SHA-256: `{dataset_manifest['hashes']['evidence_sha256']}`
- Aggregate dataset SHA-256: `{dataset_manifest['hashes']['dataset_sha256']}`

## Interpretation

The first use of this benchmark is to answer two different questions without conflating them:

1. **How does Arbiter interpret and gate untouched real exchange contracts?** This can be measured immediately from the blind compiler/semantic outputs.
2. **Does Arbiter independently reproduce the final YES/NO outcome?** This is scored only when a source/evidence pack is frozen independently of the outcome label.

A failure is evidence, not a prompt to edit this holdout. Remediation should be developed against the existing development corpus and evaluated on a future frozen holdout.
"""
