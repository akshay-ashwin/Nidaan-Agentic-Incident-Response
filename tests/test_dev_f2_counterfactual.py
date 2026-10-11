"""ENVIRONMENT DIAGNOSTIC - not evidence of LLM success.

Deterministically replays the act calls of the failed Nidaan dev_f2 run
(runs/nidaan-dev_f2-s11-r1-20261010T130437328361.jsonl, events #7-#39) through the real ToolExecutor and
SettleSim, then appends one safe continuation (batch status, resume settlement, check_pipeline) and runs
the real deterministic verifier. It shows that after #39 the environment was one safe step from the goal;
it says nothing about whether an LLM would take that step. No LLM call is made.
"""
import glob
import os

import pytest

from nidaan.logger import RunLogger, read_jsonl
from nidaan.tools import ToolExecutor
from nidaan.verifier import verify
from settlesim.generator import generate
from settlesim.tools import SettleSimTools

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEV_F2 = (11, ["F2"])  # evaluation/scenarios.py: dev_f2
# (log seq, tool, args, expected outcome) of every act call up to #39, copied from the run log
RECORDED_ACTS = (
    (7, "run_settlement", {"mode": "resume"}, "ok"),
    (13, "run_task", {"component": "settlement", "task": "rotate_credential"}, "rejected"),
    (15, "run_task", {"component": "bank", "task": "rotate_credential"}, "ok"),
    (17, "restart", {"component": "settlement"}, "rejected"),
    (19, "run_settlement", {"mode": "resume"}, "ok"),
    (29, "set_config", {"component": "settlement", "key": "bank_credential_id", "value": "cred-a101"}, "rejected"),
    (31, "set_config", {"component": "settlement", "key": "credential_id", "value": "cred-a101"}, "rejected"),
    (35, "run_settlement", {"mode": "full"}, "ok"),
    (37, "run_task", {"component": "settlement", "task": "sync_clock"}, "rejected"),
    (39, "restart", {"component": "bank"}, "ok"),
)
META = {"llm_call": 0}


def _replay(tmp_path):
    sim = generate(*DEV_F2)
    lg = RunLogger("diag-dev_f2", str(tmp_path))
    ex = ToolExecutor(SettleSimTools(sim), lg)
    ex.execute("update_plan", {"steps": ["replay recorded actions"], "reason": "diagnostic", "triggered_by": []}, META)
    replayed = []
    for seq, tool, args, _ in RECORDED_ACTS:
        ex.execute(tool, {**args, "why": f"replay of #{seq}"}, META)
        replayed.append(lg.events[-1])
    return sim, lg, ex, replayed


def test_replay_reproduces_recorded_outcomes_and_fault_state(tmp_path):
    sim, _, _, replayed = _replay(tmp_path)
    for (seq, tool, _, outcome), ev in zip(RECORDED_ACTS, replayed):
        assert (ev["tool"], ev["outcome"]) == (tool, outcome), seq
        expected_faults = [] if seq == 39 else ["F2"]
        assert ev["eval"]["faults_active_after"] == expected_faults, seq
    assert sim.active_faults() == [] and not sim.goal_met()  # fault cleared, goal not yet met (as in the run)
    assert len(sim.duplicates()) == 0


def test_replay_matches_the_actual_log_when_available(tmp_path):
    paths = glob.glob(os.path.join(ROOT, "runs", "nidaan-dev_f2-s11-r1-20261010T130437328361.jsonl"))
    if not paths:
        pytest.skip("run log not present (runs/ is gitignored)")
    logged = {e["seq"]: e for e in read_jsonl(paths[0]) if e["type"] == "ACT"}
    assert sorted(s for s in logged if s <= 39) == [s for s, *_ in RECORDED_ACTS]
    _, _, _, replayed = _replay(tmp_path)
    for (seq, *_), ev in zip(RECORDED_ACTS, replayed):
        assert ev["args"] == logged[seq]["args"] and ev["outcome"] == logged[seq]["outcome"], seq
        assert ev["result"] == logged[seq]["result"], seq
        assert ev["eval"]["faults_active_after"] == logged[seq]["eval"]["faults_active_after"], seq


def test_one_safe_continuation_reaches_verified_goal_without_duplicates(tmp_path):
    sim, lg, ex, _ = _replay(tmp_path)
    status = ex.execute("get_batch_status", {"why": "check sent/pending before retrying"}, META)
    assert "Payouts sent more than once: none" in status
    out = ex.execute("run_settlement", {"mode": "resume", "why": "retry from the checkpoint"}, META)
    assert "20/20" in out
    pipe = ex.execute("check_pipeline", {"why": "confirm the goal"}, META)
    assert "G3 every payout sent exactly once: PASS" in pipe
    assert sim.goal_met() and len(sim.duplicates()) == 0 and sim.active_faults() == []
    ok_acts = [e["seq"] for e in lg.events if e["type"] == "ACT" and e["outcome"] == "ok"]
    report = {"status_claimed": "resolved", "actions": ok_acts, "summary": "diagnostic",
              "root_causes": [{"component": "bank", "description": "diagnostic", "evidence": []}]}
    res = verify(report, lg.events, sim)
    assert res.passed and res.checks == {"V1": True, "V2": True, "V3": True}
