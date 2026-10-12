"""Offline tests for LLM rate-limit handling (nidaan/llm_errors.py, nidaan/graph.py, ui/live.py, dashboard).

No network and no model calls: every "model" here is a stub, and sleeping is replaced by a recorder.
The 429 messages are the Groq token-per-minute rejections observed in dashboard runs, with a fake key and
fake organisation/request ids planted to check redaction.
"""
import pathlib

import pytest
from langchain_core.messages import AIMessage

import config
import nidaan.graph as G
import nidaan.llm_errors as E
import ui.live as live
from nidaan.logger import RunLogger, read_jsonl
from settlesim.generator import generate

SECRETS = ("gsk_LIVEKEY1234567890abcdef", "org_01hzSECRETorg", "req_01SECRETreq")
OBSERVED_A = ("Error code: 429 - {'error': {'message': 'Rate limit reached for model `openai/gpt-oss-120b` in "
              "organization `org_01hzSECRETorg` service tier `on_demand` on tokens per minute (TPM): Limit 8000, "
              "Used 7758, Requested 2191. Please try again in 14.6s. Need more tokens? Upgrade to Dev Tier today.', "
              "'type': 'tokens', 'code': 'rate_limit_exceeded'}} request_id=req_01SECRETreq "
              "key=gsk_LIVEKEY1234567890abcdef")
OBSERVED_B = OBSERVED_A.replace("Used 7758, Requested 2191", "Used 5641, Requested 2522").replace("14.6s", "1.2s")


class RateLimitError(Exception):
    """Same class name as the Groq SDK's, so messages read like real ones."""


class StubLLM:
    """Raises the scripted errors in order, then answers. Never contacts anything."""

    def __init__(self, errors, then=None):
        self.errors, self.then, self.calls = list(errors), then, 0

    def invoke(self, messages):
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        if self.then is None:
            raise RateLimitError(OBSERVED_A)
        return self.then


@pytest.fixture
def sleeps(monkeypatch):
    slept = []
    monkeypatch.setattr(G, "_sleep", slept.append)
    return slept


def agent(tmp_path, llm, name="t"):
    sim = generate(323, ["F6", "F1", "F7"])  # the development hero scenario
    lg = RunLogger(name, str(tmp_path))
    return G.NidaanAgent(sim, lg, llm=llm, scenario_info={"scenario": "hero", "seed": 323,
                                                           "faults": ["F6", "F1", "F7"], "arm": "nidaan"}), sim, lg


# ---- classification and provider guidance ----
@pytest.mark.parametrize("msg,used,req,after", [(OBSERVED_A, 7758, 2191, 14.6), (OBSERVED_B, 5641, 2522, 1.2)])
def test_observed_groq_tpm_rejections_are_rate_limits_with_guidance(msg, used, req, after):
    err = E.classify(f"RateLimitError: {msg}")
    assert err.kind == E.RATE_LIMIT and err.scope == "tokens per minute"
    assert (err.limit, err.used, err.requested, err.retry_after_s) == (8000, used, req, after)
    assert E.next_delay_s(err, 0, 0, 0.0) == pytest.approx(after + config.LLM_RETRY_MARGIN_S)


@pytest.mark.parametrize("text,seconds", [("14.6s", 14.6), ("1.2s", 1.2), ("450ms", 0.45), ("1m2.5s", 62.5)])
def test_provider_retry_guidance_parsed(text, seconds):
    assert E.provider_retry_after_s(f"429 rate limit. Please try again in {text}.") == pytest.approx(seconds)


def test_daily_quota_and_fatal_errors_are_not_retried():
    daily = E.classify("RateLimitError: 429 on tokens per day (TPD): Limit 200000, Used 199000, Requested 2000. "
                       "Please try again in 2h3m4s.")
    assert daily.kind == E.QUOTA_EXHAUSTED and E.next_delay_s(daily, 0, 0, 0) is None
    fatal = E.classify("BadRequestError: Error code: 400 - invalid tool schema")
    assert fatal.kind == E.FATAL and E.next_delay_s(fatal, 0, 0, 0) is None


def test_backoff_without_guidance_is_bounded_exponential_with_jitter():
    for a in range(8):
        cap = min(config.LLM_BACKOFF_MAX_S, config.LLM_BACKOFF_BASE_S * 2 ** a)
        assert E.backoff_s(a, rng=lambda: 0.0) == cap / 2
        assert E.backoff_s(a, rng=lambda: 1.0) == cap
    assert E.backoff_s(20, rng=lambda: 1.0) == config.LLM_BACKOFF_MAX_S


def test_total_wait_budget_stops_retries():
    err = E.classify("RateLimitError: 429 tokens per minute. Please try again in 100s.")
    assert E.next_delay_s(err, 0, 0, 0.0) == 101
    assert E.next_delay_s(err, 2, 0, 202.0) is None  # 202 + 101 > LLM_MAX_TOTAL_RETRY_WAIT_S (300)


def test_redaction_removes_keys_and_identifiers():
    out = E.redact(OBSERVED_A + " Authorization: Bearer abc.def-123")
    assert not any(s in out for s in SECRETS) and "abc.def-123" not in out
    assert "Limit 8000, Used 7758, Requested 2191" in out  # the diagnostic content survives


# ---- the agent's retry loop ----
def test_rate_limit_then_successful_retry(tmp_path, sleeps):
    ok = AIMessage(content="")
    a, _, lg = agent(tmp_path, StubLLM([RateLimitError(OBSERVED_A)], then=ok))
    resp, _, err = a._invoke([])
    assert resp is ok and err is None
    assert sleeps == [pytest.approx(15.6)]  # provider's 14.6 s + 1 s margin
    errs = [e for e in lg.events if e["type"] == "ERROR"]
    assert len(errs) == 1 and errs[0]["error_kind"] == "rate_limit" and errs[0]["attempt"] == 1
    assert errs[0]["retry_in_s"] == pytest.approx(15.6)
    assert errs[0]["error"].startswith("LLM call failed (attempt 1): RateLimitError")  # trace-analysis format kept
    assert not any(s in errs[0]["error"] for s in SECRETS)
    assert a.metrics["rate_limit_retries"] == 1 and a.metrics["llm_errors"] == 1


def test_exhausted_rate_limit_retries_stop_without_infinite_loop(tmp_path, sleeps):
    llm = StubLLM([])  # rate-limited forever
    a, _, lg = agent(tmp_path, llm)
    resp, _, err = a._invoke([])
    assert resp is None and err.kind == E.RATE_LIMIT
    assert llm.calls == config.LLM_RATE_LIMIT_RETRIES + 1
    assert len(sleeps) == config.LLM_RATE_LIMIT_RETRIES
    assert sum(sleeps) <= config.LLM_MAX_TOTAL_RETRY_WAIT_S
    last = [e for e in lg.events if e["type"] == "ERROR"][-1]
    assert "retry_in_s" not in last  # the final attempt is logged as not retried


def test_transient_errors_without_guidance_stop_after_the_transient_budget(tmp_path, sleeps):
    llm = StubLLM([Exception("Error code: 503 - UNAVAILABLE")] * 20, then=AIMessage(content=""))
    a, _, _ = agent(tmp_path, llm)
    resp, _, err = a._invoke([])
    assert resp is None and err.kind == E.TRANSIENT and llm.calls == config.LLM_RETRIES + 1
    assert all(0 < s <= config.LLM_BACKOFF_MAX_S for s in sleeps)


def test_fatal_error_is_not_retried(tmp_path, sleeps):
    llm = StubLLM([ValueError("Error code: 400 - bad request")], then=AIMessage(content=""))
    a, _, _ = agent(tmp_path, llm)
    resp, _, err = a._invoke([])
    assert resp is None and err.kind == E.FATAL and llm.calls == 1 and sleeps == []


def test_exhausted_run_ends_incomplete_never_verified_and_keeps_simulator_state(tmp_path, sleeps):
    a, sim, lg = agent(tmp_path, StubLLM([]))
    out = a.run()
    events = read_jsonl(lg.path)
    final = events[-1]
    assert out["status"] == "FAILED" and final["type"] == "FINAL" and final["outcome"] == "FAILED"
    assert final["result"].startswith("LLM error: ") and final["error_kind"] == "rate_limit"
    assert not any(e["type"] == "VERIFY" for e in events)  # nothing was submitted or verified
    assert final["eval"]["goal_met"] is False and final["eval"]["faults_active"] == sim.active_faults()
    assert sim.sent_count() == 0  # the simulator was never touched by a failed call
    assert final["metrics"]["rate_limit_retries"] == config.LLM_RATE_LIMIT_RETRIES
    assert events[0]["type"] == "GOAL" and "provenance" in events[0]  # logging and provenance preserved
    assert not any(s in str(events) for s in SECRETS)
    assert live.verdict("nidaan", True, None, None, {"goal_met": False}, final) == "ERROR"


def test_a_verifier_pass_is_not_overridden_but_an_llm_stop_never_reads_verified():
    fin_llm = {"type": "FINAL", "outcome": "FAILED", "result": "LLM error: RateLimitError: 429"}
    assert live.verdict("nidaan", True, None, {"outcome": "pass"}, {"goal_met": True},
                        {"type": "FINAL", "outcome": "VERIFIED", "result": "goal verified"}) == "VERIFIED"
    assert live.verdict("nidaan", True, None, None, {"goal_met": True}, fin_llm) == "ERROR"
    assert live.verdict("nidaan", True, None, None, {"goal_met": False}, fin_llm) == "ERROR"


# ---- pacing ----
def test_token_pacer_reproduces_the_providers_own_retry_guidance():
    now = [0.0]
    p = E.TokenPacer(8000, headroom=1.0, clock=lambda: now[0])
    assert p.wait_s(2191) == 0.0  # nothing recorded yet
    p.record(7758)
    assert p.wait_s(2191) == pytest.approx(14.6, abs=0.05)  # Groq said "try again in 14.6s"
    q = E.TokenPacer(8000, headroom=1.0, clock=lambda: now[0])
    q.record(5641)
    assert q.wait_s(2522) == pytest.approx(1.2, abs=0.05)  # Groq said "try again in 1.2s"


def test_token_pacer_drains_over_time_and_can_be_disabled():
    now = [0.0]
    p = E.TokenPacer(8000, clock=lambda: now[0])  # default 90% headroom
    p.record(7000)
    first = p.wait_s(2500)
    assert first > 0
    now[0] = 10.0
    assert p.wait_s(2500) == pytest.approx(first - 10.0)  # the bucket drains at 8000/60 tokens per second
    now[0] = 60.0
    assert p.wait_s(2500) == 0.0
    assert p.wait_s(10 ** 6) == 60.0  # never more than a minute
    assert E.TokenPacer(None).wait_s(10 ** 6) == 0.0


# ---- live run + dashboard ----
def test_live_run_stopped_by_rate_limit_is_explained_redacted_and_not_verified(tmp_path, sleeps, monkeypatch):
    from streamlit.testing.v1 import AppTest
    run = live.LiveRun("nidaan", "hero", runs_dir=tmp_path, llm=StubLLM([])).start()
    assert run.wait(30)
    snap = run.snapshot()
    assert snap["verdict"] == "ERROR" and snap["status"] == "completed"
    f = snap["llm_failure"]
    assert f["kind"] == "rate_limit" and f["scope"] == "tokens per minute" and f["retry_after_s"] == 14.6
    assert "tokens per minute" in f["text"] and "14.6" in f["action"]
    assert snap["rate_limit_retries"] == config.LLM_RATE_LIMIT_RETRIES
    assert not any(s in str(snap) for s in SECRETS)

    monkeypatch.setattr(live, "provider_key_present", lambda: False)
    at = AppTest.from_file(str(pathlib.Path(__file__).resolve().parent.parent / "ui" / "app.py"),
                           default_timeout=60).run()
    at.segmented_control(key="section").set_value("Live Execution").run()
    assert not at.exception, [e.value for e in at.exception]
    text = "\n".join(str(x.value) for x in list(at.markdown) + list(at.error) + list(at.caption) + list(at.code))
    assert "Stopped by the model provider" in text and "tokens per minute" in text
    assert "Verified" not in text and "not verified" in text
    assert not any(s in text for s in SECRETS)
    assert any(x.label == "Diagnostic details (redacted)" for x in at.expander)


def test_waiting_state_is_reported_while_a_retry_is_pending():
    evs = [{"type": "GOAL", "seq": 1},
           {"type": "ERROR", "seq": 2, "error": "LLM call failed (attempt 1): RateLimitError: 429",
            "error_kind": "rate_limit", "retry_in_s": 15.6, "attempt": 1, "ts": "t"}]
    assert live._waiting(evs) == {"kind": "rate_limit", "retry_in_s": 15.6, "attempt": 1, "since": "t"}
    assert live._waiting(evs[:1]) is None


def test_no_model_client_is_built_on_import_or_navigation(monkeypatch):
    from streamlit.testing.v1 import AppTest
    import nidaan.llm
    built = []

    def boom(*a, **k):
        built.append(1)
        raise AssertionError("a model client was built")
    monkeypatch.setattr(nidaan.llm, "make_chat_model", boom)
    monkeypatch.setattr(G, "make_chat_model", boom)
    monkeypatch.setattr(live, "provider_key_present", lambda: False)
    at = AppTest.from_file(str(pathlib.Path(__file__).resolve().parent.parent / "ui" / "app.py"),
                           default_timeout=60).run()
    for s in ("Overview", "Investigate & Run", "Live Execution", "Recovery Verification", "Trace & Evaluation"):
        at.segmented_control(key="section").set_value(s).run()
        assert not at.exception, [e.value for e in at.exception]
    assert built == []
