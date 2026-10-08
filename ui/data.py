"""Non-UI helpers for the judge dashboard. No Streamlit import; fully unit-tested.

Metrics are NOT recalculated here: records come from evaluation.metrics.compute_run_metrics and
summaries from evaluation.aggregate.aggregate. This module only discovers logs, filters, formats and
classifies event fields for display.

Only development scenarios are ever surfaced: a run whose fault set is empty/unknown or contains any
non-development fault id is hidden (counted, never shown), so no held-out information can appear.
"""
from __future__ import annotations

import glob
import os
import re

from evaluation.aggregate import ARMS, aggregate
from evaluation.metrics import compute_run_metrics
from nidaan.logger import read_jsonl
from settlesim.generator import DEV_FAULTS

# ---- field classification (SPEC §6 channels) ----
AGENT_VISIBLE_FIELDS = ("goal", "tool", "args", "why", "result", "outcome", "plan_version", "steps",
                        "reason", "triggered_by", "diff", "checks", "retries_left")
RUN_META_FIELDS = ("ts", "llm_call", "latency_ms", "tokens", "model", "metrics", "error")

EVENT_COLORS = {"PLAN": "#4f46e5", "REPLAN": "#d97706", "OBSERVE": "#6b7280", "ACT": "#0d9488",
                "VERIFY": "#16a34a", "FINAL": "#1f2937", "ERROR": "#dc2626", "GOAL": "#0ea5e9"}


# ---- discovery and records ----
def discover_logs(runs_dir: str) -> list[str]:
    return sorted(glob.glob(os.path.join(runs_dir, "*.jsonl")), key=os.path.getmtime)


def is_api_failure(events: list[dict]) -> bool:
    """Run ended because of an API/quota error (infrastructure), not an agent decision."""
    final = next((e for e in reversed(events) if e["type"] == "FINAL"), None)
    return bool(final and str(final.get("result", "")).startswith("LLM error"))


def record_from_log(path: str) -> dict | None:
    """Result record (same shape as evaluation.harness.run_arm) built from a JSONL log."""
    try:
        events = read_jsonl(path)
        goal = next(e for e in events if e["type"] == "GOAL")
    except (StopIteration, ValueError, OSError):
        return None
    info = goal.get("eval") or {}
    m = re.search(r"-r(\d+)-", goal["run_id"])
    metrics = compute_run_metrics(events)
    return {"arm": metrics["arm"], "scenario": info.get("scenario", "unknown"), "seed": info.get("seed"),
            "faults": list(info.get("faults", [])), "repeat": int(m.group(1)) if m else 1,
            "run_id": goal["run_id"], "log_path": path, "metrics": metrics,
            "api_failure": is_api_failure(events),
            "incomplete": not any(e["type"] == "FINAL" for e in events)}


def build_records(runs_dir: str) -> list[dict]:
    return [r for r in (record_from_log(p) for p in discover_logs(runs_dir)) if r]


def is_dev_record(r: dict) -> bool:
    return bool(r["faults"]) and all(f in DEV_FAULTS for f in r["faults"])


def is_infra_failure(r: dict) -> bool:
    return bool(r.get("api_failure") or r.get("incomplete"))


def prepare(records: list[dict], exclude_infra: bool = False) -> tuple[list[dict], dict]:
    """Filter to development runs (always) and optionally drop infrastructure failures.
    Returns (records, counts). Nothing is dropped silently: counts report every exclusion."""
    dev = [r for r in records if is_dev_record(r)]
    infra = [r for r in dev if is_infra_failure(r)]
    kept = [r for r in dev if not (exclude_infra and is_infra_failure(r))]
    return kept, {"total_logs": len(records), "non_development_hidden": len(records) - len(dev),
                  "infrastructure_failures_in_view": len([r for r in kept if is_infra_failure(r)]),
                  "infrastructure_failures_total": len(infra),
                  "excluded_by_toggle": len(dev) - len(kept)}


def summarize_records(records: list[dict]) -> dict:
    return aggregate(records)  # existing aggregation code, unchanged


# ---- formatting ----
def fmt_ci(ci: dict | None) -> str:
    if not ci:
        return "n/a"
    return f"{ci['k']}/{ci['n']} = {ci['rate']:.0%}  (95% CI {ci['ci_low']:.0%}-{ci['ci_high']:.0%})"


def fmt_count(c: dict | None, digits: int = 1) -> str:
    if not c or c.get("mean") is None:
        return "unavailable"
    return f"{c['mean']:.{digits}f} (n={c['n_available']})"


SPEC_CI_ROWS = (("Goal success", "goal_success"),
                ("Runs with zero duplicate payouts", "runs_with_zero_duplicates"),
                ("Appropriate replanning (pooled falsifying events)", "appropriate_replanning"),
                ("Batch status checked before every settlement run", "batch_status_checked_before_every_settlement"),
                ("Root-cause component accuracy", "root_cause_component_accuracy"))
SPEC_COUNT_ROWS = (("Duplicate payouts (mean per run)", "duplicate_payouts"),
                   ("Refused unsafe attempts (mean)", "refused_unsafe_attempts"),
                   ("Actions (mean)", "actions"), ("Unnecessary actions (mean)", "unnecessary_actions"),
                   ("Harmful actions (mean)", "harmful_actions"), ("LLM calls (mean)", "llm_calls"),
                   ("Tokens, total (mean)", "total_tokens"), ("LLM latency, s (mean)", "llm_latency_s"))
SUPP_COUNT_ROWS = (("Wall-clock, s (mean)", "wall_clock_s"), ("Tool steps (mean)", "tool_steps"),
                   ("Actions executed OK (mean)", "actions_ok"), ("Actions refused (mean)", "actions_refused"),
                   ("Actions rejected (mean)", "actions_rejected"),
                   ("Input tokens (mean)", "input_tokens"), ("Output tokens (mean)", "output_tokens"))
REPLAN_LABELS = (("Replans accepted (total)", "replans_accepted"),
                 ("...after a falsifying event", "replans_after_a_falsifying_event"),
                 ("...with none since previous plan", "replans_without_a_falsifying_event_since_previous_plan"),
                 ("Plan updates rejected (total)", "plan_updates_rejected"))
NOT_APPLICABLE = {"runbook": "n/a (no plans)", "oneshot": "n/a (no plans)"}


def comparison_rows(by_arm: dict) -> list[dict]:
    """Side-by-side rows for every arm; an arm with no runs shows 'no runs', never a fabricated value."""
    def cells(fn):
        return {a: ("no runs" if a not in by_arm else fn(by_arm[a], a)) for a in ARMS}

    rows = [{"Type": "SPEC §9", "Metric": "Runs (n)",
             **cells(lambda s, a: str(s["n_runs"]))}]
    for label, key in SPEC_CI_ROWS:
        def f(s, a, key=key):
            v = s["spec"][key]
            if v is None and key == "appropriate_replanning":
                return NOT_APPLICABLE.get(a, "n/a")
            if v is None and key == "root_cause_component_accuracy":
                return "n/a (Nidaan only)"
            return fmt_ci(v)
        rows.append({"Type": "SPEC §9", "Metric": label, **cells(f)})
    for label, key in SPEC_COUNT_ROWS:
        rows.append({"Type": "SPEC §9", "Metric": label,
                     **cells(lambda s, a, key=key: fmt_count(s["spec"]["counts"][key]))})
    for label, key in SUPP_COUNT_ROWS:
        rows.append({"Type": "Supplementary", "Metric": label,
                     **cells(lambda s, a, key=key: fmt_count(s["supplementary"]["counts"][key]))})
    for label, key in REPLAN_LABELS:
        def f(s, a, key=key):
            t = s["supplementary"]["replan_detail_totals"]
            return str(t[key]) if t else NOT_APPLICABLE.get(a, "n/a")
        rows.append({"Type": "Supplementary", "Metric": label, **cells(f)})
    return rows


def scenario_matrix(records: list[dict], scenarios) -> list[dict]:
    """One row per supplied dev scenario; every arm shown, 'no runs' where none exist (no cherry-picking)."""
    rows = []
    for s in scenarios:
        row = {"Scenario": s.name}
        for a in ARMS:
            rs = [r for r in records if r["scenario"] == s.name and r["arm"] == a]
            ok = sum(r["metrics"]["spec"]["goal_success"] for r in rs)
            row[a] = f"{ok}/{len(rs)} succeeded" if rs else "no runs"
        rows.append(row)
    return rows


def run_label(r: dict) -> str:
    st = r["metrics"]["supplementary"]["final_outcome"] or "incomplete"
    flag = " [API/quota failure]" if r.get("api_failure") else (" [interrupted]" if r.get("incomplete") else "")
    return f"{r['arm']} | {r['scenario']} | {st}{flag} | {r['run_id']}"


# ---- trace helpers ----
def split_event_fields(e: dict) -> tuple[dict, dict, dict]:
    """(agent-visible, run-metadata, evaluation-only) fields of one event."""
    visible = {k: e[k] for k in AGENT_VISIBLE_FIELDS if k in e}
    meta = {k: e[k] for k in RUN_META_FIELDS if k in e}
    ev = e.get("eval") or {}
    if e["type"] == "VERIFY" and "args" in visible:  # the agent's submitted report
        visible["report"] = visible.pop("args")
    return visible, meta, dict(ev)


def event_style(e: dict) -> dict:
    kind = e["type"]
    replan = kind == "PLAN" and (e.get("plan_version") or 1) >= 2 and e.get("outcome") == "ok"
    key = "REPLAN" if replan else kind
    refused = e.get("outcome") == "refused"
    label = "REPLAN" if replan else kind
    badge = e.get("outcome") if kind in ("ACT", "OBSERVE", "PLAN", "VERIFY") else None
    return {"color": EVENT_COLORS[key], "label": label, "badge": badge, "refused": refused,
            "border": "#dc2626" if refused or e.get("outcome") in ("rejected", "fail") else EVENT_COLORS[key]}


def headline(e: dict) -> str:
    kind = e["type"]
    if kind in ("OBSERVE", "ACT"):
        args = e.get("args") or {}
        a = ", ".join(f"{k}={v}" for k, v in args.items() if v is not None)
        return f"{e.get('tool', '?')}({a})"
    if kind == "PLAN":
        return f"plan v{e.get('plan_version')}" if e.get("plan_version") else "plan update"
    if kind == "VERIFY":
        return f"verifier: {e.get('outcome', '?')}"
    if kind == "FINAL":
        return f"final: {e.get('outcome', '?')}"
    if kind == "ERROR":
        return "error"
    return "goal"


LOOP_PHASE = {"OBSERVE": "observe", "ACT": "act", "VERIFY": "verify", "FINAL": "final", "ERROR": "error",
              "GOAL": "goal"}


def loop_timeline(events: list[dict]) -> list[dict]:
    """Observe -> decide -> act -> environment changes -> re-observe -> replan -> verify, from the log."""
    rows = []
    for e in events:
        k, ann = e["type"], e.get("eval") or {}
        if k == "PLAN":
            first = (e.get("plan_version") or 0) <= 1 and e.get("outcome") == "ok"
            phase = "decide (initial plan)" if first else (
                "replan" if e.get("outcome") == "ok" else "plan update rejected")
        elif k == "ACT":
            phase = "act"
            if ann.get("new_failure_exposed"):
                phase = "act -> environment exposed a new failure"
            elif e.get("outcome") == "refused":
                phase = "act -> refused by a safety guard"
            elif e.get("outcome") == "rejected":
                phase = "act -> rejected"
        else:
            phase = LOOP_PHASE[k]
        rows.append({"seq": e["seq"], "phase": phase, "event": headline(e), "type": k})
    return rows


def evidence_summary(events: list[dict]) -> dict:
    counts: dict[str, int] = {}
    for e in events:
        counts[e["type"]] = counts.get(e["type"], 0) + 1
    plans = [e for e in events if e["type"] == "PLAN"]
    accepted = [e for e in plans if e.get("outcome") == "ok"]
    acts = [e for e in events if e["type"] == "ACT"]
    final = next((e for e in reversed(events) if e["type"] == "FINAL"), None)
    return {
        "event_counts": counts,
        "actions": [{"seq": e["seq"], "action": headline(e), "outcome": e.get("outcome")} for e in acts],
        "plans_accepted": len(accepted), "replans": max(0, len(accepted) - 1),
        "plan_updates_rejected": len(plans) - len(accepted),
        "replan_events": [{"seq": e["seq"], "version": e.get("plan_version"),
                           "triggered_by": e.get("triggered_by"), "added": (e.get("diff") or {}).get("added", []),
                           "removed": (e.get("diff") or {}).get("removed", [])}
                          for e in accepted[1:]],
        "final": ({"outcome": final.get("outcome"), "reason": final.get("result"),
                   "state_eval_only": final.get("eval"), "llm_metrics": final.get("metrics")}
                  if final else None),
    }
