from __future__ import annotations
from collections import Counter

def summarize(rows: list[dict]) -> dict:
    total = len(rows)
    valid = [r for r in rows if r["validator_pass"]]
    mutations = [r for r in valid if r["expected_failure_mode"] != "NONE"]
    clean = [r for r in valid if r["expected_failure_mode"] == "NONE"]
    detected = [r for r in mutations if r["detected"]]
    lever_ok = [r for r in detected if r["lever_correct"]]
    false_positive = [r for r in clean if r["actual_verdict"] != "AUTO-RESOLVE"]
    return {
        "total_cases": total,
        "valid_cases": len(valid),
        "mutation_cases": len(mutations),
        "clean_cases": len(clean),
        "defect_detection_rate": round(len(detected)/len(mutations),4) if mutations else None,
        "correct_lever_rate_on_detected": round(len(lever_ok)/len(detected),4) if detected else None,
        "clean_auto_resolve_rate": round((len(clean)-len(false_positive))/len(clean),4) if clean else None,
        "clean_false_positive_rate": round(len(false_positive)/len(clean),4) if clean else None,
        "verdicts": dict(Counter(r["actual_verdict"] for r in valid)),
        "by_expected_failure_mode": {
            fm: {
                "n": len(group := [r for r in mutations if r["expected_failure_mode"] == fm]),
                "detected": sum(1 for r in group if r["detected"]),
            }
            for fm in sorted({r["expected_failure_mode"] for r in mutations})
        }
    }
