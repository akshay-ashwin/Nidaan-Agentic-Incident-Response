"""Offline trace analyser: calculations, ordering, missing events, failed and incomplete runs. No LLM."""
import importlib.util
import json
import os
import random
from datetime import datetime, timedelta, timezone

import pytest

from evaluation.trace_analysis import (analyse_run, comparison_rows, failure_responses, integrity, render_markdown,
                                       set_config_grounding, timeline)

T0 = datetime(2026, 10, 10, tzinfo=timezone.utc)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def ev(seq, type, t=None, **kw):
    return {"seq": seq, "ts": (T0 + timedelta(seconds=t if t is not None else seq)).isoformat(),
            "run_id": "r1", "type": type, **kw}


def act(seq, tool, outcome="ok", eval=None, **args):
    return ev(seq, "ACT", tool=tool, args=args, why="w", result=f"{tool} result", outcome=outcome,
              eval={"new_failure_exposed": False, "refusal": False, "no_effect": False, "harmful": False,
                    "duplicate_created": False, "faults_active_after": ["F1"], **(eval or {})})


def obs(seq, tool, result="", **args):
    return ev(seq, "OBSERVE", tool=tool, args=args, why="w", result=result, outcome="ok")


def plan(seq, v, trig=()):
    return ev(seq, "PLAN", plan_version=v, steps=["a"], reason="r", triggered_by=list(trig), outcome="ok",
              diff={"added": ["a"], "removed": []})


def rate_limit(seq):
    return ev(seq, "ERROR", error="LLM call failed (attempt 1): RateLimitError: Error code: 429 - tokens per minute")


GOAL = ev(1, "GOAL", goal="g", model="groq:m", eval={"scenario": "s", "seed": 1, "faults": ["F1"]})


def verified_run():
    return [GOAL, plan(2, 1), obs(3, "inspect", "bank:\n  key_in_use: key-abc123\n  max_concurrency: 9", component="bank"),
            rate_limit(4),
            act(5, "run_settlement", eval={"new_failure_exposed": True}, mode="resume"),
            plan(6, 2, [5]),
            act(7, "set_config", "rejected", component="settlement", key="token", value="guess-999"),
            act(8, "set_config", component="bank", key="key_in_use", value="key-abc123", eval={"faults_active_after": []}),
            ev(9, "ERROR", error="agent replied without a tool call; nudged"),
            act(10, "run_settlement", mode="resume", eval={"faults_active_after": []}),
            obs(11, "check_pipeline", "Payouts sent: 20/20"),
            ev(12, "VERIFY", args={}, result="verification PASSED", outcome="pass", checks={"V1": True, "V2": True, "V3": True}),
            ev(13, "FINAL", t=33, outcome="VERIFIED", result="goal verified",
               metrics={"llm_calls": 10, "llm_errors": 1, "input_tokens": 900, "output_tokens": 100,
                        "total_tokens": 1000, "latency_s": 12.0},
               eval={"goal_met": True, "duplicates": 0, "faults_active": []})]


def test_measured_and_derived_values_on_a_verified_run():
    a = analyse_run(verified_run())
    m, d = a["measured"], a["derived"]
    assert m["final_outcome"] == "VERIFIED" and m["goal_met"] is True and m["duplicates"] == 0
    assert m["actions"] == 4 and m["actions_by_outcome"] == {"ok": 3, "refused": 0, "rejected": 1}
    assert m["verifier"] == {"submitted": 1, "passed": 1, "last_checks": {"V1": True, "V2": True, "V3": True}}
    assert m["payouts_sent_last_observed"] == "20/20"
    assert (m["rate_limit_retries"], m["other_llm_errors"], m["nudges"]) == (1, 0, 1)
    assert m["wall_clock_s"] == 32.0
    assert d["action_validity_rate"] == 0.75
    assert d["non_llm_wall_clock_s"] == 20.0 and d["tokens_per_llm_call"] == 100.0
    assert d["inspected_before_act"] == {"component_actions": 2, "inspected_first": 1, "rate": 0.5,
                                         "not_inspected_first": [7]}
    assert d["after_all_faults_cleared"]["cleared_at"] == 8
    assert d["after_all_faults_cleared"]["settlement_after"] == [10]
    assert d["after_all_faults_cleared"]["check_pipeline_after"] == [11]
    assert d["replan_citations"][0]["cited"][0]["seq"] == 5
    assert a["spec_metrics"]["goal_success"] is True and a["unavailable"] == {}


def test_failure_responses_window_and_errors_are_not_steps():
    events = verified_run()
    fr = {f["seq"]: f for f in failure_responses(events)}
    assert set(fr) == {5, 7}
    assert fr[5]["kinds"] == ["new_failure_exposed"] and fr[5]["next_step"] == "PLAN (#6)"
    assert fr[5]["replanned_within_window"] and fr[5]["counted_by_spec_metric"]
    assert fr[7]["kinds"] == ["rejected"] and fr[7]["next_step"] == "ACT set_config (#8)"
    assert not fr[7]["replanned_within_window"] and not fr[7]["counted_by_spec_metric"]


def test_replan_outside_window_is_not_counted():
    events = [GOAL, plan(2, 1), act(3, "run_settlement", eval={"new_failure_exposed": True}, mode="resume"),
              rate_limit(4), obs(5, "inspect", component="bank"), obs(6, "inspect", component="ledger"), plan(7, 2, [3])]
    assert failure_responses(events)[0]["replanned_within_window"] is False


def test_set_config_grounding_rules():
    g = {x["seq"]: x for x in set_config_grounding(verified_run())}
    assert g[7]["key_seen_before"] is False and g[7]["value_seen_before"] is False  # guessed key and value
    assert g[8]["key_seen_before"] is True and g[8]["value_seen_before"] is True
    short = [GOAL, obs(2, "inspect", "max_concurrency: 9"), act(3, "set_config", component="bank",
                                                                key="max_concurrency", value="5")]
    assert set_config_grounding(short)[0]["value_seen_before"] is None  # too short to be evidence
    partial = [GOAL, obs(2, "inspect", "id: cred-a101"), act(3, "set_config", component="bank", key="id", value="cred-a1")]
    assert set_config_grounding(partial)[0]["value_seen_before"] is False  # whole-word match only


def test_repeated_rejected_action_ignores_why():
    a1 = act(2, "restart", "rejected", component="settlement")
    a2 = {**act(3, "restart", "rejected", component="settlement"), "why": "different reason"}
    a3 = act(4, "restart", "rejected", component="worker")
    assert analyse_run([GOAL, a1, a2, a3])["derived"]["repeated_rejected_actions"] == [3]


def test_event_order_is_normalised_and_reported():
    events = verified_run()
    shuffled = events[:]
    random.Random(0).shuffle(shuffled)
    a, b = analyse_run(events), analyse_run(shuffled)
    assert a["measured"] == b["measured"] and a["derived"] == b["derived"]
    assert integrity(shuffled)["seq_in_file_order"] is False and integrity(events)["seq_in_file_order"] is True
    gap = [e for e in events if e["seq"] != 4]
    assert integrity(gap)["seq_contiguous"] is False


def test_incomplete_log_without_final():
    events = verified_run()[:6] + [rate_limit(7), rate_limit(8)]
    a = analyse_run(events)
    assert a["integrity"]["complete"] is False and a["measured"]["final_outcome"] is None
    assert "final" in a["unavailable"]
    assert a["spec_metrics"]["goal_success"] is False  # existing metric: no FINAL -> goal not met
    last = timeline(events)[-1]
    assert last["stage"] == "log ends" and last["errors_before"] == {"rate_limit_retries": 2}


def test_log_without_goal_does_not_crash():
    a = analyse_run([obs(1, "check_pipeline", "x"), ev(2, "FINAL", outcome="FAILED", result="r")])
    assert a["spec_metrics"] is None and "spec_metrics" in a["unavailable"] and a["arm"] is None


def test_failed_run_with_faults_cleared_is_not_success():
    events = [GOAL, plan(2, 1), act(3, "restart", component="bank", eval={"faults_active_after": []}),
              act(4, "restart", component="bank", eval={"faults_active_after": [], "no_effect": True}),
              ev(5, "FINAL", outcome="FAILED", result="step limit (30 LLM steps) reached",
                 metrics={"llm_calls": 30, "total_tokens": 1, "latency_s": 1.0},
                 eval={"goal_met": False, "duplicates": 0, "faults_active": []})]
    a = analyse_run(events)
    assert a["measured"]["goal_met"] is False and a["measured"]["faults_active_at_end"] == []
    assert a["spec_metrics"]["goal_success"] is False
    assert a["measured"]["verifier"]["submitted"] == 0
    assert a["unavailable"]["verifier"].startswith("no report was submitted")
    assert a["derived"]["after_all_faults_cleared"] == {"cleared_at": 3, "cleared_by": "restart(component=bank)",
                                                        "settlement_after": [], "check_pipeline_after": [],
                                                        "steps_after": 1}


def test_baseline_arms_report_unavailable_not_zero():
    g = ev(1, "GOAL", goal="g", eval={"scenario": "s", "seed": 1, "faults": ["F1"], "arm": "runbook"})
    fin = ev(3, "FINAL", outcome="GOAL_MET", result="ok", metrics={"llm_calls": 0, "latency_s": 0.0},
             eval={"goal_met": True, "duplicates": 0, "faults_active": []})
    a = analyse_run([g, act(2, "restart", component="worker"), fin])
    assert a["arm"] == "runbook" and a["measured"]["verifier"] is None
    assert {"llm_tokens_latency", "plans_and_replanning", "verifier"} <= set(a["unavailable"])
    assert a["derived"]["non_llm_wall_clock_s"] is None
    assert a["arm_source"] == "GOAL.eval.arm" and a["reason_source"].startswith("scripted")
    row = comparison_rows([a])[0]
    assert row["tokens"] == "n/a" and row["llm_latency_s"] == "n/a" and row["llm_calls"] == 0
    assert row["replan_in_time"] == "n/a" and row["run_id"] == "r1"


def test_cli_run_without_arm_is_labelled_with_its_default():
    a = analyse_run(verified_run())
    assert a["arm"] == "nidaan" and a["arm_source"].startswith("default 'nidaan'")
    assert a["reason_source"].startswith("agent-supplied")


def test_only_provider_rate_limits_count_as_rate_limit_retries():
    quoted = ev(3, "ERROR", error="LLM call failed (attempt 1): BadRequestError: Error code: 400 - tool_use_failed "
                                  "failed_generation: '... 429 Too Many Requests ...'")
    gemini = ev(4, "ERROR", error="LLM call failed (attempt 1): GoogleRateLimitError: 429 RESOURCE_EXHAUSTED")
    unavailable = ev(5, "ERROR", error="LLM call failed (attempt 1): GoogleAPIError: 503 UNAVAILABLE")
    m = analyse_run([GOAL, rate_limit(2), quoted, gemini, unavailable])["measured"]
    assert (m["rate_limit_retries"], m["other_llm_errors"]) == (2, 2)
    rows = timeline([GOAL, rate_limit(2), quoted, obs(6, "check_pipeline")])
    assert rows[-1]["errors_before"] == {"rate_limit_retries": 1, "other_errors": 1}


def test_markdown_labels_reasons_and_evaluation_only_fields():
    g = ev(1, "GOAL", goal="g", eval={"scenario": "s", "seed": 1, "faults": ["F1"], "arm": "oneshot"})
    base = [g, act(2, "restart", component="worker"),
            ev(3, "FINAL", outcome="GOAL_NOT_MET", result="r", metrics={"llm_calls": 1, "total_tokens": 5, "latency_s": 1.0},
               eval={"goal_met": False, "duplicates": 0, "faults_active": ["F1"]})]
    runs = [analyse_run(verified_run()), analyse_run(base)]
    runs[1]["run_id"] = "r2"
    md = render_markdown(runs, {"r1": timeline(verified_run()), "r2": timeline(base)}, inputs=["x.json"])
    assert "| stated why (LLM) |" in md and "| scripted reason |" in md
    assert "**not** LLM-generated reasoning" in md and "*(evaluation-only state, read after the run)*" in md
    assert "{'" not in md  # no raw Python dict text in the report
    assert md.count("## nidaan · s") == 1 and md.count("## oneshot · s") == 1
    assert "\\n" not in md and "**Inputs** (2 runs)" in md  # no literal backslash-n in cells
    for block in md.split("\n\n"):  # every table row has the header's column count
        rows = [ln for ln in block.splitlines() if ln.startswith("|")]
        assert len({ln.replace("\\|", "").count("|") for ln in rows}) <= 1


def test_timeline_folds_errors_into_next_step_and_keeps_flags():
    rows = timeline(verified_run())
    by = {r["seq"]: r for r in rows}
    assert by[5]["errors_before"] == {"rate_limit_retries": 1} and by[5]["eval_flags"] == ["new_failure_exposed"]
    assert by[6]["stage"] == "replan" and by[10]["errors_before"] == {"nudges": 1}
    assert by[12]["stage"] == "verify [pass]" and by[12]["environment_response"] == "V1✓ V2✓ V3✓"
    assert [r["seq"] for r in rows] == sorted(r["seq"] for r in rows)
    assert 4 not in by and 9 not in by  # ERROR events are folded, not rows


def _cli():
    spec = importlib.util.spec_from_file_location("analyse_traces", os.path.join(ROOT, "scripts", "analyse_traces.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_cli_writes_reports_refuses_overwrite_and_flags_unreadable(tmp_path):
    log = tmp_path / "r1.jsonl"
    log.write_text("".join(json.dumps(e) + "\n" for e in verified_run()))
    out = tmp_path / "rep" / "a.md"
    cli = _cli()
    assert cli.main(["--log", str(log), "--out", str(out)]) == 0
    data = json.loads((tmp_path / "rep" / "a.json").read_text())
    assert data["analyses"][0]["measured"]["final_outcome"] == "VERIFIED" and data["unreadable"] == []
    text = out.read_text()
    assert "## Comparison" in text and "Timeline" in text and "## Definitions" in text
    with pytest.raises(SystemExit):
        cli.main(["--log", str(log), "--out", str(out)])
    empty = tmp_path / "empty.jsonl"
    empty.write_text("")
    assert cli.main(["--log", str(log), str(empty)]) == 1
