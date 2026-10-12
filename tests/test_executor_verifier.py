from nidaan.logger import RunLogger
from nidaan.tools import ToolExecutor, build_langchain_tools
from nidaan.verifier import verify
from settlesim.generator import hero
from settlesim.tools import SettleSimTools

W = "checking"


def make(tmp_path):
    sim = hero()
    lg = RunLogger("t", str(tmp_path))
    return sim, lg, ToolExecutor(SettleSimTools(sim), lg)


def test_tool_count_and_names():
    names = [t.name for t in build_langchain_tools()]
    assert len(names) == 10 and "update_plan" in names and "submit_incident_report" in names


def test_gate_on_plan_v1(tmp_path):
    sim, lg, ex = make(tmp_path)
    out = ex.execute("restart", {"component": "worker", "why": W}, {})
    assert "no plan yet" in out and not sim.worker.running
    ev = lg.events[-1]
    assert ev["type"] == "ACT" and ev["outcome"] == "rejected"
    ex.execute("update_plan", {"steps": ["assess"], "reason": "start"}, {})
    assert "[" in ex.execute("restart", {"component": "worker", "why": W}, {}) and sim.worker.running


def test_results_carry_event_numbers_and_eval_stays_out_of_text(tmp_path):
    sim, lg, ex = make(tmp_path)
    ex.execute("update_plan", {"steps": ["assess"], "reason": "r"}, {})
    out = ex.execute("run_settlement", {"mode": "resume", "why": W}, {})
    assert out.startswith("[2]") and "harmful" not in out and "faults_active_after" not in out
    assert lg.events[-1]["eval"]["refusal"] is True


def test_replan_flow_logs_diff_and_rejects_stale_trigger(tmp_path):
    sim, lg, ex = make(tmp_path)
    ex.execute("update_plan", {"steps": ["a"], "reason": "r"}, {})  # seq 1
    ex.execute("check_pipeline", {"why": W}, {})  # seq 2
    bad = ex.execute("update_plan", {"steps": ["b"], "reason": "r", "triggered_by": [1]}, {})
    assert "rejected" in bad and ex.plans.current_version == 1
    ok = ex.execute("update_plan", {"steps": ["b"], "reason": "r", "triggered_by": [2]}, {})
    assert "plan v2 accepted" in ok
    plan_ev = [e for e in lg.events if e["type"] == "PLAN"][-1]
    assert plan_ev["plan_version"] == 2 and plan_ev["triggered_by"] == [2] and plan_ev["diff"]["added"] == ["b"]


def test_invalid_args_and_submit_pending(tmp_path):
    sim, lg, ex = make(tmp_path)
    assert "invalid arguments" in ex.execute("inspect", {"component": "nope", "why": W}, {})
    assert lg.events[-1]["type"] == "ERROR"
    rep = {"status_claimed": "unresolved", "root_causes": [], "actions": [], "summary": "s"}
    assert ex.execute("submit_incident_report", rep, {}) is None and ex.pending_report == rep


def test_no_free_text_fields_logged(tmp_path):
    sim, lg, ex = make(tmp_path)
    ex.execute("update_plan", {"steps": ["a"], "reason": "r"}, {"llm_call": 1})
    allowed = {"seq", "ts", "run_id", "type", "plan_version", "steps", "reason", "triggered_by", "diff",
               "result", "outcome", "llm_call"}
    assert set(lg.events[-1]) <= allowed


# ---- verifier V1-V3 ----
def solved_sim():
    sim = hero()
    t = SettleSimTools(sim)
    t.restart("worker", W)
    t.run_task("bank", "rotate_credential", W)
    t.run_settlement("resume", W)
    t.set_config("bank", "max_concurrency", sim.bank.rate_limit, W)
    t.run_settlement("resume", W)
    return sim


EVENTS = [{"seq": 1, "type": "PLAN"}, {"seq": 2, "type": "ACT"}, {"seq": 3, "type": "OBSERVE"}]


def rep(status="resolved", actions=(2,)):
    return {"status_claimed": status, "root_causes": [], "actions": list(actions), "summary": "s"}


def test_verifier_passes_when_goal_met_and_claims_valid():
    r = verify(rep(), EVENTS, solved_sim())
    assert r.passed and r.checks == {"V1": True, "V2": True, "V3": True}


def test_v1_and_v3_fail_when_resolved_claimed_but_goal_unmet():
    r = verify(rep(), EVENTS, hero())
    assert not r.passed and r.checks["V1"] is False and r.checks["V3"] is False


def test_v1_fails_on_duplicates_even_if_all_sent():
    sim = solved_sim()
    SettleSimTools(sim).run_settlement("full", W)
    assert len(sim.duplicates()) == 20
    r = verify(rep(), EVENTS, sim)
    assert not r.passed and not r.checks["V1"]


def test_v2_fails_for_missing_or_non_act_steps():
    sim = solved_sim()
    for bad in ([3], [99], [1]):  # OBSERVE, absent, PLAN
        r = verify(rep(actions=bad), EVENTS, sim)
        assert not r.passed and r.checks["V2"] is False and r.checks["V1"] is True


def test_honest_unresolved_claim_does_not_trip_v3_but_v1_still_fails():
    r = verify(rep("unresolved"), EVENTS, hero())
    assert r.checks["V3"] is True and r.checks["V1"] is False and not r.passed


def test_transient_classification_daily_quota_is_not_retried():
    from nidaan.graph import is_transient
    assert is_transient("503 UNAVAILABLE high demand")
    assert is_transient("429 RESOURCE_EXHAUSTED per-minute limit")
    assert not is_transient("429 RESOURCE_EXHAUSTED ... GenerateRequestsPerDayPerProjectPerModel-FreeTier")
    assert not is_transient("400 INVALID_ARGUMENT")


# ---- run_task schema (SPEC §3: exactly four tasks) ----
ALLOWED_TASKS = ["rotate_credential", "sync_clock", "rotate_logs", "kill_idle_connections"]


def test_run_task_schema_exposes_exactly_the_four_spec_tasks():
    tool = next(t for t in build_langchain_tools() if t.name == "run_task")
    schema = tool.args_schema.model_json_schema()
    assert sorted(schema["properties"]["task"]["enum"]) == sorted(ALLOWED_TASKS)


def test_run_task_invalid_task_rejected_before_reaching_sim(tmp_path):
    from nidaan.tools import RunTaskArgs
    for t in ALLOWED_TASKS:  # every SPEC task passes schema validation
        assert RunTaskArgs(component="bank", task=t, why=W).task == t
    sim, lg, ex = make(tmp_path)
    ex.execute("update_plan", {"steps": ["a"], "reason": "r"}, {})
    n = len(sim.logs["bank"])
    out = ex.execute("run_task", {"component": "bank", "task": "help", "why": W}, {})
    assert "invalid arguments" in out and lg.events[-1]["type"] == "ERROR"
    assert len(sim.logs["bank"]) == n  # nothing reached the simulator


def test_run_task_description_is_general():
    tool = next(t for t in build_langchain_tools() if t.name == "run_task")
    assert not any(w in tool.description.lower() for w in ("fix", "expired", "stale", "full"))


# ---- rate-limit retry delay ----
def test_retry_delay_respects_server_delay():
    from nidaan.graph import retry_delay_s
    msg = ("429 RESOURCE_EXHAUSTED ... 'quotaId': 'GenerateRequestsPerMinutePerProjectPerModel-FreeTier' "
           "... 'retryDelay': '53s'")
    assert retry_delay_s(msg, 0) == 54 and retry_delay_s(msg, 3) == 54  # not the 2/4/8/16 backoff
    assert retry_delay_s("429 RESOURCE_EXHAUSTED Please retry in 11.5s.", 0) == 12.5


def test_retry_delay_fallback_cap_and_nonretryable():
    from nidaan.graph import retry_delay_s
    # Exponential backoff with jitter: retry a waits within [50%, 100%] of 2, 4, 8, 16 s (capped at 30 s).
    for a, cap in enumerate([2, 4, 8, 16]):
        d = retry_delay_s("503 UNAVAILABLE", a)
        assert cap / 2 <= d <= cap
    assert retry_delay_s("503 UNAVAILABLE", 4) is None  # transient retries exhausted (LLM_RETRIES = 4)
    assert retry_delay_s("429 RESOURCE_EXHAUSTED 'retryDelay': '500s'", 0) is None  # beyond cap
    assert retry_delay_s("429 ... PerDay ... 'retryDelay': '10s'", 0) is None  # daily quota
    assert retry_delay_s("400 INVALID_ARGUMENT", 0) is None
