"""Offline tests for ui/live.py. No network and no LLM requests.

The runbook arm is used for real end-to-end runs (it makes no LLM calls). The only "nidaan" test uses a
stub whose invoke() raises a non-retryable error, to check that an agent-side failure is reported honestly;
it never produces a model reply or a tool call.
"""
import os
import pathlib
import threading

import pytest

import ui.live as live
from nidaan.logger import read_jsonl

ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _no_leftover_run():
    """Every test starts and ends with the process-wide lock free."""
    assert not live.is_busy()
    yield
    run = live.current_run()
    if run is not None:
        run.wait(30)
    assert not live.is_busy()


def _blocking_runbook(monkeypatch, gate: threading.Event, started: threading.Event):
    """Replace run_runbook with one that logs a GOAL event, then waits for the test to release it."""
    import baselines.runbook as rb

    def fake(sim, logger, info):
        logger.log("GOAL", goal="test goal", eval={**info, "arm": "runbook"})
        started.set()
        assert gate.wait(10)
        logger.log("FINAL", outcome="GOAL_NOT_MET", result="test stop")
        return {"reason": "test stop"}

    monkeypatch.setattr(rb, "run_runbook", fake)


def test_import_is_inert():
    # Importing must not start a run or build a model client.
    assert live.current_run() is None or not live.current_run().running
    assert not live.is_busy()


def test_runbook_live_run_succeeds_and_matches_log(tmp_path):
    run = live.start_live_run("runbook", "hero", runs_dir=tmp_path)
    assert run.wait(30)
    snap = run.snapshot()
    assert snap["status"] == "completed" and snap["error"] is None
    assert snap["verdict"] == "GOAL_MET" and snap["final_outcome"] == "GOAL_MET"
    fs = snap["final_state"]
    assert fs["goal_met"] and fs["duplicates"] == 0 and fs["faults_active"] == []
    assert fs["payouts_sent"] == fs["payouts_total"] == 20
    assert snap["initial_state"]["goal_met"] is False and snap["initial_state"]["payouts_sent"] == 0
    # Streamed events are exactly the events written to the JSONL log (schema unchanged).
    assert snap["events"] == read_jsonl(snap["log_path"])
    types = [e["type"] for e in snap["events"]]
    assert types[0] == "GOAL" and types[-1] == "FINAL"
    assert snap["agent_claim"] is None and snap["verification"] is None  # runbook submits no report


def test_events_arrive_incrementally_while_running(tmp_path, monkeypatch):
    gate, started = threading.Event(), threading.Event()
    _blocking_runbook(monkeypatch, gate, started)
    run = live.start_live_run("runbook", "dev_f2", runs_dir=tmp_path)
    assert started.wait(10)
    mid = run.snapshot()
    assert mid["status"] == "running" and mid["verdict"] is None and mid["final_state"] is None
    assert [e["type"] for e in mid["events"]] == ["GOAL"]
    gate.set()
    assert run.wait(10)
    assert [e["type"] for e in run.snapshot()["events"]] == ["GOAL", "FINAL"]


def test_second_concurrent_run_is_refused(tmp_path, monkeypatch):
    gate, started = threading.Event(), threading.Event()
    _blocking_runbook(monkeypatch, gate, started)
    first = live.start_live_run("runbook", "hero", runs_dir=tmp_path)
    assert started.wait(10) and live.is_busy()
    with pytest.raises(live.LiveRunBusy):
        live.start_live_run("runbook", "dev_f4", runs_dir=tmp_path)
    gate.set()
    assert first.wait(10)
    assert not live.is_busy()  # lock released; a new run would now be allowed


@pytest.mark.parametrize("name", ["F3", "heldout", "custom", "", "hero; F8"])
def test_unknown_or_non_development_scenarios_are_rejected(name, tmp_path):
    with pytest.raises(ValueError):
        live.LiveRun("runbook", name, runs_dir=tmp_path)
    assert not live.is_busy()


def test_scenario_with_non_development_fault_is_refused(monkeypatch, tmp_path):
    from evaluation.harness import Scenario
    monkeypatch.setattr(live, "dev_scenarios", lambda: {"x": Scenario("x", 1, ["F1", "F3"])})
    with pytest.raises(ValueError, match="non-development"):
        live.LiveRun("runbook", "x", runs_dir=tmp_path)


def test_unknown_mode_rejected(tmp_path):
    with pytest.raises(ValueError):
        live.LiveRun("oneshot", "hero", runs_dir=tmp_path)


def test_logs_are_isolated_from_runs_dir(tmp_path):
    assert live.LIVE_RUNS_DIR.resolve() != (ROOT / "runs").resolve()
    before = sorted(os.listdir(ROOT / "runs")) if (ROOT / "runs").exists() else []
    run = live.start_live_run("runbook", "dev_f7", runs_dir=tmp_path)
    assert run.wait(30)
    assert pathlib.Path(run.log_path).parent == tmp_path
    assert pathlib.Path(run.log_path).name.startswith("live-runbook-dev_f7-")
    after = sorted(os.listdir(ROOT / "runs")) if (ROOT / "runs").exists() else []
    assert before == after


def test_exception_in_run_is_reported_redacted_and_releases_lock(tmp_path, monkeypatch):
    import baselines.runbook as rb

    def boom(sim, logger, info):
        raise RuntimeError("simulated failure with key gsk_ABCDEF123456 and org_xyz789")

    monkeypatch.setattr(rb, "run_runbook", boom)
    run = live.start_live_run("runbook", "hero", runs_dir=tmp_path)
    assert run.wait(10)
    snap = run.snapshot()
    assert snap["status"] == "error" and snap["verdict"] == "ERROR"
    assert "simulated failure" in snap["error"]
    assert "gsk_ABCDEF123456" not in snap["error"] and "org_xyz789" not in snap["error"]
    assert not live.is_busy()


class _FailingLLM:
    """Stub for the error path only: every invoke() raises a non-retryable error. No reply is ever made."""

    def invoke(self, messages):
        raise ValueError("400 bad request (stub)")


def test_nidaan_agent_failure_is_reported_as_error_not_success(tmp_path):
    run = live.LiveRun("nidaan", "hero", runs_dir=tmp_path, llm=_FailingLLM()).start()
    assert run.wait(30)
    snap = run.snapshot()
    assert snap["status"] == "completed"  # the agent handled the error and ended the run itself
    # A provider error stops the run: ERROR (incomplete), never success. The logged FINAL outcome is unchanged.
    assert snap["verdict"] == "ERROR" and snap["final_outcome"] == "FAILED"
    assert snap["llm_failure"]["kind"] == "fatal"
    assert snap["result"]["status"] == "FAILED" and "LLM error" in snap["result"]["reason"]
    assert any(e["type"] == "ERROR" for e in snap["events"])
    assert snap["verification"] is None and snap["agent_claim"] is None
    assert snap["final_state"]["goal_met"] is False


def test_nidaan_without_key_is_refused_before_any_run(tmp_path, monkeypatch):
    monkeypatch.setattr(live, "provider_key_present", lambda: False)
    with pytest.raises(RuntimeError, match="no API key"):
        live.LiveRun("nidaan", "hero", runs_dir=tmp_path).start()
    assert not live.is_busy()
    assert not list(tmp_path.iterdir())  # no log file was created


@pytest.mark.parametrize("mode,done,error,verify,goal,expected", [
    ("nidaan", False, None, None, None, None),
    ("nidaan", True, "x", None, True, "ERROR"),
    ("nidaan", True, None, {"outcome": "pass"}, True, "VERIFIED"),
    ("nidaan", True, None, {"outcome": "pass"}, False, "FAILED"),   # never trust a pass the sim contradicts
    ("nidaan", True, None, {"outcome": "fail"}, True, "FAILED"),
    ("nidaan", True, None, None, True, "FAILED"),                   # no verifier pass, no success claim
    ("runbook", True, None, None, True, "GOAL_MET"),
    ("runbook", True, None, None, False, "GOAL_NOT_MET"),
])
def test_verdict_requires_independent_evidence(mode, done, error, verify, goal, expected):
    fs = None if goal is None else {"goal_met": goal}
    assert live.verdict(mode, done, error, verify, fs) == expected


def test_sim_state_exposes_per_payout_send_counts(tmp_path):
    run = live.start_live_run("runbook", "hero", runs_dir=tmp_path)
    assert run.wait(30)
    snap = run.snapshot()
    init, fin = snap["initial_state"]["payouts"], snap["final_state"]["payouts"]
    assert len(init) == len(fin) == 20
    assert all(p["send_count"] == 0 for p in init)
    assert all(p["send_count"] == 1 for p in fin)  # runbook hero: each payout exactly once
    assert sum(p["send_count"] >= 1 for p in fin) == snap["final_state"]["payouts_sent"]
    assert snap["verify_history"] == []  # runbook submits no report


def test_verify_history_lists_every_verifier_attempt():
    # A LiveRun shell (no simulator run, no thread) fed two VERIFY events through its queue.
    run = live.LiveRun.__new__(live.LiveRun)
    run.__dict__.update(mode="nidaan", scenario=type("S", (), {"name": "hero", "seed": 1, "faults": ["F1"]})(),
                        run_id="r", started_at=None, finished_at=None, log_path=None, error=None, result=None,
                        initial_state={}, _thread=object(), _events=[], _ev_lock=threading.Lock())
    import queue
    run._q = queue.Queue()
    for e in ({"seq": 5, "type": "VERIFY", "outcome": "fail", "checks": {"V1": False}, "result": "V1 failed",
               "args": {"status_claimed": "resolved"}},
              {"seq": 9, "type": "VERIFY", "outcome": "pass", "checks": {"V1": True}, "result": "verification PASSED",
               "args": {"status_claimed": "resolved"}}):
        run._q.put(e)
    run._done = threading.Event()  # still "running": no final state, no verdict
    run.sim = type("Sim", (), {"sent_count": lambda self: 0, "payouts": []})()
    snap = run.snapshot()
    assert [v["seq"] for v in snap["verify_history"]] == [5, 9]
    assert snap["verification"]["outcome"] == "pass" and snap["verdict"] is None
