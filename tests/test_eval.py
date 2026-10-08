import ast
import itertools
import json
import pathlib

import pytest

from baselines.common import LoggedTools, start_run
from baselines.oneshot import build_snapshot, execute_actions, parse_action_list
from evaluation.aggregate import aggregate, load_results, save_results, summarize
from evaluation.ground_truth import TRUTH_COMPONENT
from evaluation.harness import Scenario, run_arm
from evaluation.metrics import (DEFINITIONS, appropriate_replanning, batch_status_checks,
                                compute_run_metrics, replan_detail)
from evaluation.wilson import wilson
from nidaan.logger import RunLogger, read_jsonl
from settlesim.generator import DEV_FAULTS, HERO_FAULTS, HERO_SEED, generate

ROOT = pathlib.Path(__file__).resolve().parent.parent

# SPEC §9 official metric keys (nothing else may appear in the "spec" block)
SPEC_KEYS = {"goal_success", "duplicate_payouts", "refused_unsafe_attempts", "actions", "unnecessary_actions",
             "harmful_actions", "appropriate_replanning", "batch_status_checked_before_settlement",
             "root_cause_exact", "llm_calls", "total_tokens", "llm_latency_s"}


# ---- Wilson ----
def test_wilson_reference_values():
    w = wilson(5, 10)
    assert w["rate"] == 0.5 and w["ci_low"] == pytest.approx(0.2366, abs=1e-3)
    assert w["ci_high"] == pytest.approx(0.7634, abs=1e-3)
    z = wilson(0, 10)
    assert z["ci_low"] == 0 and z["ci_high"] == pytest.approx(0.2775, abs=1e-3)
    o = wilson(10, 10)
    assert o["ci_high"] == 1.0 and o["ci_low"] == pytest.approx(0.7225, abs=1e-3)
    assert wilson(0, 0) is None


# ---- metrics from hand-built events ----
def ev(seq, type, **kw):
    return {"seq": seq, "ts": f"2026-10-08T10:{seq // 60:02d}:{seq % 60:02d}+00:00", "run_id": "r",
            "type": type, **kw}


def act(seq, tool="restart", outcome="ok", **ann):
    return ev(seq, "ACT", tool=tool, outcome=outcome, eval=ann or None)


def plan(seq, v, outcome="ok"):
    return ev(seq, "PLAN", plan_version=v, outcome=outcome)


def obs(seq, tool="inspect"):
    return ev(seq, "OBSERVE", tool=tool)


def test_appropriate_replanning_in_time_vs_missed():
    events = [ev(1, "GOAL"), plan(2, 1),
              act(3, new_failure_exposed=True),  # falsifying: replanned within 2 steps (ERROR not a step)
              ev(4, "ERROR"), obs(5), plan(6, 2),
              act(7, no_effect=True),  # falsifying: 3 steps pass before the next plan
              obs(8), obs(9), obs(10), plan(11, 3)]
    assert appropriate_replanning(events) == {"falsifying_events": 2, "replanned_in_time": 1}
    assert appropriate_replanning([ev(1, "GOAL"), act(2)]) is None  # arms without plans
    rejected_plan = [ev(1, "GOAL"), plan(2, 1), act(3, harmful=True), plan(4, 2, outcome="rejected")]
    assert appropriate_replanning(rejected_plan)["replanned_in_time"] == 0  # only accepted plans count


def test_replan_after_evidence_gathering_is_not_judged_spurious():
    # v2 follows pure evidence-gathering (no falsifying event): described, never labelled spurious
    events = [ev(1, "GOAL"), plan(2, 1), obs(3), obs(4), obs(5), plan(6, 2),
              act(7, new_failure_exposed=True), plan(8, 3), plan(9, 4, outcome="rejected")]
    d = replan_detail(events)
    assert d == {"replans_accepted": 2, "replans_after_a_falsifying_event": 1,
                 "replans_without_a_falsifying_event_since_previous_plan": 1, "plan_updates_rejected": 1}
    assert replan_detail([ev(1, "GOAL"), act(2)]) is None
    assert "spurious" not in json.dumps(compute_run_metrics(
        [ev(1, "GOAL", eval={"faults": []}), *events, ev(90, "FINAL", eval={})]))
    assert "UNDEFINED" in DEFINITIONS["spurious_replans"]


def test_batch_status_checked_before_each_settlement():
    s = lambda q, **k: ev(q, "ACT", tool="run_settlement", outcome="ok", **k)  # noqa: E731
    g = lambda q: ev(q, "OBSERVE", tool="get_batch_status")  # noqa: E731
    assert batch_status_checks([g(1), s(2), s(3), g(4), s(5)]) == {
        "settlement_runs": 3, "settlement_runs_with_batch_check": 2, "always_checked": False}
    assert batch_status_checks([obs(1)])["always_checked"] is None


def run_events(acts, faults=("F1",), arm="nidaan", metrics=None, final_eval=None, extra=()):
    return ([ev(1, "GOAL", eval={"arm": arm, "faults": list(faults)})] + list(acts) + list(extra) +
            [ev(90, "FINAL", outcome="X", metrics=metrics or {},
                eval=final_eval or {"goal_met": True, "duplicates": 0})])


def test_spec_and_supplementary_blocks_are_separate():
    acts = [act(2, outcome="refused", refusal=True), act(3, no_effect=True), act(4, harmful=True),
            act(5, outcome="rejected"), act(6, progress=True)]
    m = compute_run_metrics(run_events(acts, final_eval={"goal_met": False, "duplicates": 2},
                                       metrics={"llm_calls": 7, "total_tokens": "unavailable",
                                                "latency_s": 3.5, "input_tokens": 9}))
    assert set(m["spec"]) == SPEC_KEYS
    s, x = m["spec"], m["supplementary"]
    assert (s["goal_success"], s["duplicate_payouts"], s["actions"]) == (False, 2, 5)
    assert s["refused_unsafe_attempts"] == 1 and s["harmful_actions"] == 1
    assert s["unnecessary_actions"] == 1  # executed + no_effect + not harmful
    assert s["llm_calls"] == 7 and s["total_tokens"] is None and s["llm_latency_s"] == 3.5
    # wall-clock, tool steps, outcome breakdown, token split live only in the supplementary block
    assert x["wall_clock_s"] == 89.0 and x["tool_steps"] == 5
    assert (x["actions_ok"], x["actions_refused"], x["actions_rejected"]) == (3, 1, 1)
    assert x["input_tokens"] == 9
    assert not ({"wall_clock_s", "tool_steps", "actions_ok"} & set(s))


def test_root_cause_exact_only_for_nidaan_with_known_faults():
    def verify(components):
        return ev(50, "VERIFY", args={"root_causes": [{"component": c} for c in components]})

    def rc(**kw):
        return compute_run_metrics(run_events(**kw))["spec"]["root_cause_exact"]
    assert rc(acts=[], faults=("F1", "F7"), extra=[verify(["bank"])]) is True
    assert rc(acts=[], faults=("F1", "F6"), extra=[verify(["bank"])]) is False
    assert rc(acts=[], faults=("F1",)) is False  # no report submitted
    assert rc(acts=[], arm="runbook") is None
    assert rc(acts=[], faults=("X9",), extra=[verify(["bank"])]) is None  # no truth data -> N/A


# ---- evaluation-only data stays out of agent-accessible code ----
def _imports(path: pathlib.Path) -> set[str]:
    names = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return names


def test_agent_accessible_code_never_imports_evaluation():
    for pkg in ("nidaan", "settlesim", "baselines"):
        for f in (ROOT / pkg).glob("*.py"):
            assert "evaluation" not in _imports(f), f"{f} imports evaluation"
            assert "TRUTH_COMPONENT" not in f.read_text(), f"{f} references ground truth"


def test_truth_map_is_development_only():
    assert set(TRUTH_COMPONENT) <= set(DEV_FAULTS)


# ---- runbook (no LLM) ----
def combos():
    for k in range(1, len(DEV_FAULTS) + 1):
        yield from itertools.combinations(DEV_FAULTS, k)


@pytest.mark.parametrize("faults", list(combos()), ids=lambda c: "+".join(c))
def test_runbook_solves_every_dev_combination(tmp_path, faults):
    for seed in (1, 2, 3):
        rec = run_arm("runbook", Scenario("t", seed, list(faults)), runs_dir=str(tmp_path))
        s, x = rec["metrics"]["spec"], rec["metrics"]["supplementary"]
        assert s["goal_success"] and s["duplicate_payouts"] == 0, (faults, seed)
        assert s["harmful_actions"] == 0 and x["actions_refused"] == 0 and x["actions_rejected"] == 0
        assert s["batch_status_checked_before_settlement"]["always_checked"] in (True, None)
        assert s["llm_calls"] == 0 and s["total_tokens"] == 0


def test_runbook_hero_is_logged_in_shared_format(tmp_path):
    rec = run_arm("runbook", Scenario("hero", HERO_SEED, list(HERO_FAULTS)), runs_dir=str(tmp_path))
    events = read_jsonl(rec["log_path"])
    assert {e["type"] for e in events} <= {"GOAL", "OBSERVE", "ACT", "FINAL"}
    assert [e["seq"] for e in events] == list(range(1, len(events) + 1))
    s = rec["metrics"]["spec"]
    assert s["appropriate_replanning"] is None and rec["metrics"]["supplementary"]["replan_detail"] is None
    assert s["batch_status_checked_before_settlement"]["always_checked"] is True
    assert s["batch_status_checked_before_settlement"]["settlement_runs"] >= 2 and s["actions"] >= 4
    modes = [e["args"]["mode"] for e in events if e.get("tool") == "run_settlement"]
    assert modes[-1] == "resume" and s["duplicate_payouts"] == 0


def test_run_arm_rejects_unknown_arm_and_takes_any_scenario(tmp_path):
    with pytest.raises(ValueError):
        run_arm("magic", Scenario("t", 1, ["F1"]), runs_dir=str(tmp_path))
    rec = run_arm("runbook", Scenario("anything-supplied-later", 99, ["F4", "F2"]), runs_dir=str(tmp_path))
    assert rec["scenario"] == "anything-supplied-later" and rec["metrics"]["spec"]["goal_success"]


# ---- one-shot helpers (no LLM) ----
def test_parse_action_list_lenient():
    txt = 'Sure:\n```json\n[{"tool": "restart", "args": {"component": "worker"}}]\n```'
    assert parse_action_list(txt) == [{"tool": "restart", "args": {"component": "worker"}}]
    assert parse_action_list("no json here") == [] and parse_action_list("[not json]") == []
    assert parse_action_list('{"tool": "restart"}') == []


def test_snapshot_is_generous_and_executes_blindly(tmp_path):
    sim = generate(HERO_SEED, list(HERO_FAULTS))
    lg = RunLogger("o", str(tmp_path))
    t = LoggedTools(sim, lg)
    start_run(lg, "oneshot", {"faults": list(HERO_FAULTS)})
    snap = build_snapshot(t)
    assert [e.get("tool") for e in lg.events].count("inspect") == 4 and len(lg.events) == 1 + 9
    assert "logs: bank" in snap
    actions = [{"tool": "restart", "args": {"component": "worker"}},
               {"tool": "run_task", "args": {"component": "bank", "task": "rotate_credential"}},
               {"tool": "run_settlement", "args": {"mode": "resume"}},
               {"tool": "bogus", "args": {}}, "junk"]
    assert execute_actions(t, actions) == 2
    assert not sim.goal_met() and sim.sent_count() == 8  # stopped by the rate limit; no replanning
    lg.log("FINAL", outcome="GOAL_NOT_MET", metrics={},
           eval={"goal_met": sim.goal_met(), "duplicates": len(sim.duplicates())})
    m = compute_run_metrics(lg.events)
    assert m["arm"] == "oneshot" and not m["spec"]["goal_success"]
    assert m["supplementary"]["actions_rejected"] == 2 and m["spec"]["actions"] == 5


# ---- aggregation ----
def rec(arm, scenario, faults, success, spec=None, supp=None):
    sp = {"goal_success": success, "duplicate_payouts": 0, "refused_unsafe_attempts": 1, "actions": 1,
          "unnecessary_actions": 1, "harmful_actions": 1, "appropriate_replanning": None,
          "batch_status_checked_before_settlement": {"always_checked": True}, "root_cause_exact": None,
          "llm_calls": 0, "total_tokens": 0, "llm_latency_s": 0.0, **(spec or {})}
    su = {"wall_clock_s": 1.0, "tool_steps": 1, "actions_ok": 1, "actions_refused": 1, "actions_rejected": 1,
          "input_tokens": 0, "output_tokens": 0, "final_outcome": "X", "replan_detail": None, **(supp or {})}
    return {"arm": arm, "scenario": scenario, "seed": 1, "faults": faults, "repeat": 1, "run_id": "x",
            "log_path": "p", "metrics": {"arm": arm, "spec": sp, "supplementary": su}}


def test_aggregate_separates_arms_scenarios_and_known_vs_held_out(tmp_path):
    rep = {"falsifying_events": 2, "replanned_in_time": 1}
    det = {"replans_accepted": 1, "replans_after_a_falsifying_event": 1,
           "replans_without_a_falsifying_event_since_previous_plan": 0, "plan_updates_rejected": 2}
    records = [
        rec("nidaan", "A", ["F1"], True, {"appropriate_replanning": rep, "root_cause_exact": True,
                                          "llm_calls": 10, "total_tokens": None}, {"replan_detail": det}),
        rec("nidaan", "A", ["F1"], False, {"appropriate_replanning": rep, "root_cause_exact": False,
                                           "llm_calls": 20, "total_tokens": 500}, {"replan_detail": det}),
        rec("runbook", "A", ["F1"], True),
        rec("oneshot", "A", ["F1"], False, {"duplicate_payouts": 3}),
        rec("nidaan", "B", ["F1", "X9"], True),  # contains a type outside the development set
        rec("runbook", "B", ["F1", "X9"], False),
    ]
    s = aggregate(records)
    assert set(s["by_arm"]) == {"nidaan", "runbook", "oneshot"}
    n = s["by_arm"]["nidaan"]
    assert n["n_runs"] == 3 and set(n) == {"n_runs", "spec", "supplementary"}
    sp = n["spec"]
    assert sp["goal_success"]["k"] == 2 and sp["goal_success"]["n"] == 3
    assert sp["root_cause_component_accuracy"]["n"] == 2 and sp["appropriate_replanning"]["n"] == 4
    assert sp["counts"]["llm_calls"]["mean"] == pytest.approx(10.0)  # (10 + 20 + 0) / 3
    assert sp["counts"]["total_tokens"] == {"mean": 250.0, "total": 500, "n_available": 2}  # None excluded
    assert "wall_clock_s" not in sp["counts"] and "wall_clock_s" in n["supplementary"]["counts"]
    assert n["supplementary"]["replan_detail_totals"]["plan_updates_rejected"] == 4
    assert s["by_arm"]["oneshot"]["spec"]["runs_with_zero_duplicates"]["k"] == 0
    assert set(s["by_scenario"]) == {"A", "B"} and set(s["by_scenario"]["A"]) == {"nidaan", "runbook", "oneshot"}
    assert s["split_known_vs_held_out"]["known"]["nidaan"]["n_runs"] == 2
    assert s["split_known_vs_held_out"]["held_out"]["runbook"]["spec"]["goal_success"]["k"] == 0
    assert "oneshot" not in s["split_known_vs_held_out"]["held_out"]
    assert "spurious_replans" in s["definitions"] and "spurious" not in json.dumps(
        {k: v for k, v in s.items() if k != "definitions"})

    out = tmp_path / "results" / "r.json"
    save_results(str(out), records, s)
    back = load_results(str(out))
    assert back["summary"] == json.loads(json.dumps(s)) and len(back["records"]) == 6


def test_summarize_handles_empty_applicable_sets():
    s = summarize([rec("runbook", "A", ["F1"], True)])["spec"]
    assert s["root_cause_component_accuracy"] is None and s["appropriate_replanning"] is None
    assert s["goal_success"]["rate"] == 1.0
