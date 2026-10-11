"""SPEC §5 verifier contract, pinned with the incident report from the revision-1 dev_f2 run
(runs/nidaan-dev_f2-s11-r1-20261010T135920634391.jsonl, VERIFY #43). Offline; no LLM.

That report (a) attributes the 401 partly to an expired credential, which the cited #7 contradicts, and
(b) omits performed settlement runs #5, #16, #34 from `actions`. Neither is checked by the verifier under
SPEC §5 ("does not judge root-cause correctness"; V2 = claimed steps exist and are ACT events). These tests
document that boundary; changing it is a verifier-semantics change and must update them deliberately.
"""
from nidaan.verifier import verify
from evaluation.metrics import root_cause_exact
from settlesim.generator import generate
from settlesim.tools import SettleSimTools

# Verbatim from VERIFY #43 of the revision-1 dev_f2 log.
REV1_REPORT = {
    "status_claimed": "resolved",
    "root_causes": [
        {"component": "bank", "description": "Expired credential caused 401 errors during settlement",
         "evidence": [5, 7, 10]},
        {"component": "bank", "description": "bank.key_in_use still pointed to old key after credential rotation",
         "evidence": [34, 32, 36]},
    ],
    "actions": [10, 36, 38],
    "summary": "Rotated bank credential and corrected key_in_use; settlement batch completed successfully with all "
               "payouts sent exactly once.",
}
# ACT events of that run (seq, outcome); OBSERVE events at the cited evidence seqs 7 and 32.
ACTS = [(5, "ok"), (10, "ok"), (14, "rejected"), (16, "ok"), (22, "rejected"), (26, "rejected"), (30, "rejected"),
        (34, "ok"), (36, "ok"), (38, "ok")]


def _events():
    ev = [{"seq": s, "type": "ACT", "outcome": o} for s, o in ACTS]
    ev += [{"seq": 7, "type": "OBSERVE"}, {"seq": 32, "type": "OBSERVE"}]
    return sorted(ev, key=lambda e: e["seq"])


def _solved_dev_f2():
    sim = generate(11, ["F2"])
    t = SettleSimTools(sim)
    key = sim.bank.vault_active_key  # the value inspect(bank) shows as vault_active_key
    assert t.set_config(component="bank", key="key_in_use", value=key, why="fix").outcome == "ok"
    assert "20/20" in t.run_settlement(mode="full", why="settle").text
    assert sim.goal_met() and not sim.duplicates()
    return sim


def test_verifier_does_not_judge_root_cause_or_action_completeness_spec5():
    res = verify(REV1_REPORT, _events(), _solved_dev_f2())
    assert res.passed and res.checks == {"V1": True, "V2": True, "V3": True}
    performed = {s for s, o in ACTS if o == "ok"}
    assert performed - set(REV1_REPORT["actions"]) == {5, 16, 34}  # omitted, yet V2 passes by contract


def test_v2_still_rejects_claimed_steps_that_are_not_act_events():
    bad = {**REV1_REPORT, "actions": [10, 36, 38, 7, 99]}  # 7 is an OBSERVE, 99 does not exist
    res = verify(bad, _events(), _solved_dev_f2())
    assert not res.checks["V2"] and "[7, 99]" in res.message()


def test_spec9_root_cause_metric_is_component_level_only():
    # Both claimed root causes name 'bank', the true component for F2, so the metric scores it exact
    # although one description is wrong.
    events = [{"seq": 43, "type": "VERIFY", "args": REV1_REPORT}]
    assert root_cause_exact(events, ["F2"], "nidaan") is True
