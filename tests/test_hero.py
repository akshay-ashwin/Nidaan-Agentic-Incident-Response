"""Hero scenario (F6 + F1 + F7) solved by hand through the tool wrappers (Phase 1 gate)."""
from settlesim.generator import hero
from settlesim.tools import ACT, OBSERVE, SettleSimTools

W = "test step"


def test_hero_by_hand():
    sim = hero()
    t = SettleSimTools(sim)
    limit = sim.bank.rate_limit

    r = t.check_pipeline(W)  # initial: worker down, queue 37, 0/20
    assert "stopped" in r.text and "queue depth: 37" in r.text and "0/20" in r.text
    assert t.run_settlement("resume", W).outcome == "refused"  # S4
    assert "37 payments unconfirmed" in t.read_logs("settlement", W).text
    assert "running: false" in t.inspect("worker", W).text

    assert t.restart("worker", W).outcome == "ok" and sim.worker.queue_depth == 0
    r = t.run_settlement("resume", W)  # newly exposed: 401
    assert "401" in r.text and r.annotations["new_failure_exposed"]

    bank = t.inspect("bank", W).text  # expired credential visible
    assert "credential.expires_at" in bank
    assert t.run_task("bank", "rotate_credential", W).outcome == "ok"

    r = t.run_settlement("resume", W)  # 8 sent then 429 (limit 5)
    assert f"sent 8 payouts" in r.text and "429" in r.text and f"X-RateLimit-Limit: {limit}" in r.text
    assert r.annotations["new_failure_exposed"]

    assert t.set_config("bank", "max_concurrency", limit, W).outcome == "ok"
    assert "8 sent, 12 pending" in t.get_batch_status(W).text
    r = t.run_settlement("resume", W)  # resume, not full
    assert "Run complete" in r.text and not r.annotations["duplicate_created"]

    final = t.check_pipeline(W).text
    assert "20/20" in final and "Reconciled: yes" in final
    assert sim.goal_met() and sim.duplicates() == [] and sim.active_faults() == []
    assert {x.kind for x in t.history} == {OBSERVE, ACT}


def test_hero_full_instead_of_resume_fails_s1():
    sim = hero()
    t = SettleSimTools(sim)
    t.restart("worker", W)
    t.run_task("bank", "rotate_credential", W)
    t.run_settlement("resume", W)
    t.set_config("bank", "max_concurrency", sim.bank.rate_limit, W)
    r = t.run_settlement("full", W)
    assert r.annotations["duplicate_created"] and not sim.goal_met()


def test_why_over_25_words_is_rejected_and_25_is_accepted():
    t = SettleSimTools(hero())
    ok = " ".join(["word"] * 25)
    too_long = " ".join(["word"] * 26)
    assert t.check_pipeline(ok).outcome == "ok"
    r = t.restart("worker", too_long)
    assert r.outcome == "rejected" and "25 words" in r.text
    assert t.sim.worker.queue_depth == 37 and not t.sim.worker.running  # action not executed
    assert t.inspect("bank", too_long).outcome == "rejected"


def test_why_is_required_and_annotations_hidden_from_observe():
    t = SettleSimTools(hero())
    r = t.restart("worker", "")
    assert r.outcome == "rejected" and t.sim.worker.queue_depth == 37
    assert t.check_pipeline(W).annotations == {}
