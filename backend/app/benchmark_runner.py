"""Arbiter benchmark runner.

Runs a labeled benchmark dataset against the deterministic resolution-integrity engine
without mutating engine policy. Intended for reproducible baseline and regression runs.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from pathlib import Path

from app.engine import analyze
from app.policy import load_policy


def _market_from_clean_case(case: dict) -> dict:
    """Adapt ARB-GOLD-CLEAN-v0.1 structured fields to the engine market schema.

    NOTE: v0.1 stores structured paraphrases, not verbatim exchange rule text.
    Future gold datasets should include `rules_verbatim` and this adapter should prefer it.
    """
    rules = case.get("rules_verbatim") or " ".join(
        part for part in [
            case.get("definition", ""),
            case.get("timing", ""),
            f"Source: {case.get('source', '')}" if case.get("source") else "",
            case.get("revision_rule", ""),
        ] if part
    )
    return {
        "ticker": case["id"],
        "title": case.get("title", ""),
        "subtitle": case.get("subtitle", ""),
        "category": case.get("domain", "uncategorized"),
        "rules_primary": rules,
        "rules_secondary": "",
        "open_interest": 0,
    }


def run(dataset_path: str | Path) -> dict:
    dataset_path = Path(dataset_path)
    data = json.loads(dataset_path.read_text())
    policy = load_policy()
    rows = []

    for case in data["cases"]:
        report = analyze(_market_from_clean_case(case), policy)
        expected = case.get("gold_status", "accepted")
        gold = "clean" if expected == "accepted" else case.get("gold", "unknown")
        passed = report["verdict"]["key"] == "clean" if gold == "clean" else None
        rows.append({
            "id": case["id"],
            "venue": case.get("venue"),
            "domain": case.get("domain"),
            "title": case.get("title"),
            "gold": gold,
            "verdict": report["verdict"]["key"],
            "verdict_label": report["verdict"]["label"],
            "composite": report["composite"],
            "source_score": report["levers"]["source"]["score"],
            "timing_score": report["levers"]["timing"]["score"],
            "definition_score": report["levers"]["definition"]["score"],
            "source_flags": report["levers"]["source"]["flags"],
            "timing_flags": report["levers"]["timing"]["flags"],
            "definition_flags": report["levers"]["definition"]["flags"],
            "pass": passed,
        })

    clean_rows = [r for r in rows if r["gold"] == "clean"]
    n = len(clean_rows)
    auto = sum(r["verdict"] == "clean" for r in clean_rows)
    monitored = sum(r["verdict"] == "monitored" for r in clean_rows)
    hold = sum(r["verdict"] == "review" for r in clean_rows)

    summary = {
        "benchmark": data.get("metadata", {}).get("dataset", dataset_path.stem),
        "engine": "Arbiter v0.4",
        "policy_version": policy["version"],
        "n_clean_cases": n,
        "auto_resolve": auto,
        "monitored": monitored,
        "hold_review": hold,
        "clean_recognition_rate": round(auto / n, 4) if n else None,
        "false_nonclean_rate": round((n - auto) / n, 4) if n else None,
        "false_hold_rate": round(hold / n, 4) if n else None,
        "avg_composite": round(statistics.mean(r["composite"] for r in clean_rows), 2) if n else None,
        "avg_source": round(statistics.mean(r["source_score"] for r in clean_rows), 2) if n else None,
        "avg_timing": round(statistics.mean(r["timing_score"] for r in clean_rows), 2) if n else None,
        "avg_definition": round(statistics.mean(r["definition_score"] for r in clean_rows), 2) if n else None,
        "caveat": "ARB-GOLD-CLEAN-v0.1 uses structured paraphrases; external benchmark runs should use preserved verbatim market rules.",
    }
    return {"summary": summary, "cases": rows}


def save(result: dict, out_prefix: str | Path) -> tuple[Path, Path]:
    out_prefix = Path(out_prefix)
    out_prefix.parent.mkdir(parents=True, exist_ok=True)
    json_path = out_prefix.with_suffix(".json")
    csv_path = out_prefix.with_suffix(".csv")
    json_path.write_text(json.dumps(result, indent=2))
    fields = ["id","venue","domain","title","gold","verdict","verdict_label","composite","source_score","timing_score","definition_score","source_flags","timing_flags","definition_flags","pass"]
    with csv_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for row in result["cases"]:
            row = row.copy()
            for k in ("source_flags","timing_flags","definition_flags"):
                row[k] = " | ".join(row[k])
            w.writerow({k: row.get(k) for k in fields})
    return json_path, csv_path


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("dataset")
    p.add_argument("--out", default="backend/data/benchmark_runs/latest")
    args = p.parse_args()
    result = run(args.dataset)
    paths = save(result, args.out)
    print(json.dumps(result["summary"], indent=2))
    print("Saved:", *paths)


if __name__ == "__main__":
    main()
