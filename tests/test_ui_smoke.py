"""Headless smoke tests of the dashboard (Streamlit AppTest). Local only: reads runs/ and results/, makes no
network or LLM calls. Live runs use the runbook arm (no model) in a temporary directory; the Nidaan start is
replaced by a recorder, so no model client is ever built."""
import pathlib

import pytest
from streamlit.testing.v1 import AppTest

import ui.live as live

APP = str(pathlib.Path(__file__).resolve().parent.parent / "ui" / "app.py")
SECTIONS = ["Overview", "Investigate & Run", "Live Execution", "Recovery Verification", "Trace & Evaluation"]


@pytest.fixture(autouse=True)
def _isolated_live(tmp_path, monkeypatch):
    monkeypatch.setattr(live, "LIVE_RUNS_DIR", tmp_path / "runs_live")
    monkeypatch.setattr(live, "provider_key_present", lambda: False)  # never read the real .env in tests
    yield
    run = live.current_run()
    if run is not None:
        run.wait(30)
    assert not live.is_busy()


def app(section=None):
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception, [e.value for e in at.exception]
    if section:
        at.segmented_control(key="section").set_value(section).run()
        assert not at.exception, [e.value for e in at.exception]
    return at


def all_text(at) -> str:
    parts = [m.value for m in at.markdown] + [c.value for c in at.caption] + [e.value for e in at.error]
    return "\n".join(str(p) for p in parts)


def test_dashboard_renders_without_errors():
    at = app()
    assert "<b>Nidaan</b>" in all_text(at)
    assert list(at.segmented_control(key="section").options) == SECTIONS


@pytest.mark.parametrize("section", SECTIONS)
def test_every_section_renders_without_exceptions(section):
    at = app(section)
    assert at.segmented_control(key="section").value == section
    if section != "Overview":  # Overview opens with the hero instead of the section name
        assert f">{section.replace('&', '&amp;')}</h1>" in all_text(at)


def test_trace_and_evaluation_keeps_recorded_views():
    at = app("Trace & Evaluation")
    assert [t.label for t in at.tabs] == ["Metrics", "Comparison", "Run trace", "Evidence", "Scenarios"]
    heads = [s.value for s in at.subheader]
    assert "SPEC §9 metrics" in heads and "Every run in view" in heads
    assert len(at.dataframe) + len(at.table) >= 6


def test_dashboard_toggle_exclusion_renders():
    at = app()
    at.sidebar.checkbox[0].check().run()
    assert not at.exception, [e.value for e in at.exception]


def test_loading_and_navigating_start_no_run():
    before = live.current_run()
    at = app()
    for s in SECTIONS:
        at.segmented_control(key="section").set_value(s).run()
        assert not at.exception
    assert live.current_run() is before and not live.is_busy()
    assert not live.LIVE_RUNS_DIR.exists() or not list(live.LIVE_RUNS_DIR.iterdir())


def test_run_runbook_requires_an_explicit_click_and_is_never_called_verified():
    before = live.current_run()
    at = app("Investigate & Run")
    assert live.current_run() is before
    at.button(key="run_runbook").click().run()
    run = live.current_run()
    assert run is not before and run.mode == "runbook"
    assert run.wait(30)
    assert pathlib.Path(run.log_path).parent == live.LIVE_RUNS_DIR
    at.run()
    assert not at.exception
    assert at.segmented_control(key="section").value == "Live Execution"
    text = all_text(at)
    assert "Goal met" in text and "Verified" not in text  # the runbook is never labelled VERIFIED
    at.segmented_control(key="section").set_value("Recovery Verification").run()
    assert not at.exception
    assert "this arm submits no report" in all_text(at)


def test_run_nidaan_requires_key_and_explicit_confirmation(monkeypatch):
    calls = []
    monkeypatch.setattr(live, "start_live_run", lambda *a, **k: calls.append((a, k)))
    at = app("Investigate & Run")
    assert at.button(key="run_nidaan").disabled and at.checkbox(key="confirm_quota").disabled  # no key
    monkeypatch.setattr(live, "provider_key_present", lambda: True)
    at.run()
    assert at.button(key="run_nidaan").disabled  # key present, not yet confirmed
    assert "uses API quota" in all_text(at)
    at.checkbox(key="confirm_quota").check().run()
    assert not at.button(key="run_nidaan").disabled and calls == []  # confirming alone starts nothing
    at.button(key="run_nidaan").click().run()
    assert not at.exception
    assert len(calls) == 1 and calls[0][0] == ("nidaan", "hero")
    assert at.segmented_control(key="section").value == "Live Execution"
    at.segmented_control(key="section").set_value("Investigate & Run").run()
    assert at.checkbox(key="confirm_quota").value is False  # confirmation required again next time
    assert at.button(key="run_nidaan").disabled


def test_start_errors_are_shown_redacted(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("provider said no for key gsk_SECRETSECRET123 org_abc123")
    monkeypatch.setattr(live, "start_live_run", boom)
    at = app("Investigate & Run")
    at.button(key="run_runbook").click().run()
    text = all_text(at)
    assert "provider said no" in text
    assert "gsk_SECRETSECRET123" not in text and "org_abc123" not in text


def test_recorded_verification_view_separates_claim_verifier_and_ground_truth():
    at = app("Recovery Verification")
    at.segmented_control(key="w_verify_source").set_value("Recorded run").run()
    assert not at.exception
    text = all_text(at)
    assert ">Agent report</h2>" in text and ">Independent verifier</h2>" in text
    assert ">Simulator goal check</h2>" in text
    assert "not stored in recorded logs" in all_text(at)  # no reconstructed payout ledger for recorded runs


def test_live_execution_while_running_is_labelled_updating_and_not_verified(monkeypatch):
    import threading
    import baselines.runbook as rb
    gate, started = threading.Event(), threading.Event()

    def blocking(sim, logger, info):
        logger.log("GOAL", goal="test goal", eval={**info, "arm": "runbook"})
        started.set()
        assert gate.wait(10)
        logger.log("FINAL", outcome="GOAL_NOT_MET", result="test stop")
        return {"reason": "test stop"}

    monkeypatch.setattr(rb, "run_runbook", blocking)
    at = app("Investigate & Run")
    at.button(key="run_runbook").click().run()
    assert started.wait(10)
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    try:
        text = all_text(at)
        assert "updating" in text and "read while the run changes it" in text
        assert "Running" in text and "Verified" not in text
        at.segmented_control(key="section").set_value("Investigate & Run").run()
        assert at.button(key="run_runbook").disabled and at.button(key="run_nidaan").disabled  # one run at a time
    finally:
        gate.set()


def test_every_recorded_data_source_renders_recorded_views():
    at = app("Trace & Evaluation")
    for option in at.sidebar.selectbox(key="data_source").options:
        at.sidebar.selectbox(key="data_source").set_value(option).run()
        assert not at.exception, (option, [e.value for e in at.exception])
        at.segmented_control(key="section").set_value("Recovery Verification").run()
        at.segmented_control(key="w_verify_source").set_value("Recorded run").run()
        assert not at.exception, (option, [e.value for e in at.exception])
        at.segmented_control(key="section").set_value("Trace & Evaluation").run()


def test_open_recovery_verification_button_switches_section():
    at = app("Investigate & Run")
    at.button(key="run_runbook").click().run()
    assert live.current_run().wait(30)
    at.run()
    assert at.segmented_control(key="section").value == "Live Execution"
    at.button(key="open_verification").click().run()
    assert not at.exception
    assert at.segmented_control(key="section").value == "Recovery Verification"
    assert "Goal met" in all_text(at) and "Verified" not in all_text(at)
