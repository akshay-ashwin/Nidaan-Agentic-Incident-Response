import json

from nidaan.logger import EVENT_TYPES, RunLogger, agent_visible, read_jsonl
from nidaan.plan import PlanManager


# ---- logger ----
def test_event_types_are_the_seven_specified():
    assert EVENT_TYPES == ("GOAL", "PLAN", "OBSERVE", "ACT", "VERIFY", "FINAL", "ERROR")


def test_logger_writes_jsonl_with_seq_and_channels(tmp_path):
    lg = RunLogger("r1", str(tmp_path))
    lg.log("GOAL", goal="g")
    lg.log("ACT", tool="restart", result="ok", eval={"harmful": False}, why=None)
    lg.close()
    rows = read_jsonl(lg.path)
    assert [r["seq"] for r in rows] == [1, 2] and all(r["run_id"] == "r1" and "ts" in r for r in rows)
    assert "why" not in rows[1]  # None fields are dropped
    assert "eval" in rows[1] and "eval" not in agent_visible(rows[1])
    json.dumps(rows)


def test_logger_rejects_unknown_type(tmp_path):
    lg = RunLogger("r2", str(tmp_path))
    try:
        lg.log("THOUGHT", text="x")
        assert False
    except ValueError:
        pass


def test_tool_event_seqs_only_observe_and_act(tmp_path):
    lg = RunLogger("r3", str(tmp_path))
    lg.log("GOAL")
    lg.log("PLAN")
    lg.log("OBSERVE")
    lg.log("ACT")
    lg.log("ERROR")
    assert lg.tool_event_seqs() == {3, 4}


# ---- plan validation (SPEC §4 rules 1-4) ----
def test_v1_accepted_and_empty_rejected():
    pm = PlanManager()
    assert not pm.validate([], [], set()).ok
    v = pm.validate(["assess", "fix"], [], set())
    assert v.ok and v.version == 1


def test_replan_requires_triggered_by_existing_events():
    pm = PlanManager()
    pm.commit(["a"], seq=2)
    assert "triggered_by" in pm.validate(["b"], [], {3}).message
    assert "unknown" in pm.validate(["b"], [99], {3}).message
    assert pm.validate(["b"], [3], {3}).ok


def test_replan_needs_event_newer_than_previous_plan():
    pm = PlanManager()
    pm.commit(["a"], seq=5)
    v = pm.validate(["b"], [3], {3, 4})
    assert not v.ok and "newer" in v.message
    assert pm.validate(["b"], [3, 6], {3, 6}).ok


def test_noop_replan_rejected_and_diff_reported():
    pm = PlanManager()
    pm.commit(["a", "b"], seq=1)
    assert not pm.validate(["a", " b "], [2], {2}).ok
    v = pm.validate(["a", "c"], [2], {2})
    assert v.ok and v.version == 2 and v.diff["added"] == ["c"] and v.diff["removed"] == ["b"]
