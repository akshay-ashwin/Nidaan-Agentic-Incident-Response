"""Aggregate per-run records into machine-readable results (counts with Wilson 95% CIs).

Record = {"arm", "scenario", "seed", "faults", "repeat", "run_id", "log_path", "metrics"} where
metrics = {"arm", "spec": {...}, "supplementary": {...}} (see evaluation/metrics.py).
Each summary has a "spec" block (SPEC §9) and a "supplementary" block (descriptive, not SPEC metrics).
Arms stay separate throughout. Fault types outside `known_types` are grouped as "held_out"
generically (no held-out ids are named here).
"""
from __future__ import annotations

import json
import os

from evaluation.metrics import DEFINITIONS
from evaluation.wilson import wilson
from settlesim.generator import DEV_FAULTS

ARMS = ("nidaan", "runbook", "oneshot")
SPEC_COUNTS = ("duplicate_payouts", "refused_unsafe_attempts", "actions", "unnecessary_actions",
               "harmful_actions", "llm_calls", "total_tokens", "llm_latency_s")
SUPP_COUNTS = ("wall_clock_s", "tool_steps", "actions_ok", "actions_refused", "actions_rejected",
               "input_tokens", "output_tokens")
REPLAN_DETAIL_KEYS = ("replans_accepted", "replans_after_a_falsifying_event",
                      "replans_without_a_falsifying_event_since_previous_plan", "plan_updates_rejected")


def _bool_ci(vals: list) -> dict | None:
    vals = [v for v in vals if v is not None]
    return wilson(sum(1 for v in vals if v), len(vals))


def _mean(vals: list) -> dict:
    vals = [v for v in vals if v is not None]
    return {"mean": (sum(vals) / len(vals)) if vals else None, "total": sum(vals) if vals else None,
            "n_available": len(vals)}


def summarize(records: list[dict]) -> dict:
    """Summary for one group of records (all from the same arm)."""
    spec = [r["metrics"]["spec"] for r in records]
    supp = [r["metrics"]["supplementary"] for r in records]
    rep = [s["appropriate_replanning"] for s in spec if s["appropriate_replanning"]]
    detail = [s["replan_detail"] for s in supp if s["replan_detail"]]
    batch = [s["batch_status_checked_before_settlement"]["always_checked"] for s in spec]
    return {
        "n_runs": len(records),
        "spec": {
            "goal_success": _bool_ci([s["goal_success"] for s in spec]),
            "runs_with_zero_duplicates": _bool_ci([s["duplicate_payouts"] == 0 for s in spec]),
            "batch_status_checked_before_every_settlement": _bool_ci(batch),
            "root_cause_component_accuracy": _bool_ci([s["root_cause_exact"] for s in spec]),
            "appropriate_replanning": (wilson(sum(r["replanned_in_time"] for r in rep),
                                              sum(r["falsifying_events"] for r in rep)) if rep else None),
            "counts": {k: _mean([s[k] for s in spec]) for k in SPEC_COUNTS},
        },
        "supplementary": {
            "note": "Descriptive only; not SPEC §9 metrics.",
            "counts": {k: _mean([s[k] for s in supp]) for k in SUPP_COUNTS},
            "replan_detail_totals": ({k: sum(d[k] for d in detail) for k in REPLAN_DETAIL_KEYS}
                                     if detail else None),
        },
    }


def _by_arm(records: list[dict]) -> dict:
    return {a: summarize([r for r in records if r["arm"] == a]) for a in ARMS
            if any(r["arm"] == a for r in records)}


def aggregate(records: list[dict], known_types=DEV_FAULTS) -> dict:
    known = set(known_types)
    scenarios = sorted({r["scenario"] for r in records})
    is_known = lambda r: all(f in known for f in r["faults"])  # noqa: E731
    return {
        "n_records": len(records),
        "by_arm": _by_arm(records),
        "by_scenario": {s: _by_arm([r for r in records if r["scenario"] == s]) for s in scenarios},
        "split_known_vs_held_out": {
            "known": _by_arm([r for r in records if is_known(r)]),
            "held_out": _by_arm([r for r in records if not is_known(r)]),
        },
        "definitions": DEFINITIONS,
        "note": "Small n; indicative only. Wilson 95% intervals. Counts are measured, never estimated.",
    }


def save_results(path: str, records: list[dict], summary: dict | None = None) -> dict:
    summary = summary if summary is not None else aggregate(records)
    out = {"records": records, "summary": summary}
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    return out


def load_results(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)
