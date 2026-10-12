import json
import pathlib

import pytest

from evaluation.harness import Scenario, run_arm
from evaluation.scenarios import DEV_SCENARIOS
from ui import data as D

ROOT = pathlib.Path(__file__).resolve().parent.parent


def write_log(path, events):
    path.write_text("\n".join(json.dumps(e) for e in events) + "\n")


def ev(seq, type, **kw):
    return {"seq": seq, "ts": f"2026-10-08T10:00:{seq:02d}+00:00", "run_id": "nidaan-x-s1-r2-t", "type": type, **kw}


def goal(faults, scenario="x", arm=None):
    info = {"scenario": scenario, "seed": 1, "faults": faults}
    if arm:
        info["arm"] = arm
    return ev(1, "GOAL", goal="g", eval=info)


@pytest.fixture
def runs(tmp_path):
    d = tmp_path / "runs"
    run_arm("runbook", DEV_SCENARIOS[1], runs_dir=str(d))  # real, local, deterministic
    write_log(d / "api.jsonl", [goal(["F2"], "dev_f2", "nidaan"),
                                ev(2, "ERROR", error="429"),
                                ev(3, "FINAL", outcome="FAILED", result="LLM error: 429 quota",
                                   metrics={"llm_calls": 0}, eval={"goal_met": False, "duplicates": 0})])
    write_log(d / "cut.jsonl", [goal(["F4"], "dev_f4", "nidaan"), ev(2, "OBSERVE", tool="inspect")])
    write_log(d / "sealed.jsonl", [goal(["F2", "X9"], "other", "nidaan"),
                                   ev(2, "FINAL", outcome="X", eval={"goal_met": True, "duplicates": 0})])
    write_log(d / "nofaults.jsonl", [goal([], "unknown")])
    (d / "corrupt.jsonl").write_text("not json\n")
    write_log(d / "nogoal.jsonl", [ev(2, "OBSERVE")])
    return str(d)


def test_records_built_from_logs_and_corrupt_logs_skipped(runs):
    recs = D.build_records(runs)
    assert len(recs) == 5  # corrupt + no-GOAL logs skipped, nothing raised
    by_id = {r["log_path"].split("/")[-1]: r for r in recs}
    assert by_id["api.jsonl"]["api_failure"] and not by_id["api.jsonl"]["incomplete"]
    assert by_id["cut.jsonl"]["incomplete"] and not by_id["cut.jsonl"]["api_failure"]
    assert by_id["api.jsonl"]["repeat"] == 2 and by_id["api.jsonl"]["arm"] == "nidaan"
    rb = next(r for r in recs if r["arm"] == "runbook")
    assert rb["metrics"]["spec"]["goal_success"] and not D.is_infra_failure(rb)


def test_non_development_and_unknown_runs_are_hidden_and_counted(runs):
    recs = D.build_records(runs)
    kept, counts = D.prepare(recs)
    assert all(D.is_dev_record(r) for r in kept)
    assert "sealed.jsonl" not in " ".join(r["log_path"] for r in kept)
    assert "nofaults.jsonl" not in " ".join(r["log_path"] for r in kept)
    assert counts["non_development_hidden"] == 2 and len(kept) == 3
    blob = json.dumps(kept)
    assert "X9" not in blob and "sealed" not in blob


def test_exclusion_toggle_is_explicit_and_default_includes_everything(runs):
    recs = D.build_records(runs)
    kept, c = D.prepare(recs)
    assert len(kept) == 3 and c["excluded_by_toggle"] == 0 and c["infrastructure_failures_in_view"] == 2
    kept2, c2 = D.prepare(recs, exclude_infra=True)
    assert len(kept2) == 1 and c2["excluded_by_toggle"] == 2 and c2["infrastructure_failures_total"] == 2


def test_summary_uses_existing_aggregation_and_counts_failures(runs):
    kept, _ = D.prepare(D.build_records(runs))
    s = D.summarize_records(kept)
    assert s["by_arm"]["nidaan"]["spec"]["goal_success"]["k"] == 0 and s["by_arm"]["nidaan"]["n_runs"] == 2
    assert s["by_arm"]["runbook"]["spec"]["goal_success"]["k"] == 1


def test_formatters_never_fabricate():
    assert D.fmt_ci(None) == "n/a"
    assert "2/4 = 50%" in D.fmt_ci({"k": 2, "n": 4, "rate": 0.5, "ci_low": 0.15, "ci_high": 0.85})
    assert "15%-85%" in D.fmt_ci({"k": 2, "n": 4, "rate": 0.5, "ci_low": 0.15, "ci_high": 0.85})
    assert D.fmt_count({"mean": None, "total": None, "n_available": 0}) == "unavailable"
    assert D.fmt_count({"mean": 2.0, "total": 4, "n_available": 2}) == "2.0 (n=2)"


def test_comparison_rows_separate_spec_from_supplementary_and_mark_missing(runs):
    kept, _ = D.prepare(D.build_records(runs))
    rows = D.comparison_rows(D.summarize_records(kept)["by_arm"])
    assert {r["Type"] for r in rows} == {"SPEC §9", "Supplementary"}
    labels_spec = [r["Metric"] for r in rows if r["Type"] == "SPEC §9"]
    labels_supp = [r["Metric"] for r in rows if r["Type"] == "Supplementary"]
    assert not any("Wall-clock" in x or "Tool steps" in x for x in labels_spec)
    assert any("Wall-clock" in x for x in labels_supp)
    assert all(r["oneshot"] == "no runs" for r in rows)  # no one-shot runs -> never fabricated
    replan = next(r for r in rows if r["Metric"].startswith("Appropriate replanning"))
    assert replan["runbook"] == "n/a (no plans)"
    rc = next(r for r in rows if r["Metric"].startswith("Root-cause"))
    assert rc["runbook"] == "n/a (Nidaan only)"
    tokens = next(r for r in rows if r["Metric"].startswith("Tokens"))
    assert tokens["nidaan"] == "0.0 (n=2)" or tokens["nidaan"] == "unavailable"


def test_comparison_rows_empty_input_is_all_no_runs():
    rows = D.comparison_rows({})
    assert all(r[a] == "no runs" for r in rows for a in ("nidaan", "runbook", "oneshot"))


def test_scenario_matrix_lists_every_dev_scenario_and_arm(runs):
    kept, _ = D.prepare(D.build_records(runs))
    rows = D.scenario_matrix(kept, DEV_SCENARIOS)
    assert [r["Scenario"] for r in rows] == [s.name for s in DEV_SCENARIOS]  # all six, no cherry-picking
    f2 = next(r for r in rows if r["Scenario"] == "dev_f2")
    assert f2["runbook"] == "1/1 succeeded" and f2["nidaan"] == "0/1 succeeded" and f2["oneshot"] == "no runs"
    assert next(r for r in rows if r["Scenario"] == "hero")["runbook"] == "no runs"


# ---- trace helpers ----
def test_field_split_separates_channels():
    e = ev(5, "ACT", tool="restart", args={"component": "worker"}, why="w", result="r", outcome="ok",
           plan_version=1, llm_call=3, latency_ms=10, tokens={"total": 5}, model="m",
           eval={"harmful": False, "faults_active_after": []})
    vis, meta, evo = D.split_event_fields(e)
    assert set(vis) == {"tool", "args", "why", "result", "outcome", "plan_version"}
    assert set(meta) == {"ts", "llm_call", "latency_ms", "tokens", "model"}
    assert evo == {"harmful": False, "faults_active_after": []}
    assert "eval" not in vis and "eval" not in meta


def test_verify_args_shown_as_the_agents_report_and_no_free_text_fields():
    vis, _, _ = D.split_event_fields(ev(9, "VERIFY", args={"summary": "s"}, outcome="pass", checks={"V1": True}))
    assert "report" in vis and "args" not in vis
    assert not ({"thought", "reasoning", "thinking"} & set(D.AGENT_VISIBLE_FIELDS + D.RUN_META_FIELDS))


def test_event_styles():
    assert D.event_style(ev(1, "PLAN", plan_version=1, outcome="ok"))["label"] == "PLAN"
    r = D.event_style(ev(2, "PLAN", plan_version=2, outcome="ok"))
    assert r["label"] == "REPLAN" and r["color"] == D.EVENT_COLORS["REPLAN"]
    assert D.event_style(ev(3, "PLAN", plan_version=2, outcome="rejected"))["label"] == "PLAN"
    ref = D.event_style(ev(4, "ACT", outcome="refused"))
    assert ref["refused"] and ref["border"] == "#dc2626" and ref["badge"] == "refused"
    assert D.event_style(ev(5, "ACT", outcome="ok"))["color"] == D.EVENT_COLORS["ACT"]


def test_loop_timeline_and_evidence_summary():
    events = [goal(["F1"]), ev(2, "PLAN", plan_version=1, outcome="ok"),
              ev(3, "OBSERVE", tool="check_pipeline", args={}),
              ev(4, "ACT", tool="run_settlement", args={"mode": "resume"}, outcome="ok",
                 eval={"new_failure_exposed": True}),
              ev(5, "ACT", tool="restart", args={"component": "ledger"}, outcome="refused"),
              ev(6, "PLAN", plan_version=2, outcome="ok", triggered_by=[4], diff={"added": ["a"], "removed": ["b"]}),
              ev(7, "PLAN", plan_version=2, outcome="rejected"),
              ev(8, "VERIFY", outcome="pass"),
              ev(9, "FINAL", outcome="VERIFIED", result="goal verified", eval={"goal_met": True},
                 metrics={"llm_calls": 4})]
    phases = [r["phase"] for r in D.loop_timeline(events)]
    assert phases == ["goal", "decide (initial plan)", "observe", "act -> environment exposed a new failure",
                      "act -> refused by a safety guard", "replan", "plan update rejected", "verify", "final"]
    s = D.evidence_summary(events)
    assert s["event_counts"]["PLAN"] == 3 and len(s["actions"]) == 2
    assert s["replans"] == 1 and s["plan_updates_rejected"] == 1
    assert s["replan_events"] == [{"seq": 6, "version": 2, "triggered_by": [4], "added": ["a"], "removed": ["b"]}]
    assert s["final"]["outcome"] == "VERIFIED" and s["final"]["llm_metrics"] == {"llm_calls": 4}
    assert D.evidence_summary([goal(["F1"])])["final"] is None


def test_headline_and_run_label():
    assert D.headline(ev(1, "ACT", tool="restart", args={"component": "worker", "x": None})) == \
        "restart(component=worker)"
    rec = {"arm": "nidaan", "scenario": "hero", "run_id": "rid", "api_failure": True,
           "metrics": {"supplementary": {"final_outcome": "FAILED"}}}
    assert D.run_label(rec) == "nidaan | hero | FAILED [API/quota failure] | rid"


def test_live_dashboard_runs_never_enter_recorded_aggregates(runs):
    import shutil
    from ui import live
    d = pathlib.Path(runs)
    run = live.start_live_run("runbook", "hero", runs_dir=d / "live_tmp")
    assert run.wait(30)
    shutil.copy(run.log_path, d / pathlib.Path(run.log_path).name)  # even if copied into runs/
    recs = D.build_records(runs)
    kept, counts = D.prepare(recs)
    assert counts["live_runs_hidden"] == 1
    assert not any(D.is_live_record(r) for r in kept)
    assert len(kept) == 3 and counts["non_development_hidden"] == 2  # recorded semantics unchanged
    assert D.summarize_records(kept)["by_arm"]["runbook"]["n_runs"] == 1


@pytest.mark.parametrize("arm,verifies,final_eval,api_error,expected", [
    ("nidaan", ["pass"], {"goal_met": True}, False, "VERIFIED"),
    ("nidaan", ["pass"], {"goal_met": False}, False, "FAILED"),   # a pass the simulator contradicts
    ("nidaan", ["fail"], {"goal_met": True}, False, "FAILED"),
    ("nidaan", ["pass", "fail"], {"goal_met": True}, False, "FAILED"),  # the last attempt counts
    ("nidaan", [], {"goal_met": True}, False, "FAILED"),          # no verifier pass, no success claim
    ("nidaan", [], {"goal_met": False}, True, "ERROR"),
    ("nidaan", ["pass"], None, False, "INCOMPLETE"),              # no FINAL event
    ("runbook", [], {"goal_met": True}, False, "GOAL_MET"),
    ("oneshot", [], {"goal_met": False}, False, "GOAL_NOT_MET"),
])
def test_recorded_verdict_requires_independent_evidence(arm, verifies, final_eval, api_error, expected):
    events = [goal(["F1"], "hero", arm)]
    for i, o in enumerate(verifies):
        events.append(ev(2 + i, "VERIFY", outcome=o, args={"status_claimed": "resolved"}))
    if final_eval is not None:
        events.append(ev(9, "FINAL", outcome="VERIFIED", eval=final_eval,
                         result="LLM error: 429" if api_error else "done"))
    assert D.recorded_verdict(arm, events) == expected


def test_no_recorded_run_is_labelled_verified_without_evidence():
    recs = D.build_records(str(ROOT / "runs"))
    for r in recs:
        events = D.read_jsonl(r["log_path"])
        if D.recorded_verdict(r["arm"], events) == "VERIFIED":
            last = [e for e in events if e["type"] == "VERIFY"][-1]
            final = [e for e in events if e["type"] == "FINAL"][-1]
            assert last["outcome"] == "pass" and final["eval"]["goal_met"] is True


def test_recorded_verification_keeps_claim_verifier_and_ground_truth_separate():
    events = [goal(["F1"], "hero", "nidaan"),
              ev(2, "VERIFY", outcome="pass", checks={"V1": True, "V2": True, "V3": True}, result="verification PASSED",
                 args={"status_claimed": "resolved", "root_causes": [{"component": "settlement"}]}),
              ev(3, "FINAL", outcome="VERIFIED", result="goal verified",
                 eval={"goal_met": True, "duplicates": 0, "faults_active": []})]
    rec = {"arm": "nidaan", "metrics": {"spec": {"root_cause_exact": False}}}
    v = D.recorded_verification(rec, events)
    assert v["verdict"] == "VERIFIED"
    assert v["agent_claim"]["root_causes"] == [{"component": "settlement"}]
    assert v["verify_history"] == [{"seq": 2, "outcome": "pass", "checks": {"V1": True, "V2": True, "V3": True},
                                    "message": "verification PASSED"}]
    assert v["ground_truth"] == {"goal_met": True, "duplicates": 0, "faults_active": []}
    assert v["root_cause_exact"] is False  # evaluation-only; a verified run can still name the wrong component
