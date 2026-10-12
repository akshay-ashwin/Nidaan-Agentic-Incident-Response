"""Offline tests for ui/theme.py: contrast of the colour tokens, escaping, and status labels."""
import pytest

from ui import data as D
from ui import theme as T


def _lum(h):
    c = [int(h.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def contrast(a, b):
    la, lb = _lum(a), _lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


@pytest.mark.parametrize("fg", ["ink", "text", "muted", "accent", "teal", "ok", "fail", "warn", "idle"])
@pytest.mark.parametrize("bg", ["ground", "panel", "wash-accent", "wash-teal", "wash-ok", "wash-warn", "wash-fail",
                                "wash-ink"])
def test_text_tokens_meet_wcag_aa_on_every_surface(fg, bg):
    surface = T.WASHES[bg[5:]] if bg.startswith("wash-") else T.TOKENS[bg]
    assert contrast(T.TOKENS[fg], surface) >= 4.5


@pytest.mark.parametrize("fill", ["ok", "fail", "accent", "ink"])
def test_white_text_on_solid_fills(fill):
    assert contrast("#FFFFFF", T.TOKENS[fill]) >= 4.5


def test_every_semantic_colour_is_documented():
    assert set(T.SEMANTICS) == {"ink", "accent", "teal", "ok", "warn", "fail", "idle"}


def test_forest_strip_prints_values_escapes_labels_and_marks_missing():
    out = T.forest("Goal <b>", "sub", [
        {"label": "<script>x</script>", "color": "#2459E0",
         "ci": {"k": 3, "n": 10, "rate": 0.3, "ci_low": 0.108, "ci_high": 0.603}},
        {"label": "Runbook", "color": "#4A3AA7", "ci": None, "na": "n/a (no plans)"}])
    assert "3/10" in out and "30%" in out and "CI 11% to 60%" in out  # values printed, not colour alone
    assert "<script>" not in out and "Goal &lt;b&gt;" in out
    assert "n/a (no plans)" in out and "Wilson 95% CI" in out


def test_every_state_has_word_and_glyph_not_colour_alone():
    for key, (label, glyph, tone, style, explain) in T.STATES.items():
        html = T.badge(key)
        assert label in html and glyph in html and explain
    assert {"VERIFIED", "GOAL_MET", "GOAL_NOT_MET", "FAILED", "RUNNING", "ERROR", "INCOMPLETE"} <= set(T.STATES)


def test_builders_escape_log_content():
    evil = "<script>alert(1)</script>"
    e = {"seq": 3, "type": "ACT", "tool": evil, "args": {"x": evil}, "why": evil, "result": evil,
         "outcome": "ok", "eval": {"note": evil}, "latency_ms": 1}
    vis, meta, ev = D.split_event_fields(e)
    out = T.spine_event(e, vis, meta, ev, D.event_style(e), D.headline(e), show_eval=True)
    assert "<script>" not in out and "&lt;script&gt;" in out
    assert "<script>" not in T.ledger_strip([{"id": evil, "amount": 1, "send_count": 2}])
    assert "<script>" not in T.provenance("live", evil) and "<script>" not in T.banner("FAILED", evil)


def test_evaluation_only_annotations_hidden_unless_requested():
    e = {"seq": 3, "type": "ACT", "tool": "restart", "args": {}, "outcome": "ok", "eval": {"harmful": False}}
    vis, meta, ev = D.split_event_fields(e)
    hidden = T.spine_event(e, vis, meta, ev, D.event_style(e), D.headline(e), False).lower()
    shown = T.spine_event(e, vis, meta, ev, D.event_style(e), D.headline(e), True).lower()
    assert "evaluation-only" not in hidden and "harmful" not in hidden
    assert "evaluation-only" in shown and "harmful" in shown


def test_ledger_strip_marks_duplicates_in_words():
    out = T.ledger_strip([{"id": "PO-1", "amount": 10, "send_count": 0},
                          {"id": "PO-2", "amount": 10, "send_count": 1},
                          {"id": "PO-3", "amount": 10, "send_count": 2}])
    assert "not sent" in out and "sent once" in out and "duplicate" in out and "2×" in out


def test_multiline_results_stay_inside_one_html_block():
    # Streamlit's markdown ends a raw-HTML block at a line break; generated HTML must not contain raw newlines.
    e = {"seq": 2, "type": "OBSERVE", "tool": "check_pipeline", "args": {}, "outcome": "ok",
         "result": "Components:\n  ledger: up\n\n  worker: stopped", "why": "look"}
    vis, meta, ev = D.split_event_fields(e)
    out = T.spine_event(e, vis, meta, ev, D.event_style(e), D.headline(e), True)
    assert "\n" not in out and "&#10;" in out
