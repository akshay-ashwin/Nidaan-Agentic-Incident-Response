"""Offline execution-trace analysis of run logs (descriptive; NOT SPEC §9 metrics).

Reads the existing JSONL events (nidaan/logger.py) and reuses evaluation.metrics for the SPEC §9
block. Everything else here is descriptive and labelled by evidence class:
  measured     - read directly from logged events
  derived      - computed from measured events by a rule stated in DEFINITIONS
  unavailable  - not recorded for this run/arm (with the reason); never estimated
Qualitative interpretation is deliberately NOT produced here. No hidden reasoning is inferred: the only
reasons used are the logged `why` arguments and plan `reason` fields, reported verbatim as stated text.
Evaluation-only annotations (`eval`) are read for post-run analysis only; they are never shown to an agent.
"""
from __future__ import annotations

import re
from datetime import datetime

from evaluation.metrics import REPLAN_WINDOW, _falsifying, compute_run_metrics

REASON_SOURCE = {
    "nidaan": "agent-supplied: the `why` argument the LLM attached to each tool call (stated text, not verified)",
    "runbook": "scripted: fixed strings in baselines/runbook.py (no LLM)",
    "oneshot": "scripted: fixed strings in baselines/oneshot.py; the LLM produced only the action list",
}
STEP_TYPES = ("OBSERVE", "ACT", "PLAN", "VERIFY")  # same step notion as evaluation.metrics
SENT_RE = re.compile(r"(?:Total sent|Payouts sent): (\d+)/(\d+)")
SHORT_VALUE = 2  # values this short (e.g. "1", "5") match almost any text; grounding is then "insufficient"

DEFINITIONS = {
    # measured
    "final_outcome": "FINAL.outcome (VERIFIED/FAILED for nidaan; GOAL_MET/GOAL_NOT_MET for baselines). JSON null if no FINAL; shown as 'none (no FINAL event)'.",
    "stop_reason": "FINAL.result text.",
    "verifier": "VERIFY events: number submitted, number passed, checks of the last one. Nidaan only.",
    "goal_met / duplicates / faults_active_at_end": "FINAL.eval (evaluation-only channel), set by SettleSim.",
    "payouts_sent_last_observed": "Last 'Total sent: x/y' or 'Payouts sent: x/y' in an agent-visible tool result. "
                                  "What the log showed, not a separate ground truth.",
    "actions_by_outcome": "ACT events counted by outcome: ok (applied), refused (safety guard), rejected "
                          "(schema/target/key invalid; not executed).",
    "tool_calls": "OBSERVE/ACT events counted by tool name.",
    "llm": "FINAL.metrics as logged by the run (calls, failed attempts, tokens, LLM latency).",
    "rate_limit_retries": "ERROR events of failed LLM attempts rejected by the provider rate limit "
                          "(text contains 'RateLimit' or 'RESOURCE_EXHAUSTED').",
    "other_llm_errors": "ERROR events of other failed LLM attempts (e.g. 503, timeout).",
    "nudges": "ERROR events 'agent replied without a tool call'.",
    "wall_clock_s": "Last event ts minus first event ts.",
    # derived
    "action_validity_rate": "(ok + refused) / ACT events: share of actions whose tool, target and parameters "
                            "were accepted (a refusal is a valid request blocked by a safety guard).",
    "failure_responses": "For each ACT that was rejected or annotated new_failure_exposed / no_effect / harmful / "
                         "refusal: the next step (OBSERVE/ACT/PLAN/VERIFY; ERROR is not a step) and whether an "
                         f"accepted PLAN followed within {REPLAN_WINDOW} steps (same window as SPEC §9 metric).",
    "repeated_rejected_actions": "ACT whose tool and args (excluding `why`) equal an earlier rejected ACT.",
    "set_config_grounding": "For each set_config: key_seen_before = '<key>:' occurs in an earlier OBSERVE result; "
                            "value_seen_before = the value occurs as a whole word in an earlier tool result. "
                            f"Values of <= {SHORT_VALUE} characters are 'insufficient': JSON null, shown as '—'.",
    "inspected_before_act": "Share of component-targeted ACT events (restart/set_config/run_task) preceded at any "
                            "earlier point by inspect or read_logs of the same component.",
    "replan_citations": "For each accepted PLAN v2+: the cited events' type, tool and outcome.",
    "after_all_faults_cleared": "Evaluation-only: first ACT after which SettleSim reports no active fault; whether a "
                                "run_settlement ACT and a check_pipeline OBSERVE follow it.",
    "non_llm_wall_clock_s": "wall_clock_s - LLM latency: time spent outside successful LLM calls (rate-limit "
                            "waits, failed attempts, tool execution).",
    "tokens_per_llm_call": "total_tokens / llm_calls.",
    # report diagnostics (descriptive; not SPEC §9 metrics; verifier pass/fail unchanged)
    "report_action_coverage": "Last submitted report's `actions` vs ACT events executed (outcome ok) before it: "
                              "claimed executed, omitted executed, claimed but not executed (rejected/refused), "
                              "invalid references (not an ACT event before the report, or not an integer), duplicates.",
    "report_root_cause_evidence": "Per reported root cause: cited ACT events whose evaluation-only annotation is "
                                  "no_effect. A flag marks the citation for review; it is not a verdict, because a "
                                  "no-effect action can be valid evidence (e.g. a retry that still fails). 'uncertain' = "
                                  "no evidence cited, cited ACT without the annotation, or a citation that is not an "
                                  "OBSERVE/ACT event before the report.",
}


def is_rate_limit(msg: str) -> bool:
    """A failed LLM attempt rejected by the provider's rate limit (Groq RateLimitError / Gemini RESOURCE_EXHAUSTED).
    A bare '429' is not enough: tool results quoted inside other errors can contain it."""
    return "LLM call failed" in msg and ("RateLimit" in msg or "RESOURCE_EXHAUSTED" in msg)


def _ts(e: dict) -> datetime:
    return datetime.fromisoformat(e["ts"])


def _num(x):
    return x if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def _key(e: dict) -> tuple:
    return e.get("tool"), tuple(sorted((k, str(v)) for k, v in (e.get("args") or {}).items() if k != "why"))


def integrity(events: list[dict]) -> dict:
    """Log well-formedness. Analysis runs on events sorted by seq; problems are reported, not hidden."""
    seqs = [e.get("seq") for e in events]
    ordered = sorted(events, key=lambda e: e.get("seq", 0))
    types = [e["type"] for e in ordered]
    return {"n_events": len(events),
            "seq_in_file_order": seqs == sorted(seqs),
            "seq_contiguous": sorted(seqs) == list(range(1, len(events) + 1)),
            "has_goal": "GOAL" in types, "has_final": "FINAL" in types,
            "final_is_last": bool(types) and types[-1] == "FINAL",
            "complete": "GOAL" in types and bool(types) and types[-1] == "FINAL"}


def _steps(events):
    return [e for e in events if e["type"] in STEP_TYPES]


def failure_responses(events: list[dict]) -> list[dict]:
    steps = _steps(events)
    out = []
    for f in (e for e in events if e["type"] == "ACT"):
        ann = f.get("eval") or {}
        kinds = [k for k in ("new_failure_exposed", "no_effect", "harmful", "refusal") if ann.get(k)]
        if f.get("outcome") == "rejected":
            kinds.append("rejected")
        if not kinds:
            continue
        after = [e for e in steps if e["seq"] > f["seq"]]
        nxt = after[0] if after else None
        within = after[:REPLAN_WINDOW]
        out.append({"seq": f["seq"], "action": _label(f), "kinds": kinds,
                    "next_step": (f"{nxt['type']} {nxt.get('tool') or ''}".strip() + f" (#{nxt['seq']})") if nxt else None,
                    "replanned_within_window": any(e["type"] == "PLAN" and e.get("outcome") == "ok" for e in within),
                    "counted_by_spec_metric": _falsifying(f)})
    return out


def set_config_grounding(events: list[dict]) -> list[dict]:
    out = []
    for i, e in enumerate(events):
        if not (e["type"] == "ACT" and e.get("tool") == "set_config"):
            continue
        a = e.get("args") or {}
        key, value = str(a.get("key", "")), str(a.get("value", ""))
        earlier = [x for x in events[:i] if x["type"] in ("OBSERVE", "ACT")]
        obs_text = "\n".join(str(x.get("result", "")) for x in earlier if x["type"] == "OBSERVE")
        all_text = "\n".join(str(x.get("result", "")) for x in earlier)
        value_seen = (None if len(value) <= SHORT_VALUE
                      else re.search(rf"(?<![\w-]){re.escape(value)}(?![\w-])", all_text) is not None)
        out.append({"seq": e["seq"], "component": a.get("component"), "key": key, "value": value,
                    "outcome": e.get("outcome"), "key_seen_before": f"{key}:" in obs_text,
                    "value_seen_before": value_seen})
    return out


def inspected_before_act(events: list[dict]) -> dict:
    seen, n, ok, misses = set(), 0, 0, []
    for e in events:
        comp = (e.get("args") or {}).get("component")
        if e["type"] == "OBSERVE" and e.get("tool") in ("inspect", "read_logs") and comp:
            seen.add(comp)
        elif e["type"] == "ACT" and e.get("tool") in ("restart", "set_config", "run_task") and comp:
            n += 1
            if comp in seen:
                ok += 1
            else:
                misses.append(e["seq"])
    return {"component_actions": n, "inspected_first": ok, "rate": (ok / n) if n else None,
            "not_inspected_first": misses}


def replan_citations(events: list[dict]) -> list[dict]:
    by_seq = {e["seq"]: e for e in events}
    out = []
    for p in events:
        if p["type"] == "PLAN" and p.get("outcome") == "ok" and (p.get("plan_version") or 1) >= 2:
            cited = [by_seq.get(s) for s in (p.get("triggered_by") or [])]
            out.append({"seq": p["seq"], "version": p.get("plan_version"), "reason": p.get("reason"),
                        "cited": [{"seq": c["seq"], "type": c["type"], "event": _label(c), "outcome": c.get("outcome")}
                                  if c else {"seq": None, "type": "missing"} for c in cited]})
    return out


def after_all_faults_cleared(events: list[dict]) -> dict | None:
    """Evaluation-only channel. None if no ACT carries fault annotations (e.g. no actions)."""
    acts = [e for e in events if e["type"] == "ACT" and "faults_active_after" in (e.get("eval") or {})]
    if not acts:
        return None
    first = next((e for e in acts if not e["eval"]["faults_active_after"]), None)
    if first is None:
        return {"cleared_at": None, "faults_still_active": acts[-1]["eval"]["faults_active_after"]}
    later = [e for e in events if e["seq"] > first["seq"]]
    return {"cleared_at": first["seq"], "cleared_by": _label(first),
            "settlement_after": [e["seq"] for e in later if e["type"] == "ACT" and e.get("tool") == "run_settlement"],
            "check_pipeline_after": [e["seq"] for e in later
                                     if e["type"] == "OBSERVE" and e.get("tool") == "check_pipeline"],
            "steps_after": len(_steps(later))}


REPORT_DIAG_NOTE = ("Descriptive diagnostics of the submitted incident report; not SPEC §9 metrics; the verifier's "
                    "pass/fail result (SPEC §5) is unchanged.")


def _int(x) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def report_diagnostics(events: list[dict], arm: str | None) -> dict:
    """Action coverage and root-cause evidence of the last submitted report. Uses only events logged before it."""
    if arm != "nidaan":
        return {"status": "not_applicable",
                "reason": f"{arm} arm does not submit an incident report" if arm else "arm unknown (no GOAL event)"}
    reports = [e for e in events if e["type"] == "VERIFY" and isinstance(e.get("args"), dict)]
    if not reports:
        return {"status": "no_report", "reason": "no incident report was submitted"}
    rep = reports[-1]
    args = rep["args"]
    before = {e["seq"]: e for e in events if e["seq"] < rep["seq"]}

    raw = args.get("actions")
    if not isinstance(raw, list):
        coverage = {"status": "unavailable", "reason": "report has no 'actions' list"}
    else:
        executed = sorted(s for s, e in before.items() if e["type"] == "ACT" and e.get("outcome") == "ok")
        claimed, not_executed, invalid, dup, seen = [], [], [], [], set()
        for x in raw:
            if not _int(x):
                invalid.append(x)
                continue
            if x in seen:
                dup.append(x)
                continue
            seen.add(x)
            e = before.get(x)
            if e is None or e["type"] != "ACT":
                invalid.append(x)
            elif e.get("outcome") == "ok":
                claimed.append(x)
            else:
                not_executed.append({"seq": x, "outcome": e.get("outcome")})
        coverage = {"status": "ok", "executed": executed, "claimed_executed": claimed,
                    "omitted_executed": sorted(set(executed) - set(claimed)),
                    "claimed_not_executed": not_executed, "invalid_references": invalid,
                    "duplicate_references": dup,
                    "coverage": f"{len(claimed)}/{len(executed)}" if executed else None}

    rcs = args.get("root_causes")
    if not isinstance(rcs, list) or not rcs:
        evidence = {"status": "unavailable", "reason": "report has no root causes"}
    else:
        items = []
        for i, rc in enumerate(rcs, 1):
            rc = rc if isinstance(rc, dict) else {}
            cited = rc.get("evidence")
            item = {"index": i, "component": rc.get("component"), "description": rc.get("description"),
                    "cited": cited}
            if not isinstance(cited, list) or not cited:
                items.append({**item, "status": "uncertain", "reason": "no evidence cited"})
                continue
            no_effect, unannotated, invalid = [], [], []
            for x in cited:
                e = before.get(x) if _int(x) else None
                if e is None or e["type"] not in ("OBSERVE", "ACT"):
                    invalid.append(x)
                elif e["type"] == "ACT":
                    ann = e.get("eval")
                    if not isinstance(ann, dict) or "no_effect" not in ann:
                        unannotated.append(x)
                    elif ann["no_effect"]:
                        no_effect.append(x)
            status = "flagged" if no_effect else ("uncertain" if unannotated or invalid else "no_flag")
            items.append({**item, "cites_no_effect_actions": no_effect,
                          "act_evidence_without_annotation": unannotated, "invalid_evidence": invalid,
                          "status": status})
        evidence = {"status": "ok", "root_causes": items}
    return {"status": "ok", "note": REPORT_DIAG_NOTE, "report_seq": rep["seq"], "reports_submitted": len(reports),
            "verifier_outcome": rep.get("outcome"), "action_coverage": coverage, "root_cause_evidence": evidence}


def _label(e: dict) -> str:
    if e["type"] in ("OBSERVE", "ACT"):
        args = ", ".join(f"{k}={v}" for k, v in (e.get("args") or {}).items() if v is not None)
        return f"{e.get('tool', '?')}({args})"
    if e["type"] == "PLAN":
        return f"plan v{e.get('plan_version')}"
    return e["type"].lower()


def analyse_run(events: list[dict], source: str = "") -> dict:
    integ = integrity(events)
    events = sorted(events, key=lambda e: e.get("seq", 0))
    goal = next((e for e in events if e["type"] == "GOAL"), None)
    final = next((e for e in reversed(events) if e["type"] == "FINAL"), None)
    info = (goal or {}).get("eval") or {}
    arm = info.get("arm", "nidaan") if goal else None
    arm_source = ("GOAL.eval.arm" if "arm" in info else
                  "default 'nidaan' (no arm in GOAL.eval: CLI run; same default as evaluation.metrics)" if goal else None)
    acts = [e for e in events if e["type"] == "ACT"]
    errors = [e for e in events if e["type"] == "ERROR"]
    llm_fail = [e for e in errors if "LLM call failed" in str(e.get("error", ""))]
    verifies = [e for e in events if e["type"] == "VERIFY"]
    plans = [e for e in events if e["type"] == "PLAN"]
    llm = (final or {}).get("metrics") or {}
    fin_eval = (final or {}).get("eval") or {}
    sent = [m for e in events if e["type"] in ("OBSERVE", "ACT") for m in SENT_RE.findall(str(e.get("result", "")))]
    by_outcome = {o: sum(1 for e in acts if e.get("outcome") == o) for o in ("ok", "refused", "rejected")}
    tools: dict[str, int] = {}
    for e in events:
        if e["type"] in ("OBSERVE", "ACT"):
            tools[e.get("tool")] = tools.get(e.get("tool"), 0) + 1
    wall = round((_ts(events[-1]) - _ts(events[0])).total_seconds(), 2) if len(events) > 1 else None
    lat, calls, tok = _num(llm.get("latency_s")), _num(llm.get("llm_calls")), _num(llm.get("total_tokens"))
    uses_llm = arm in ("nidaan", "oneshot")

    measured = {
        "final_outcome": (final or {}).get("outcome"), "stop_reason": (final or {}).get("result"),
        "verifier": ({"submitted": len(verifies), "passed": sum(v.get("outcome") == "pass" for v in verifies),
                      "last_checks": verifies[-1].get("checks") if verifies else None} if arm == "nidaan" else None),
        "goal_met": fin_eval.get("goal_met"), "duplicates": fin_eval.get("duplicates"),
        "faults_active_at_end": fin_eval.get("faults_active"),
        "payouts_sent_last_observed": f"{sent[-1][0]}/{sent[-1][1]}" if sent else None,
        "actions": len(acts), "actions_by_outcome": by_outcome, "tool_calls": tools,
        "plans": [{"seq": p["seq"], "version": p.get("plan_version"), "outcome": p.get("outcome"),
                   "triggered_by": p.get("triggered_by"), "n_steps": len(p.get("steps") or [])} for p in plans],
        "llm": llm or None,
        "rate_limit_retries": sum(is_rate_limit(str(e.get("error"))) for e in llm_fail),
        "other_llm_errors": sum(not is_rate_limit(str(e.get("error"))) for e in llm_fail),
        "nudges": sum("without a tool call" in str(e.get("error", "")) for e in errors),
        "wall_clock_s": wall,
    }
    derived = {
        "action_validity_rate": ((by_outcome["ok"] + by_outcome["refused"]) / len(acts)) if acts else None,
        "failure_responses": failure_responses(events),
        "repeated_rejected_actions": [e["seq"] for i, e in enumerate(acts)
                                      if any(p.get("outcome") == "rejected" and _key(p) == _key(e) for p in acts[:i])],
        "set_config_grounding": set_config_grounding(events),
        "inspected_before_act": inspected_before_act(events),
        "replan_citations": replan_citations(events),
        "after_all_faults_cleared": after_all_faults_cleared(events),
        "non_llm_wall_clock_s": round(wall - lat, 2) if (wall is not None and lat is not None and uses_llm) else None,
        "tokens_per_llm_call": round(tok / calls, 1) if (tok is not None and calls) else None,
    }
    unavailable = {}
    if not integ["has_goal"]:
        unavailable["spec_metrics"] = "no GOAL event; SPEC §9 metrics cannot be computed"
    if not integ["has_final"]:
        unavailable["final"] = "no FINAL event: run incomplete (stopped or crashed); outcome, goal state, LLM totals unknown"
    if arm in ("runbook", "oneshot"):
        unavailable["plans_and_replanning"] = f"{arm} arm does not plan"
        unavailable["verifier"] = f"{arm} arm does not submit an incident report"
    if arm == "runbook":
        unavailable["llm_tokens_latency"] = "not applicable: runbook makes no LLM calls (0 calls logged)"
    if arm == "nidaan" and not verifies and integ["has_final"]:
        unavailable["verifier"] = "no report was submitted, so the verifier never ran"
    if not sent:
        unavailable["payouts_sent_last_observed"] = "no payout count appears in agent-visible results"
    spec = compute_run_metrics(events)["spec"] if goal else None
    return {"source": source, "run_id": (events[0].get("run_id") if events else None), "arm": arm,
            "arm_source": arm_source, "reason_source": REASON_SOURCE.get(arm, "unknown"),
            "scenario": info.get("scenario"), "seed": info.get("seed"), "faults": info.get("faults"),
            "model": (goal or {}).get("model"), "integrity": integ, "measured": measured, "derived": derived,
            "spec_metrics": spec, "unavailable": unavailable,
            "report_diagnostics": report_diagnostics(events, arm)}


def _short(text, n: int = 110) -> str:
    s = " / ".join(line.strip() for line in str(text or "").splitlines() if line.strip())
    return s if len(s) <= n else s[: n - 1] + "…"


def timeline(events: list[dict]) -> list[dict]:
    """observation -> action -> environment response -> plan revision -> verification, one row per step.
    Consecutive ERROR events are folded into the next row as counts (rate-limit retries, nudges, other)."""
    rows, pend = [], {"rate_limit_retries": 0, "nudges": 0, "other_errors": 0}
    for e in sorted(events, key=lambda e: e.get("seq", 0)):
        t = e["type"]
        if t == "ERROR":
            msg = str(e.get("error", ""))
            k = ("rate_limit_retries" if is_rate_limit(msg)
                 else "nudges" if "without a tool call" in msg else "other_errors")
            pend[k] += 1
            continue
        ann = e.get("eval") or {}
        flags = [k for k in ("new_failure_exposed", "no_effect", "harmful", "refusal", "duplicate_created")
                 if t == "ACT" and ann.get(k)]
        if t == "GOAL":
            stage, what, resp = "goal", f"model {e.get('model') or 'none'}", ""
        elif t == "PLAN":
            v = e.get("plan_version")
            stage = "plan" if (v or 1) <= 1 else "replan"
            if e.get("outcome") != "ok":
                stage = "plan rejected"
            diff = e.get("diff") or {}
            what = f"plan v{v}" + (f" <- triggered by {e.get('triggered_by')}" if e.get("triggered_by") else "")
            resp = f"+{len(diff.get('added', []))}/-{len(diff.get('removed', []))} steps; reason: {_short(e.get('reason'), 80)}"
        elif t == "OBSERVE":
            stage, what, resp = "observe", _label(e), _short(e.get("result"))
        elif t == "ACT":
            stage, what, resp = f"act [{e.get('outcome')}]", _label(e), _short(e.get("result"))
        elif t == "VERIFY":
            stage, what = f"verify [{e.get('outcome')}]", "submit_incident_report"
            resp = " ".join(f"{k}{'✓' if v else '✗'}" for k, v in (e.get("checks") or {}).items())
        else:  # FINAL
            stage, what, resp = "final", str(e.get("outcome")), _short(e.get("result"))
        rows.append({"seq": e["seq"], "stage": stage, "event": what, "stated_reason": e.get("why"),
                     "environment_response": resp, "eval_flags": flags,
                     "errors_before": {k: v for k, v in pend.items() if v}})
        pend = {k: 0 for k in pend}
    if any(pend.values()):
        rows.append({"seq": None, "stage": "log ends", "event": "", "stated_reason": None,
                     "environment_response": "no FINAL event after these errors", "eval_flags": [],
                     "errors_before": {k: v for k, v in pend.items() if v}})
    return rows


COMPARE_COLS = ("scenario", "arm", "final_outcome", "goal_met", "duplicates", "payouts", "actions", "ok", "refused",
                "rejected", "unnecessary", "batch_checked", "replan_in_time", "llm_calls", "tokens", "llm_latency_s",
                "wall_clock_s", "run_id")
COMPARE_LEGEND = (
    "Columns: `goal_met`, `duplicates` = evaluation-only state at FINAL; `payouts` = last count shown in the log; "
    "`ok/refused/rejected` = ACT outcomes; `unnecessary`, `batch_checked` (runs with a batch-status check / "
    "settlement runs), `replan_in_time` (falsifying events followed by a plan within 2 steps / falsifying events) "
    "= SPEC §9 metrics from evaluation/metrics.py, unchanged; `tokens`, `llm_latency_s` = FINAL.metrics; "
    "`n/a` = not applicable to the arm; `—` = not recorded.")


def _sort_key(a: dict):
    return (str(a["scenario"]), str(a["arm"]), str(a["run_id"]))


def comparison_rows(analyses: list[dict]) -> list[dict]:
    rows = []
    for a in sorted(analyses, key=_sort_key):
        m, s = a["measured"], a["spec_metrics"] or {}
        b, rp = s.get("batch_status_checked_before_settlement") or {}, s.get("appropriate_replanning")
        llm, no_llm = m["llm"] or {}, a["arm"] == "runbook"
        rows.append({"scenario": a["scenario"], "arm": a["arm"], "final_outcome": m["final_outcome"] or "INCOMPLETE",
                     "goal_met": m["goal_met"], "duplicates": m["duplicates"],
                     "payouts": m["payouts_sent_last_observed"], "actions": m["actions"],
                     **m["actions_by_outcome"], "unnecessary": s.get("unnecessary_actions"),
                     "batch_checked": (f"{b.get('settlement_runs_with_batch_check')}/{b.get('settlement_runs')}"
                                       if b.get("settlement_runs") else "n/a"),
                     "replan_in_time": (f"{rp['replanned_in_time']}/{rp['falsifying_events']}" if rp else "n/a"),
                     "llm_calls": llm.get("llm_calls"), "tokens": "n/a" if no_llm else llm.get("total_tokens"),
                     "llm_latency_s": "n/a" if no_llm else llm.get("latency_s"), "wall_clock_s": m["wall_clock_s"],
                     "run_id": a["run_id"]})
    return rows


def _md_table(rows: list[dict], cols, headers=None) -> str:
    def fmt(v):
        return "—" if v is None or v == "" else str(v).replace("|", "\\|").replace("\n", " ")
    head = "| " + " | ".join(headers or cols) + " |\n|" + "---|" * len(cols) + "\n"
    return head + "".join("| " + " | ".join(fmt(r.get(c)) for c in cols) + " |\n" for r in rows)


def _na(v, unit: str = "") -> str:
    return "n/a" if v is None else f"{v}{unit}"


def _faults(fs) -> str:
    return "n/a" if fs is None else (", ".join(fs) or "none")


def _measured_lines(a: dict) -> list[str]:
    m = a["measured"]
    o = m["actions_by_outcome"]
    v, llm = m["verifier"], m["llm"] or {}
    if v is None:
        ver = "n/a (arm does not submit a report)" if a["arm"] in ("runbook", "oneshot") else "n/a"
    elif v["submitted"] == 0:
        ver = "not invoked (no report submitted)"
    else:
        checks = " ".join(f"{k}{'✓' if ok else '✗'}" for k, ok in (v["last_checks"] or {}).items())
        ver = f"{v['submitted']} submitted, {v['passed']} passed; last: {checks}"
    if a["arm"] == "runbook":
        llm_s = "none (runbook makes no LLM calls)"
    elif llm:
        llm_s = (f"{llm.get('llm_calls')} successful calls, {llm.get('llm_errors')} failed attempts; tokens "
                 f"{llm.get('input_tokens')} in + {llm.get('output_tokens')} out = {llm.get('total_tokens')}; "
                 f"LLM latency {llm.get('latency_s')} s")
    else:
        llm_s = "not recorded (no FINAL event)"
    return [
        f"- Final: **{m['final_outcome'] or 'none (no FINAL event)'}** — {m['stop_reason'] or 'no stop reason'}",
        f"- Goal met: {_na(m['goal_met'])}; duplicate payouts: {_na(m['duplicates'])}; faults active at end: "
        f"{_faults(m['faults_active_at_end'])} *(evaluation-only state, read after the run)*",
        f"- Payouts last shown in the log: {_na(m['payouts_sent_last_observed'])}",
        f"- Actions: {m['actions']} ({o['ok']} ok, {o['refused']} refused, {o['rejected']} rejected)",
        f"- Verifier: {ver}",
        f"- LLM: {llm_s}",
        f"- Errors: {m['rate_limit_retries']} rate-limit retries, {m['other_llm_errors']} other failed LLM attempts, "
        f"{m['nudges']} nudge{'' if m['nudges'] == 1 else 's'}; wall-clock {_na(m['wall_clock_s'], ' s')}",
    ]


def _derived_lines(a: dict) -> list[str]:
    d, s = a["derived"], a["spec_metrics"] or {}
    fr, ib, af = d["failure_responses"], d["inspected_before_act"], d["after_all_faults_cleared"]
    n_spec = sum(f["counted_by_spec_metric"] for f in fr)
    if a["arm"] == "nidaan":
        rp = s.get("appropriate_replanning")
        resp = (f"{len(fr)} failure events ({n_spec} falsifying per SPEC §9 + {len(fr) - n_spec} rejections or "
                f"other); accepted plan within {REPLAN_WINDOW} steps after {sum(f['replanned_within_window'] for f in fr)}"
                f" of them. SPEC §9 appropriate replanning (falsifying events only): "
                + (f"{rp['replanned_in_time']}/{rp['falsifying_events']}" if rp else "n/a"))
    else:
        resp = f"{len(fr)} failure events; replanning n/a (arm does not plan)"
    if af is None:
        clr = "n/a (no actions with fault annotations)"
    elif af["cleared_at"] is None:
        clr = f"never — still active at end: {', '.join(af['faults_still_active'])}"
    else:
        lst = lambda xs: ", ".join(f"#{x}" for x in xs) or "none"  # noqa: E731
        clr = (f"at #{af['cleared_at']} by `{af['cleared_by']}`; afterwards settlement: {lst(af['settlement_after'])}; "
               f"check_pipeline: {lst(af['check_pipeline_after'])} ({af['steps_after']} steps after)")
    rate = d["action_validity_rate"]
    return [
        f"- Action validity: {'n/a (no actions)' if rate is None else f'{rate:.2f}'}",
        f"- Component inspected before acting on it: {ib['inspected_first']}/{ib['component_actions']}"
        + (" (weak evidence: says nothing about whether the target was right)" if ib["component_actions"] else ""),
        f"- Failure responses: {resp}",
        f"- Repeated rejected actions: {', '.join(f'#{x}' for x in d['repeated_rejected_actions']) or 'none'}",
        f"- All faults cleared *(evaluation-only)*: {clr}",
        f"- Time outside successful LLM calls: {_na(d['non_llm_wall_clock_s'], ' s')}; "
        f"tokens per LLM call: {_na(d['tokens_per_llm_call'])}",
    ]


def _seqs(xs) -> str:
    return ", ".join(f"#{x}" if _int(x) else repr(x) for x in xs) or "none"


def _report_lines(rd: dict) -> list[str]:
    if rd["status"] != "ok":
        return [f"- n/a — {rd['reason']}"]
    lines = [f"- Report: VERIFY #{rd['report_seq']} (verifier: {rd['verifier_outcome']}; "
             f"{rd['reports_submitted']} submitted; the last is analysed)"]
    c = rd["action_coverage"]
    if c["status"] != "ok":
        lines.append(f"- Action coverage: unavailable — {c['reason']}")
    else:
        not_executed = ", ".join("#{} ({})".format(x["seq"], x["outcome"]) for x in c["claimed_not_executed"]) or "none"
        lines.append(f"- Action coverage: {c['coverage'] or 'n/a (no executed actions)'} executed actions listed; "
                     f"omitted: {_seqs(c['omitted_executed'])}; listed but not executed: {not_executed}; "
                     f"invalid references: {_seqs(c['invalid_references'])}; duplicates: {_seqs(c['duplicate_references'])}")
    ev = rd["root_cause_evidence"]
    if ev["status"] != "ok":
        lines.append(f"- Root-cause evidence: unavailable — {ev['reason']}")
    else:
        for r in ev["root_causes"]:
            head = f"- Root cause {r['index']} ({r['component']}), cites {_seqs(r['cited'] or [])}: "
            if r["status"] == "flagged":
                lines.append(head + f"**flag** — cites action(s) recorded as no effect: {_seqs(r['cites_no_effect_actions'])} "
                             "*(review; not a verdict)*")
            elif r["status"] == "uncertain":
                why = r.get("reason") or "; ".join(
                    x for x in (f"ACT without annotation: {_seqs(r['act_evidence_without_annotation'])}"
                                if r.get("act_evidence_without_annotation") else "",
                                f"not an OBSERVE/ACT event before the report: {_seqs(r['invalid_evidence'])}"
                                if r.get("invalid_evidence") else "") if x)
                lines.append(head + f"uncertain — {why}")
            else:
                lines.append(head + "no flag")
    return lines


def render_markdown(analyses: list[dict], timelines: dict[str, list[dict]], inputs: list[str] | None = None) -> str:
    analyses = sorted(analyses, key=_sort_key)
    out = ["# Nidaan execution-trace analysis",
           "Generated offline from run logs; no LLM or API calls. Evidence classes: **measured** (read from logged "
           "events), **derived** (computed by a rule in Definitions), **unavailable / n/a** (not recorded or not "
           "applicable; never estimated). No qualitative judgement is generated and no hidden reasoning is "
           "inferred. Reasons shown are logged text only: for Nidaan the LLM's `why` argument; for the runbook and "
           "one-shot baselines fixed scripted strings, **not** LLM-generated reasoning. Fields marked "
           "*evaluation-only* come from the annotation channel the agent never saw; they are used here only "
           "after the run."]
    if inputs:
        out.append("**Inputs** (" + str(len(analyses)) + " runs): " + ", ".join(f"`{p}`" for p in inputs))
    out += ["## Comparison (one row per run)", _md_table(comparison_rows(analyses), COMPARE_COLS), COMPARE_LEGEND]
    for a in analyses:
        d = a["derived"]
        integ = a["integrity"]
        out.append(f"## {a['arm']} · {a['scenario']} · `{a['run_id']}`")
        out.append("\n".join([
            f"- Source: `{a['source']}` ({integ['n_events']} events; "
            f"{'complete' if integ['complete'] else '**INCOMPLETE**'}"
            f"{'' if integ['seq_contiguous'] else '; **sequence gaps**'}"
            f"{'' if integ['seq_in_file_order'] else '; out of order in file (sorted for analysis)'})",
            f"- Arm: {a['arm']} — source: {a['arm_source']}; model: `{a['model'] or 'none'}`; "
            f"faults: {', '.join(a['faults'] or []) or 'n/a'}",
            f"- Reasons in the timeline: {a['reason_source']}"]))
        out.append("**Measured**\n\n" + "\n".join(_measured_lines(a)))
        out.append("**Derived**\n\n" + "\n".join(_derived_lines(a)))
        out.append("**Report diagnostics** *(descriptive; not SPEC §9 metrics; verifier pass/fail unchanged; "
                   "no-effect annotations are evaluation-only, read after the run)*\n\n"
                   + "\n".join(_report_lines(a["report_diagnostics"])))
        if d["set_config_grounding"]:
            out.append("`set_config` grounding (key / value seen in an earlier observation; `—` = value too short "
                       "to be evidence):\n\n" + _md_table(
                           d["set_config_grounding"],
                           ("seq", "component", "key", "value", "outcome", "key_seen_before", "value_seen_before")))
        if d["replan_citations"]:
            out.append("Replan triggers (events cited by each accepted plan update):\n\n" + "\n".join(
                f"- plan v{r['version']} (#{r['seq']}): " + ", ".join(
                    f"#{c['seq']} {c['type']} `{c.get('event', '')}` [{c.get('outcome')}]" for c in r["cited"])
                for r in d["replan_citations"]))
        if a["unavailable"]:
            out.append("**Unavailable / not applicable**\n\n" + "\n".join(
                f"- {k}: {v}" for k, v in a["unavailable"].items()))
        tl = timelines.get(a["run_id"])
        if tl:
            rows = [{**r, "errors_before": ", ".join(f"{k}={v}" for k, v in r["errors_before"].items()),
                     "eval_flags": ", ".join(r["eval_flags"])} for r in tl]
            reason_hdr = "stated why (LLM)" if a["arm"] == "nidaan" else "scripted reason"
            out.append("Timeline (`errors before` = folded ERROR events; `eval flags` = evaluation-only):\n\n" + _md_table(
                rows, ("seq", "errors_before", "stage", "event", "stated_reason", "environment_response", "eval_flags"),
                ("seq", "errors before", "stage", "event", reason_hdr, "environment response", "eval flags")))
    out.append("## Definitions\n\n" + "\n".join(f"- **{k}**: {v}" for k, v in DEFINITIONS.items()))
    return "\n\n".join(out) + "\n"
