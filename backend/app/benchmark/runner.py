from __future__ import annotations
import json
from pathlib import Path
from .mutations import clean_parent, GENERATORS
from .validators import validate
from .metrics import summarize

def _flat_flags(report: dict) -> str:
    flags=[]
    for lever in ("source","timing","definition"):
        flags.extend(report.get("levers",{}).get(lever,{}).get("flags",[]))
    return " ".join(flags).lower()

def _scores(report: dict) -> dict[str,int]:
    return {lever: report.get("levers",{}).get(lever,{}).get("score",0)
            for lever in ("source","timing","definition")}

def _infer_detected(expected: str, report: dict) -> bool:
    flags = _flat_flags(report)
    terms = {
        "SOURCE_MISSING":["no clearly authoritative source", "settlement source not explicitly designated"],
        "SOURCE_VAGUE":["vague / non-authoritative reporting"],
        "TIMEZONE_MISSING":["no timezone specified"],
        "SUBJECTIVE_TERM":["interpretive term"],
    }.get(expected, [])
    return any(t in flags for t in terms)

def _market(case):
    return {
        "ticker": case.id,
        "title": case.question,
        "subtitle": "",
        "category": case.metadata.get("domain","benchmark"),
        "rules_primary": case.criteria,
        "rules_secondary": "",
        "open_interest": 0,
    }

def run(engine_module, policy: dict, dataset_path: str | Path) -> dict:
    data = json.loads(Path(dataset_path).read_text())
    parents = {}
    cases = []
    for raw in data["cases"]:
        parent = clean_parent(raw)
        cases.append(parent)
        parents[parent.id] = engine_module.analyze(_market(parent), policy)
        for gen in GENERATORS:
            c = gen(raw)
            if c is not None:
                cases.append(c)

    rows=[]
    for case in cases:
        ok,note = validate(case)
        report = parents[case.id] if case.expected.failure_mode == "NONE" else engine_module.analyze(_market(case), policy)
        expected_lever = case.expected.lever
        if case.expected.failure_mode == "NONE":
            detected=False
            deltas={"source":0,"timing":0,"definition":0}
            lever_correct=True
        else:
            detected=_infer_detected(case.expected.failure_mode, report)
            parent_scores=_scores(parents[case.parent_id])
            mutation_scores=_scores(report)
            deltas={k: mutation_scores[k]-parent_scores[k] for k in parent_scores}
            max_delta=max(deltas.values())
            # ties count: a planted defect can legitimately raise more than one coupled lever.
            lever_correct=deltas.get(expected_lever, -999) == max_delta and max_delta > 0
        flags=[]
        for lever in ("source","timing","definition"):
            flags.extend(report.get("levers",{}).get(lever,{}).get("flags",[]))
        rows.append({
            "id":case.id,"parent_id":case.parent_id,"kind":case.kind,
            "expected_lever":expected_lever,"expected_failure_mode":case.expected.failure_mode,
            "validator_pass":ok,"validator_note":note,
            "actual_verdict":report.get("verdict",{}).get("label"),
            "actual_composite":report.get("composite"),
            "lever_scores":_scores(report),"lever_deltas_vs_parent":deltas,
            "detected":detected,"lever_correct":lever_correct,"flags":flags,
        })
    return {"benchmark":"ARB-SYN-v0.1","metrics":summarize(rows),"cases":rows}
