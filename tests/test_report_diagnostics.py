"""Report diagnostics in the trace analyser (descriptive; not SPEC §9 metrics; verifier unchanged). Offline; no LLM."""
import os

import pytest

from evaluation.metrics import compute_run_metrics
from evaluation.trace_analysis import analyse_run, render_markdown, report_diagnostics
from nidaan.logger import read_jsonl

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REV1_DEV_F2 = os.path.join(ROOT, "runs", "nidaan-dev_f2-s11-r1-20261010T135920634391.jsonl")
ORIG_DEV_F2 = os.path.join(ROOT, "runs", "nidaan-dev_f2-s11-r1-20261010T130437328361.jsonl")
HERO = os.path.join(ROOT, "runs", "hero-s323-20261010T122852.jsonl")


def _ann(no_effect=False):
    return {"new_failure_exposed": False, "refusal": False, "no_effect": no_effect, "harmful": False,
            "duplicate_created": False, "faults_active_after": []}


def act(seq, outcome="ok", no_effect=False, annotate=True):
    e = {"seq": seq, "type": "ACT", "tool": "t", "args": {}, "outcome": outcome}
    if annotate:
        e["eval"] = _ann(no_effect)
    return e


def obs(seq):
    return {"seq": seq, "type": "OBSERVE", "tool": "inspect", "args": {}, "outcome": "ok"}


def verify(seq, actions, root_causes, outcome="pass"):
    return {"seq": seq, "type": "VERIFY", "outcome": outcome,
            "args": {"status_claimed": "resolved", "actions": actions, "root_causes": root_causes, "summary": "s"}}


def rc(evidence, component="bank"):
    return {"component": component, "description": "d", "evidence": evidence}


BASE = [act(2), obs(3), act(4, no_effect=True), act(5, outcome="rejected"), act(6, outcome="refused"), act(7)]


# ---- action coverage ------------------------------------------------------------------------
def test_complete_report_has_full_coverage_and_no_flags():
    d = report_diagnostics(BASE + [verify(8, [2, 4, 7], [rc([3, 7])])], "nidaan")
    c = d["action_coverage"]
    assert c["coverage"] == "3/3" and c["omitted_executed"] == []
    assert c["claimed_not_executed"] == [] and c["invalid_references"] == [] and c["duplicate_references"] == []
    assert d["root_cause_evidence"]["root_causes"][0]["status"] == "no_flag"


def test_omitted_executed_actions_are_listed():
    c = report_diagnostics(BASE + [verify(8, [7], [rc([3])])], "nidaan")["action_coverage"]
    assert c["coverage"] == "1/3" and c["omitted_executed"] == [2, 4]


def test_invalid_and_not_executed_references_are_distinguished_from_omissions():
    c = report_diagnostics(BASE + [verify(8, [2, 2, 3, 5, 6, 99, "x", True, 7, 4], [rc([3])])], "nidaan")[
        "action_coverage"]
    assert c["claimed_executed"] == [2, 7, 4] and c["omitted_executed"] == []
    assert c["claimed_not_executed"] == [{"seq": 5, "outcome": "rejected"}, {"seq": 6, "outcome": "refused"}]
    assert c["invalid_references"] == [3, 99, "x", True]  # OBSERVE, missing, not integers
    assert c["duplicate_references"] == [2]


def test_references_to_events_after_the_report_are_invalid():
    events = BASE + [verify(8, [2, 4, 7, 9], [rc([9])], outcome="fail"), act(9), verify(10, [2, 4, 7, 9], [rc([9])])]
    first_only = report_diagnostics(events[:-2] + [events[-3]], "nidaan")  # log ending at the first report
    assert first_only["action_coverage"]["invalid_references"] == [9]
    last = report_diagnostics(events, "nidaan")  # the last report is analysed
    assert last["report_seq"] == 10 and last["reports_submitted"] == 2
    assert last["action_coverage"]["coverage"] == "4/4" and last["action_coverage"]["invalid_references"] == []


def test_missing_actions_list_is_reported_unavailable():
    e = verify(8, None, [rc([3])])
    del e["args"]["actions"]
    assert report_diagnostics(BASE + [e], "nidaan")["action_coverage"]["status"] == "unavailable"


# ---- root-cause evidence ----------------------------------------------------------------------
def test_root_cause_citing_a_no_effect_action_is_flagged_not_judged():
    r = report_diagnostics(BASE + [verify(8, [2, 4, 7], [rc([3, 4])])], "nidaan")["root_cause_evidence"]["root_causes"][0]
    assert r["status"] == "flagged" and r["cites_no_effect_actions"] == [4]
    assert set(r) >= {"cites_no_effect_actions", "invalid_evidence", "act_evidence_without_annotation"}
    assert "verdict" not in r and "correct" not in r  # a flag only; no correctness judgement is produced


@pytest.mark.parametrize("evidence,expected", [([], "no evidence cited"), (None, "no evidence cited")])
def test_root_cause_without_evidence_is_uncertain(evidence, expected):
    r = report_diagnostics(BASE + [verify(8, [2], [rc(evidence)])], "nidaan")["root_cause_evidence"]["root_causes"][0]
    assert r["status"] == "uncertain" and r["reason"] == expected


def test_unannotated_or_invalid_evidence_is_uncertain_not_flagged():
    events = [act(2, annotate=False), obs(3), verify(4, [2], [rc([2]), rc([3, 42]), rc(["x"])])]
    rs = report_diagnostics(events, "nidaan")["root_cause_evidence"]["root_causes"]
    assert [r["status"] for r in rs] == ["uncertain", "uncertain", "uncertain"]
    assert rs[0]["act_evidence_without_annotation"] == [2]
    assert rs[1]["invalid_evidence"] == [42] and rs[2]["invalid_evidence"] == ["x"]


def test_report_without_root_causes_is_unavailable():
    assert report_diagnostics(BASE + [verify(8, [2], [])], "nidaan")["root_cause_evidence"]["status"] == "unavailable"


# ---- applicability -----------------------------------------------------------------------------------
def test_no_report_and_baseline_arms_are_not_invented():
    assert report_diagnostics(BASE, "nidaan")["status"] == "no_report"
    for arm in ("runbook", "oneshot", None):
        assert report_diagnostics(BASE + [verify(8, [2], [rc([3])])], arm)["status"] == "not_applicable"


# ---- real development traces --------------------------------------------------------------------------
def _load(path):
    if not os.path.exists(path):
        pytest.skip("run log not present (runs/ is gitignored)")
    return read_jsonl(path)


def test_revision1_dev_f2_trace():
    events = _load(REV1_DEV_F2)
    a = analyse_run(events, REV1_DEV_F2)
    d = a["report_diagnostics"]
    c = d["action_coverage"]
    assert d["report_seq"] == 43 and d["verifier_outcome"] == "pass"
    assert c["executed"] == [5, 10, 16, 34, 36, 38] and c["claimed_executed"] == [10, 36, 38]
    assert c["omitted_executed"] == [5, 16, 34] and c["coverage"] == "3/6"
    assert c["invalid_references"] == [] and c["claimed_not_executed"] == []
    r1, r2 = d["root_cause_evidence"]["root_causes"]
    # Root cause 1 ("expired credential") cites #5 (the first settlement, which exposed the 401) and the rotation #10;
    # both are recorded as no effect. #5 is legitimate evidence that a 401 occurred, #10 shows the rotation changed nothing.
    assert r1["status"] == "flagged" and r1["cites_no_effect_actions"] == [5, 10]
    # Root cause 2 (stale key) is the correct explanation, yet it is also flagged: it cites #34, a settlement retry
    # that still failed. This is why a flag is a prompt for review, not evidence that the root cause is wrong.
    assert r2["status"] == "flagged" and r2["cites_no_effect_actions"] == [34]
    # Diagnostics are separate from the SPEC §9 metrics, which are unchanged.
    assert a["spec_metrics"] == compute_run_metrics(events)["spec"]


def test_hero_trace_report_is_complete_and_unflagged():
    d = analyse_run(_load(HERO))["report_diagnostics"]
    c = d["action_coverage"]
    assert c["coverage"] == "6/6" and c["omitted_executed"] == [] and c["invalid_references"] == []
    assert [r["status"] for r in d["root_cause_evidence"]["root_causes"]] == ["no_flag"] * 3


def test_original_dev_f2_trace_has_no_report():
    assert analyse_run(_load(ORIG_DEV_F2))["report_diagnostics"]["status"] == "no_report"


def test_markdown_labels_diagnostics_as_descriptive():
    events = BASE + [verify(8, [7], [rc([3, 4])])]
    events = [{"seq": 1, "type": "GOAL", "eval": {"scenario": "s", "faults": ["F2"]}}] + events
    for e in events:
        e.setdefault("ts", "2026-10-10T00:00:00+00:00")
        e.setdefault("run_id", "r")
    md = render_markdown([analyse_run(events)], {})
    assert "**Report diagnostics** *(descriptive; not SPEC §9 metrics; verifier pass/fail unchanged" in md
    assert "omitted: #2, #4" in md and "**flag**" in md and "*(review; not a verdict)*" in md
