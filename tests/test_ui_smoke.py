"""Headless smoke test of the dashboard (Streamlit AppTest). Local only: reads runs/ and results/,
makes no network or LLM calls."""
import pathlib

from streamlit.testing.v1 import AppTest

APP = str(pathlib.Path(__file__).resolve().parent.parent / "ui" / "app.py")


def test_dashboard_renders_without_errors():
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception, [e.value for e in at.exception]
    assert at.title[0].value.startswith("Nidaan")
    assert len(at.tabs) == 5
    assert [t.label for t in at.tabs] == ["Overview", "Run Trace", "Scenario", "Comparison", "Evidence"]


def test_dashboard_toggle_exclusion_renders():
    at = AppTest.from_file(APP, default_timeout=60).run()
    at.sidebar.checkbox[0].check().run()
    assert not at.exception, [e.value for e in at.exception]
