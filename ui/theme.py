"""Visual system for the dashboard ("evidence-led intelligence"). No Streamlit import; unit-tested.

Every builder returns an HTML string for st.markdown(..., unsafe_allow_html=True). All text that can come from a
log, a run or a simulator is passed through html.escape. Builders are display-only: no interactive elements, so
all controls stay native (keyboard-operable) Streamlit widgets.

Colour carries meaning (documented in SEMANTICS). Status is never conveyed by colour alone: every state carries a
word and a glyph. Washes (pale tints) are reserved for a few regions where they say something: the hero, status
banners, callouts and the three evidence sources.
"""
from __future__ import annotations

import html
import json

from nidaan import llm_errors

# ---- tokens (contrast checked in tests/test_ui_theme.py) ----
TOKENS = {
    "ground": "#F7F6F2",   # page: warm neutral
    "panel": "#FFFFFF",    # surfaces
    "line": "#E5E2DB",     # hairlines (decorative; never the only carrier of meaning)
    "ink": "#14213D",      # structure: headings, numbers, structural anchors
    "text": "#1F2329",     # body text
    "muted": "#5B6170",    # secondary text
    "accent": "#2459E0",   # interaction: actions, selection, links, focus, running; the Nidaan series
    "teal": "#0B7470",     # observation and system health
    "ok": "#1D7447",       # independently established success only
    "warn": "#8A5A00",     # retry, waiting, quota, recoverable issues
    "fail": "#B3261E",     # established failures and harmful outcomes
    "idle": "#5F6670",     # incomplete / not started / unproven
}
WASHES = {  # pale surfaces paired with the token of the same name; text tokens keep >= 4.5:1 on all of them
    "accent": "#EEF3FD", "teal": "#E8F4F2", "ok": "#EAF5EE", "warn": "#FDF4E2", "fail": "#FCEEEC", "ink": "#EEF0F5",
}
SEMANTICS = {
    "ink": "structure and emphasis, never status",
    "accent": "something you can act on, the current selection, a run in progress, the Nidaan series",
    "teal": "observations of the system (OBSERVE events, component health)",
    "ok": "success established independently (verifier pass, simulator goal holds, payout sent once)",
    "warn": "retries, waiting, quota use, recoverable or explanatory issues",
    "fail": "an established failure (goal not met, duplicate payout, refused or rejected action, error)",
    "idle": "not started, incomplete, or a claim not yet independently proven",
}
# Arm identity colours (dataviz validator: passes in the order nidaan, oneshot, runbook; magenta is below 3:1
# on white, so every use carries a visible text label and the values are also printed).
ARM_COLORS = {"nidaan": "#2459E0", "oneshot": "#E87BA4", "runbook": "#4A3AA7"}
ARM_ORDER = ("nidaan", "oneshot", "runbook")

SANS = "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Helvetica Neue', Helvetica, Arial, sans-serif"
MONO = "ui-monospace, 'SF Mono', Menlo, Consolas, monospace"

# state key -> (label, glyph, tone, style, explanation). style: fill | outline | dashed
STATES = {
    "VERIFIED": ("Verified", "✓", "ok", "fill",
                 "The independent verifier passed and the simulator goal check holds."),
    "GOAL_MET": ("Goal met", "✓", "ok", "outline",
                 "The simulator goal check holds. This arm submits no report, so no verifier ran."),
    "GOAL_NOT_MET": ("Goal not met", "✕", "fail", "fill", "The simulator goal check does not hold."),
    "FAILED": ("Failed", "✕", "fail", "fill",
               "No verified recovery: the verifier did not pass, or the simulator goal check does not hold."),
    "ERROR": ("Error", "!", "fail", "dashed",
              "The run stopped on an API, quota or system error, not on an agent decision."),
    "RUNNING": ("Running", "◐", "accent", "outline", "The run is in progress."),
    "INCOMPLETE": ("Incomplete evidence", "○", "idle", "dashed",
                   "The log has no final event, so no outcome can be stated."),
    "NOT_STARTED": ("Not started", "○", "idle", "dashed", "No live run has been started in this process."),
}
STATE_WASH = {"VERIFIED": "ok", "GOAL_MET": "ok", "GOAL_NOT_MET": "fail", "FAILED": "fail", "ERROR": "fail",
              "RUNNING": "accent", "INCOMPLETE": "ink", "NOT_STARTED": "ink"}
EVENT_TONES = {"GOAL": "ink", "PLAN": "ink", "REPLAN": "warn", "OBSERVE": "teal", "ACT": "accent",
               "VERIFY": "ok", "FINAL": "ink", "ERROR": "fail"}
OUTCOME_TONES = {"ok": "muted", "pass": "ok", "refused": "fail", "rejected": "fail", "fail": "fail"}

_ROOT = (" ".join(f"--nd-{k}: {v};" for k, v in TOKENS.items()) + " "
         + " ".join(f"--nd-{k}-wash: {v};" for k, v in WASHES.items())
         + f" --nd-sans: {SANS}; --nd-mono: {MONO};")

CSS = "<style>:root { " + _ROOT + " }" + """
/* ---- page frame (layout only; Streamlit containers addressed by data-testid or st-key-* classes) ---- */
[data-testid="stMainBlockContainer"] { max-width: 1180px; padding-top: 4rem; padding-bottom: 4rem; }
[data-testid="stSidebarHeader"] { height: 2.75rem; padding-bottom: 0; }
[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] { padding-top: 0.25rem; }
@media (max-width: 900px) {
  [data-testid="stHorizontalBlock"] { flex-wrap: wrap; }
  [data-testid="stColumn"] { flex: 1 1 100% !important; width: 100% !important; min-width: 100%; } }
[data-testid="stHeaderActionElements"] { display: none !important; }
h1, h2, h3 { letter-spacing: -0.015em; color: var(--nd-ink); }
:focus-visible { outline: 2px solid var(--nd-accent) !important; outline-offset: 2px; }
@media (prefers-reduced-motion: reduce) { *, *::before, *::after { animation-duration: .01ms !important;
  animation-iteration-count: 1 !important; transition-duration: .01ms !important; scroll-behavior: auto !important; } }
/* Static tables: full-strength header text (Streamlit fades it by default). */
[data-testid="stTable"] th { color: var(--nd-text) !important; }

/* Evidence and launch containers: a coloured top rule names the source (st.container(key=...) -> .st-key-<key>). */
.st-key-ev_claim, .st-key-ev_verifier_ok, .st-key-ev_verifier_fail, .st-key-ev_verifier_idle,
.st-key-ev_sim_ok, .st-key-ev_sim_fail, .st-key-ev_sim_idle, .st-key-launch_runbook, .st-key-launch_nidaan {
  background: var(--nd-panel); }
.st-key-ev_claim, .st-key-ev_verifier_idle, .st-key-ev_sim_idle { border-top: 3px solid var(--nd-idle) !important; }
.st-key-ev_verifier_ok, .st-key-ev_sim_ok { border-top: 3px solid var(--nd-ok) !important; }
.st-key-ev_verifier_fail, .st-key-ev_sim_fail { border-top: 3px solid var(--nd-fail) !important; }
.st-key-launch_runbook { border-top: 3px solid var(--nd-ink) !important; }
.st-key-launch_nidaan { border-top: 3px solid var(--nd-accent) !important; }

/* ---- primitives ---- */
.nd-mono { font-family: var(--nd-mono); font-variant-numeric: tabular-nums; }
.nd-muted { color: var(--nd-muted); }
.nd-row { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.nd-badge, .nd-chip { display: inline-flex; gap: 6px; align-items: center; border-radius: 6px; white-space: nowrap;
  padding: 2px 9px; font-size: 13px; font-weight: 600; line-height: 1.6; border: 1px solid currentColor; }
.nd-chip { font-weight: 500; color: var(--nd-ink); border-color: var(--nd-line); background: var(--nd-panel);
  white-space: normal; }
.nd-chip b { font-family: var(--nd-mono); font-weight: 600; color: var(--nd-accent); margin-right: 2px; }
.nd-fill { background: currentColor; }
.nd-fill > span { color: #FFFFFF; }
.nd-dashed { border-style: dashed; }
.nd-plain { border-color: transparent; background: none; padding-left: 0; padding-right: 10px; }
.nd-t-ok { color: var(--nd-ok); } .nd-t-fail { color: var(--nd-fail); } .nd-t-warn { color: var(--nd-warn); }
.nd-t-idle { color: var(--nd-idle); } .nd-t-accent { color: var(--nd-accent); } .nd-t-teal { color: var(--nd-teal); }
.nd-t-muted { color: var(--nd-muted); } .nd-t-text { color: var(--nd-text); } .nd-t-ink { color: var(--nd-ink); }

/* ---- brand bar ---- */
.nd-brand { display: flex; align-items: center; gap: 12px; margin: 0 0 16px; }
.nd-mark { width: 22px; height: 22px; border-radius: 6px; background: var(--nd-ink); position: relative; flex: none; }
.nd-mark::after { content: ""; position: absolute; left: 6px; top: 6px; width: 10px; height: 10px; border-radius: 50%;
  background: var(--nd-accent); box-shadow: 0 0 0 2px var(--nd-ink); }
.nd-brand b { font-size: 19px; letter-spacing: -0.01em; color: var(--nd-ink); }
.nd-brand span { color: var(--nd-muted); font-size: 15px; }

/* ---- hero: the one tinted region of the Overview ---- */
.nd-herobox { display: grid; grid-template-columns: minmax(0, 1.65fr) minmax(220px, 1fr); gap: 32px;
  background: linear-gradient(180deg, var(--nd-accent-wash), #F4F7FE); border: 1px solid #DCE5FA;
  border-radius: 16px; padding: 34px 36px; margin: 22px 0 10px; }
@media (max-width: 900px) { .nd-herobox { grid-template-columns: 1fr; padding: 26px 22px; } }
.nd-hero { margin: 0 0 12px; max-width: 22ch; text-wrap: balance; font-size: clamp(2.1rem, 4vw, 3rem);
  line-height: 1.06; font-weight: 700; letter-spacing: -0.03em; color: var(--nd-ink); }
.nd-lede { font-size: 1.125rem; line-height: 1.55; color: #3D4555; max-width: 58ch; margin: 0; }
.nd-glance { border-left: 1px solid #D3DDF5; padding-left: 24px; align-self: center; }
@media (max-width: 900px) { .nd-glance { border-left: 0; padding-left: 0; border-top: 1px solid #D3DDF5; padding-top: 16px; } }
.nd-glance .nd-gt { margin: 0 0 10px; font-size: 13px; font-weight: 600; color: var(--nd-accent); letter-spacing: 0.02em; }
.nd-glance ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 6px; }
.nd-glance li { display: grid; grid-template-columns: 3ch 1fr; gap: 14px; align-items: baseline; margin: 0;
  font-size: 15px; color: #3D4555; }
.nd-glance li b { font-size: 22px; font-weight: 650; color: var(--nd-ink); font-variant-numeric: tabular-nums;
  text-align: right; }
.nd-glance .nd-gnote { margin: 12px 0 0; padding-top: 10px; border-top: 1px solid #D3DDF5; font-size: 13px; color: #3D4555; }
.nd-section-title { font-size: 2.25rem; font-weight: 700; letter-spacing: -0.025em; line-height: 1.15;
  margin: 24px 0 6px; color: var(--nd-ink); }
.nd-kicker { font-size: 15px; color: var(--nd-muted); margin: 0 0 18px; max-width: 70ch; line-height: 1.5; }
.nd-step-label { display: flex; align-items: center; gap: 10px; margin: 22px 0 8px; padding: 0; font-size: 17px;
  font-weight: 650; color: var(--nd-ink); line-height: 1.4; letter-spacing: -0.01em; }
.nd-step-label i { font-style: normal; width: 24px; height: 24px; border-radius: 50%; display: inline-grid;
  place-items: center; font-size: 13px; color: #FFF; background: var(--nd-ink); font-variant-numeric: tabular-nums; }

/* ---- stat strip ---- */
.nd-stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); margin: 12px 0 8px;
  background: var(--nd-panel); border: 1px solid var(--nd-line); border-radius: 12px; overflow: hidden; }
.nd-stat { padding: 16px 20px; }
.nd-stat + .nd-stat { border-left: 1px solid var(--nd-line); }
.nd-stat .nd-k { font-size: 13px; color: var(--nd-muted); font-weight: 500; }
.nd-stat .nd-v { font-size: 2rem; font-weight: 650; letter-spacing: -0.02em; line-height: 1.2; margin-top: 4px;
  font-variant-numeric: tabular-nums; }
.nd-stat .nd-s { font-size: 13px; color: var(--nd-muted); margin-top: 2px; line-height: 1.45; }
.nd-meter { height: 6px; background: var(--nd-ink-wash); border-radius: 3px; margin-top: 10px; overflow: hidden; }
.nd-meter > i { display: block; height: 100%; background: var(--nd-accent); border-radius: 3px; }
@media (max-width: 760px) { .nd-stat + .nd-stat { border-left: 0; border-top: 1px solid var(--nd-line); } }

/* ---- workflow: a connected, numbered sequence (the content is a sequence) ---- */
.nd-flow { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 0; margin: 12px 0 6px; }
@media (max-width: 1000px) { .nd-flow { grid-template-columns: repeat(2, minmax(0, 1fr)); row-gap: 20px; } }
@media (max-width: 560px) { .nd-flow { grid-template-columns: 1fr; } }
.nd-flow > div { position: relative; padding: 0 18px 0 0; }
.nd-flow .nd-node { display: flex; align-items: center; margin-bottom: 12px; }
.nd-flow .nd-node i { font-style: normal; width: 30px; height: 30px; border-radius: 50%; display: inline-grid;
  place-items: center; font-size: 14px; font-weight: 650; color: #FFF; flex: none; font-variant-numeric: tabular-nums; }
.nd-flow .nd-node::after { content: ""; flex: 1; height: 2px; margin-left: 10px; background: var(--nd-line); }
.nd-flow > div:last-child .nd-node::after { background: none; }
.nd-flow b { display: block; font-size: 17px; color: var(--nd-ink); margin-bottom: 4px; }
.nd-flow p { margin: 0; font-size: 15px; color: var(--nd-muted); line-height: 1.5; }

/* ---- definitions ---- */
.nd-defs { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 8px 32px; margin: 8px 0; }
.nd-defs > div { padding: 12px 0; border-top: 1px solid var(--nd-line); }
.nd-defs b { display: block; font-size: 16px; color: var(--nd-ink); }
.nd-defs p { margin: 4px 0 0; color: var(--nd-muted); font-size: 15px; line-height: 1.5; }
.nd-swatch { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 8px; flex: none; }

/* ---- confidence-interval strips (dot = observed rate, band = Wilson 95% CI) ---- */
.nd-forest { background: var(--nd-panel); border: 1px solid var(--nd-line); border-radius: 12px; padding: 16px 20px 10px;
  margin: 8px 0 12px; container-type: inline-size; }
.nd-forest .nd-ftitle { margin: 0 0 2px; padding: 0; font-size: 15px; font-weight: 650; color: var(--nd-ink);
  letter-spacing: -0.01em; line-height: 1.4; }
.nd-forest .nd-fsub { font-size: 13px; color: var(--nd-muted); margin: 0 0 10px; }
.nd-frow { display: grid; grid-template-columns: minmax(0, 1fr) auto; grid-template-areas: "label val" "track track";
  gap: 4px 14px; align-items: baseline; padding: 7px 0; }
.nd-frow .nd-flabel { grid-area: label; font-size: 14px; color: var(--nd-text); display: flex; align-items: center; }
.nd-frow .nd-track { grid-area: track; }
.nd-frow .nd-fval { grid-area: val; font-size: 14px; color: var(--nd-ink); font-variant-numeric: tabular-nums;
  display: flex; gap: 8px; align-items: baseline; justify-content: flex-end; flex-wrap: wrap; }
.nd-frow .nd-fval small { font-size: 12px; color: var(--nd-muted); }
.nd-track { position: relative; height: 22px; margin: 0 8px;
  background: linear-gradient(90deg, transparent calc(25% - 0.5px), var(--nd-line) calc(25% - 0.5px), var(--nd-line) calc(25% + 0.5px), transparent calc(25% + 0.5px),
    transparent calc(50% - 0.5px), var(--nd-line) calc(50% - 0.5px), var(--nd-line) calc(50% + 0.5px), transparent calc(50% + 0.5px),
    transparent calc(75% - 0.5px), var(--nd-line) calc(75% - 0.5px), var(--nd-line) calc(75% + 0.5px), transparent calc(75% + 0.5px)); }
.nd-track::before { content: ""; position: absolute; left: 0; right: 0; top: 50%; height: 1px; background: var(--nd-line); }
.nd-ci { position: absolute; top: 6px; height: 10px; border-radius: 5px; opacity: 0.45; }
.nd-pt { position: absolute; top: 4px; width: 14px; height: 14px; margin-left: -7px; border-radius: 50%;
  box-shadow: 0 0 0 2px var(--nd-panel), 0 0 0 3px rgba(20, 33, 61, 0.45); }
.nd-axis { display: flex; justify-content: space-between; margin: 2px 8px 0; font-size: 12px; color: var(--nd-muted);
  font-variant-numeric: tabular-nums; }

/* ---- callouts and banners ---- */
.nd-banner { display: flex; gap: 14px; align-items: flex-start; padding: 16px 20px; border-radius: 12px;
  margin: 6px 0 18px; border: 1px solid transparent; }
.nd-banner .nd-explain { color: var(--nd-text); font-size: 15px; line-height: 1.5; }
.nd-banner .nd-explain + .nd-explain { color: #3D4555; margin-top: 2px; }
.nd-w-ok { background: var(--nd-ok-wash); border-color: #CDE7D7; }
.nd-w-fail { background: var(--nd-fail-wash); border-color: #F3D1CC; }
.nd-w-warn { background: var(--nd-warn-wash); border-color: #F1DDB1; }
.nd-w-accent { background: var(--nd-accent-wash); border-color: #D5E0FA; }
.nd-w-teal { background: var(--nd-teal-wash); border-color: #C9E4E0; }
.nd-w-ink { background: var(--nd-ink-wash); border-color: #DCE0EA; }
.nd-callout { border-radius: 10px; padding: 12px 16px; margin: 8px 0 12px; font-size: 15px; line-height: 1.5;
  border: 1px solid transparent; color: var(--nd-text); }
.nd-callout .nd-ct { font-weight: 650; display: block; margin-bottom: 2px; }

/* ---- component tiles (environment) ---- */
.nd-tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 0 24px; margin: 8px 0 12px; }
.nd-tile { padding: 12px 0; border-top: 1px solid var(--nd-line); }
.nd-tile .nd-k { color: var(--nd-muted); font-size: 13px; }
.nd-tile .nd-v { font-size: 1.25rem; font-weight: 650; margin-top: 2px; font-variant-numeric: tabular-nums; }
.nd-tile .nd-s { font-size: 13px; color: var(--nd-muted); }

/* ---- payout ledger ---- */
.nd-ledger-wrap { container-type: inline-size; }
.nd-ledger { display: grid; grid-template-columns: repeat(10, minmax(0, 1fr)); gap: 6px; margin: 8px 0 4px; }
@container (max-width: 760px) { .nd-ledger { grid-template-columns: repeat(5, minmax(0, 1fr)); } }
@container (max-width: 380px) { .nd-ledger { grid-template-columns: repeat(4, minmax(0, 1fr)); }
  .nd-cell .nd-id, .nd-cell .nd-amt { white-space: normal; overflow-wrap: anywhere; } }
.nd-cell { border-radius: 8px; padding: 7px 6px; text-align: center; font-size: 12px; line-height: 1.4;
  border: 1px solid var(--nd-line); background: var(--nd-panel); color: var(--nd-muted); min-width: 0; }
.nd-cell .nd-m { display: block; font-size: 15px; font-weight: 650; color: var(--nd-idle); }
.nd-cell .nd-id, .nd-cell .nd-amt { display: block; font-family: var(--nd-mono); white-space: nowrap; }
.nd-cell.nd-sent { border-color: #BFDFCB; color: var(--nd-muted); }
.nd-cell.nd-sent .nd-m { color: var(--nd-ok); }
.nd-cell.nd-dup { border: 2px solid var(--nd-fail); background: var(--nd-fail-wash); color: #7A2019; }
.nd-cell.nd-dup .nd-m { color: var(--nd-fail); }
.nd-legend { font-size: 13px; color: var(--nd-muted); margin: 2px 0 12px; }

/* ---- event spine ---- */
.nd-spine { margin: 6px 0; background: var(--nd-panel); border: 1px solid var(--nd-line); border-radius: 12px;
  padding: 2px 18px; }
.nd-ev { display: grid; grid-template-columns: 52px minmax(0, 1fr); gap: 14px; padding: 12px 0;
  border-top: 1px solid var(--nd-line); }
.nd-spine > .nd-ev:first-child { border-top: 0; }
.nd-ev .nd-seq { color: var(--nd-muted); text-align: right; font-size: 13px; padding-top: 3px; }
.nd-ev .nd-head { display: flex; flex-wrap: wrap; gap: 6px 10px; align-items: baseline; }
.nd-ev .nd-kind { font-weight: 700; font-size: 12px; letter-spacing: 0.04em; padding: 1px 7px; border-radius: 5px; }
.nd-k-ink { color: var(--nd-ink); background: var(--nd-ink-wash); } .nd-k-warn { color: var(--nd-warn); background: var(--nd-warn-wash); }
.nd-k-teal { color: var(--nd-teal); background: var(--nd-teal-wash); } .nd-k-accent { color: var(--nd-accent); background: var(--nd-accent-wash); }
.nd-k-ok { color: var(--nd-ok); background: var(--nd-ok-wash); } .nd-k-fail { color: var(--nd-fail); background: var(--nd-fail-wash); }
.nd-k-text, .nd-k-idle, .nd-k-muted { color: var(--nd-ink); background: var(--nd-ink-wash); }
.nd-ev .nd-call { font-family: var(--nd-mono); font-size: 14px; overflow-wrap: anywhere; color: var(--nd-ink); }
.nd-ev .nd-goaltext { font-size: 15px; line-height: 1.5; }
.nd-ev .nd-why { color: var(--nd-muted); font-size: 15px; margin-top: 3px; line-height: 1.45; }
.nd-pre { white-space: pre-wrap; overflow-wrap: anywhere; font-family: var(--nd-mono); font-size: 13px;
  line-height: 1.5; margin: 6px 0 0; color: var(--nd-text); background: var(--nd-ground); padding: 8px 10px;
  border-radius: 8px; }
.nd-ev.nd-refused { box-shadow: inset 3px 0 0 var(--nd-fail); padding-left: 10px; }
.nd-ev.nd-replan, .nd-ev.nd-retry { box-shadow: inset 3px 0 0 var(--nd-warn); padding-left: 10px; }
.nd-ev details summary { cursor: pointer; color: var(--nd-muted); font-size: 13px; margin-top: 6px; }
.nd-evalonly { border: 1px dashed var(--nd-idle); border-radius: 8px; padding: 6px 10px; margin-top: 8px;
  font-size: 13px; color: var(--nd-muted); overflow-wrap: anywhere; }
.nd-meta { font-size: 12px; color: var(--nd-muted); margin-top: 6px; overflow-wrap: anywhere; }

/* ---- verification panels ---- */
.nd-evhead { display: flex; flex-direction: column; align-items: flex-start; gap: 6px; margin: 0 0 8px; }
.nd-evhead .nd-evt { margin: 0; padding: 0; font-size: 17px; font-weight: 650; color: var(--nd-ink); line-height: 1.4;
  letter-spacing: -0.01em; }
.nd-evhead .nd-badge { white-space: normal; text-align: left; }
.nd-panel-body { font-size: 15px; line-height: 1.5; }
.nd-panel-body p, .nd-panel-body li { font-size: 15px; line-height: 1.5; margin: 0 0 6px; }
.nd-panel-body ul { padding-left: 1.2em; margin: 4px 0 10px; }
.nd-panel-body ul.nd-checks { padding-left: 0; }
.nd-src { font-size: 13px; color: var(--nd-muted); margin: 0 0 12px; line-height: 1.45; }
.nd-checks { list-style: none; padding: 0; margin: 6px 0 10px; }
.nd-checks li { padding: 3px 0; margin: 0; }
.nd-panel-h { font-size: 13px; color: var(--nd-muted); margin: 12px 0 4px; font-weight: 600; }
.nd-faults { display: flex; flex-wrap: wrap; gap: 6px; margin: 6px 0 2px; }
.nd-prov { font-size: 15px; color: var(--nd-muted); margin: 0 0 12px; overflow-wrap: anywhere; line-height: 1.5; }
.nd-prov b { color: var(--nd-ink); font-weight: 600; }
.nd-prov .nd-mono { font-size: 13px; }
.nd-prov.nd-live b { color: var(--nd-accent); }
.nd-h4 { font-size: 1.0625rem; font-weight: 650; margin: 18px 0 6px; padding: 0; line-height: 1.4;
  letter-spacing: -0.01em; color: var(--nd-ink); }
/* Custom headings inside st.markdown: Streamlit's own h1-h4 rules are more specific, so these use h*.class. */
h3.nd-group { font-size: 13px !important; font-weight: 700; letter-spacing: 0.04em; color: var(--nd-muted); margin: 22px 0 2px;
  padding: 0; line-height: 1.4; }
h2.nd-h4, h2.nd-evt, h2.nd-step-label { font-size: 17px !important; }
h3.nd-lt, h3.nd-ftitle, h4.nd-ftitle { font-size: 17px !important; }
.nd-forest .nd-ftitle { font-size: 15px !important; }
.nd-launch .nd-lt { margin: 0 0 6px; padding: 0; font-size: 17px; font-weight: 650; color: var(--nd-ink); line-height: 1.4;
  letter-spacing: -0.01em; }
.nd-launch p { margin: 0 0 8px; font-size: 15px; line-height: 1.5; color: var(--nd-muted); }
.nd-launch strong { color: var(--nd-text); }
</style>"""


def esc(x) -> str:
    return html.escape(str(x))


def pretty(v) -> str:
    return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, indent=2)


def pre(v) -> str:
    """Escaped preformatted block. A styled <div>, because Streamlit's markdown renderer replaces <pre> with its own
    element. Newlines become &#10; so the HTML stays on one line (a line break would end the raw-HTML block)."""
    return "<div class='nd-pre'>" + esc(pretty(v)).replace("\n", "&#10;") + "</div>"


def badge(state: str) -> str:
    label, glyph, tone, style, _ = STATES[state]
    cls = {"fill": "nd-fill", "outline": "", "dashed": "nd-dashed"}[style]
    return (f"<span class='nd-badge nd-t-{tone} {cls}'><span aria-hidden='true'>{glyph}</span>"
            f"<span>{esc(label)}</span></span>")


def outcome_badge(outcome) -> str:
    if not outcome:
        return ""
    tone = OUTCOME_TONES.get(str(outcome), "muted")
    return f"<span class='nd-badge nd-t-{tone}'>{esc(outcome)}</span>"


def chip(text: str, code: str | None = None) -> str:
    c = f"<b>{esc(code)}</b>" if code else ""
    return f"<span class='nd-chip'>{c}{esc(text)}</span>"


def provenance(kind: str, detail: str) -> str:
    """kind: 'live' or 'recorded'. Always shown next to run evidence so the two are never confused."""
    label = {"live": "Live run: this dashboard session, not part of the evaluation",
             "recorded": "Recorded run: evaluation evidence"}[kind]
    cls = " nd-live" if kind == "live" else ""
    return f"<div class='nd-prov{cls}'><b>{esc(label)}</b><br><span class='nd-mono'>{esc(detail)}</span></div>"


def banner(state: str, detail: str = "", live: bool = False) -> str:
    """live=True only for the live-run banner, which updates while a run is in progress (a polite live region)."""
    label, glyph, tone, style, explain = STATES[state]
    extra = f"<div class='nd-explain'>{esc(detail)}</div>" if detail else ""
    role = " role='status'" if live else ""
    return (f"<div class='nd-banner nd-w-{STATE_WASH[state]}'{role}><div>{badge(state)}</div>"
            f"<div><div class='nd-explain'>{esc(explain)}</div>{extra}</div></div>")


def callout(tone: str, title: str, text: str = "") -> str:
    t = f"<span class='nd-ct nd-t-{tone}'>{esc(title)}</span>"
    return f"<div class='nd-callout nd-w-{tone}' role='note'>{t}{esc(text)}</div>"


def brand(subtitle: str) -> str:
    return (f"<div class='nd-brand'><span class='nd-mark' aria-hidden='true'></span><b>Nidaan</b>"
            f"<span>{esc(subtitle)}</span></div>")


def hero(title: str, lede: str, glance: list[tuple[str, str]] | None = None, note: str = "") -> str:
    """The Overview's tinted hero. `glance` = (value, label) facts read from real data; `note` = a separate line."""
    g = ""
    if glance:
        rows = "".join(f"<li><b>{esc(v)}</b><span>{esc(k)}</span></li>" for v, k in glance)
        n = f"<p class='nd-gnote'>{esc(note)}</p>" if note else ""
        g = f"<div class='nd-glance'><p class='nd-gt'>Evidence at a glance</p><ul>{rows}</ul>{n}</div>"
    return (f"<div class='nd-herobox'><div><h1 class='nd-hero'>{esc(title)}</h1>"
            f"<div class='nd-lede'>{esc(lede)}</div></div>{g}</div>")


def section_title(title: str, kicker: str = "") -> str:
    k = f"<div class='nd-kicker'>{esc(kicker)}</div>" if kicker else ""
    return f"<h1 class='nd-section-title'>{esc(title)}</h1>{k}"


def step_label(n: int, text: str) -> str:
    return f"<h2 class='nd-step-label'><i aria-hidden='true'>{n}</i>{esc(text)}</h2>"


def stat(key: str, value: str, sub: str = "", tone: str = "ink", meter: float | None = None,
         meter_tone: str = "accent") -> str:
    s = f"<div class='nd-s'>{esc(sub)}</div>" if sub else ""
    m = (f"<div class='nd-meter' role='presentation'><i style='width:{max(0.0, min(1.0, meter)) * 100:.1f}%;"
         f"background:var(--nd-{meter_tone})'></i></div>" if meter is not None else "")
    return (f"<div class='nd-stat'><div class='nd-k'>{esc(key)}</div>"
            f"<div class='nd-v nd-t-{tone}'>{esc(value)}</div>{s}{m}</div>")


def stats(items: list[str]) -> str:
    return "<div class='nd-stats'>" + "".join(items) + "</div>"


def flow(steps: list[tuple[str, str, str]]) -> str:
    """Connected numbered sequence; each step is (title, description, tone)."""
    out = "".join(f"<div role='listitem'><div class='nd-node'><i style='background:var(--nd-{tone})' "
                  f"aria-hidden='true'>{i}</i></div><b>{esc(t)}</b><p>{esc(d)}</p></div>"
                  for i, (t, d, tone) in enumerate(steps, 1))
    return f"<div class='nd-flow' role='list'>{out}</div>"


def defs(items: list[tuple[str, str]], colors: list[str] | None = None) -> str:
    out = []
    for i, (t, d) in enumerate(items):
        sw = (f"<span class='nd-swatch' style='background:{colors[i]}' aria-hidden='true'></span>"
              if colors and colors[i] else "")
        out.append(f"<div><b>{sw}{esc(t)}</b><p>{esc(d)}</p></div>")
    return "<div class='nd-defs'>" + "".join(out) + "</div>"


def forest(title: str, subtitle: str, rows: list[dict], level: int = 4) -> str:
    """Dot-and-interval strips on a 0-100% scale. Each row: label, color, and either ci (dict with k, n, rate,
    ci_low, ci_high) or na (text shown instead). Values are printed beside every strip, so colour is never alone."""
    body = []
    for r in rows:
        sw = f"<span class='nd-swatch' style='background:{r['color']}' aria-hidden='true'></span>"
        ci = r.get("ci")
        if not ci:
            body.append(f"<div class='nd-frow nd-na'><div class='nd-flabel'>{sw}{esc(r['label'])}</div>"
                        f"<div class='nd-fval'><small>{esc(r.get('na', 'n/a'))}</small></div></div>")
            continue
        lo, hi, p = ci["ci_low"] * 100, ci["ci_high"] * 100, ci["rate"] * 100
        desc = f"{r['label']}: {ci['k']} of {ci['n']} ({p:.0f}%), Wilson 95% CI {lo:.0f}% to {hi:.0f}%"
        body.append(
            f"<div class='nd-frow'><div class='nd-flabel'>{sw}{esc(r['label'])}</div>"
            f"<div class='nd-track' aria-hidden='true' title='{esc(desc)}'>"
            f"<span class='nd-ci' style='left:{lo:.1f}%;width:{max(hi - lo, 0.8):.1f}%;background:{r['color']}'></span>"
            f"<span class='nd-pt' style='left:{p:.1f}%;background:{r['color']}'></span></div>"
            f"<div class='nd-fval'><span>{ci['k']}/{ci['n']}</span><span>{p:.0f}%</span>"
            f"<small>95% CI {lo:.0f}% to {hi:.0f}%</small></div></div>")
    axis = ("<div class='nd-axis' aria-hidden='true'><span>0%</span><span>25%</span><span>50%</span>"
            "<span>75%</span><span>100%</span></div>") if any(r.get("ci") for r in rows) else ""
    sub = f"<div class='nd-fsub'>{esc(subtitle)}</div>" if subtitle else ""
    return (f"<div class='nd-forest'><h{level} class='nd-ftitle'>{esc(title)}</h{level}>{sub}{''.join(body)}{axis}"
            f"</div>")


def _tile(key: str, value: str, sub: str = "", tone: str = "ink") -> str:
    s = f"<div class='nd-s'>{esc(sub)}</div>" if sub else ""
    return f"<div class='nd-tile'><div class='nd-k'>{esc(key)}</div><div class='nd-v nd-t-{tone}'>{esc(value)}</div>{s}</div>"


def rupees(x: int) -> str:
    return f"₹{x:,}"


def env_tiles(state: dict, components_only: bool = False) -> str:
    """Component tiles from ui.live.sim_state(); every value is read from the simulator."""
    up, running = state["ledger_up"], state["worker_running"]
    dup = state["duplicates"]
    tiles = [_tile("Ledger", "Up" if up else "Down", f"disk {state['disk_pct']}%", "teal" if up else "fail"),
             _tile("Worker", "Running" if running else "Stopped", f"queue depth {state['queue_depth']}",
                   "teal" if running else "fail")]
    if components_only:
        tiles.append(_tile("Settlement checkpoint", str(state["checkpoint"]),
                           "payouts confirmed in order; resume continues after it"))
    else:
        tiles += [_tile("Payouts sent", f"{state['payouts_sent']}/{state['payouts_total']}",
                        f"{rupees(state['settled_amount'])} settled, checkpoint {state['checkpoint']}"),
                  _tile("Duplicate payouts", str(dup), "must stay 0", "fail" if dup else "ink")]
    return "<div class='nd-tiles'>" + "".join(tiles) + "</div>"


def ledger_strip(payouts: list[dict]) -> str:
    """One cell per payout: not sent, sent once, or sent more than once (a duplicate)."""
    cells = []
    for p in payouts:
        n = p["send_count"]
        cls, mark, word = (("nd-dup", f"{n}×", f"sent {n} times, duplicate") if n > 1 else
                           ("nd-sent", "1×", "sent once") if n == 1 else ("", "0×", "not sent"))
        cells.append(f"<div role='listitem' class='nd-cell {cls}' "
                     f"aria-label='{esc(p['id'])}, {esc(rupees(p['amount']))}: {word}'>"
                     f"<span class='nd-m' aria-hidden='true'>{mark}</span><span class='nd-id'>{esc(p['id'])}</span>"
                     f"<span class='nd-amt'>{esc(rupees(p['amount']))}</span></div>")
    return (f"<div class='nd-ledger-wrap'><div class='nd-ledger' role='list' aria-label='Payout ledger'>"
            f"{''.join(cells)}</div></div>")


def checks_list(checks: dict | None) -> str:
    if not checks:
        return "<p class='nd-muted'>No checks recorded.</p>"
    rows = "".join(f"<li><span class='nd-t-{'ok' if v else 'fail'}' aria-hidden='true'>{'✓' if v else '✕'}</span> "
                   f"<span class='nd-mono'>{esc(k)}</span> {'passed' if v else 'failed'}</li>"
                   for k, v in checks.items())
    return f"<ul class='nd-checks'>{rows}</ul>"


def meta_line(meta: dict) -> str:
    """Run metadata (not agent-visible) as one readable line. Every value comes from the event; nothing is derived."""
    parts = []
    if meta.get("ts"):
        parts.append(str(meta["ts"]).replace("T", " ")[:19] + " UTC")
    if meta.get("llm_call") is not None:
        parts.append(f"LLM call {meta['llm_call']}")
    if meta.get("latency_ms") is not None:
        parts.append(f"{meta['latency_ms']:,} ms" if isinstance(meta["latency_ms"], (int, float)) else str(meta["latency_ms"]))
    tok = meta.get("tokens")
    if isinstance(tok, dict) and tok.get("total") is not None:
        parts.append(f"{tok['total']:,} tokens ({tok.get('input', '?'):,} in, {tok.get('output', '?'):,} out)"
                     if all(isinstance(tok.get(k), int) for k in ("input", "output")) else f"{tok['total']:,} tokens")
    elif tok is not None:
        parts.append(f"tokens {json.dumps(tok, ensure_ascii=False)}")
    if meta.get("model"):
        parts.append(str(meta["model"]))
    if meta.get("metrics"):
        parts.append("metrics " + ", ".join(f"{k}={v}" for k, v in meta["metrics"].items()))
    if meta.get("attempt") is not None:
        parts.append(f"attempt {meta['attempt']}")
    if meta.get("retry_in_s") is not None:
        parts.append(f"retried after {meta['retry_in_s']} s")
    if meta.get("error"):
        parts.append(f"error: {meta['error']}")
    return "  ·  ".join(parts)


def spine_event(e: dict, visible: dict, meta: dict, ev: dict, style: dict, head: str, show_eval: bool) -> str:
    """One event of the execution timeline. visible/meta/ev come from ui.data.split_event_fields (SPEC §6 channels);
    style and head from ui.data.event_style / ui.data.headline."""
    kind = style["label"]
    tone = EVENT_TONES.get(kind, "ink")
    if e["type"] == "VERIFY":
        tone = "ok" if e.get("outcome") == "pass" else "fail"
    if e["type"] == "ACT" and e.get("outcome") in ("refused", "rejected"):
        tone = "fail"
    cls = "nd-refused" if style["refused"] else ("nd-replan" if kind == "REPLAN" else "")
    llm_err = e["type"] == "ERROR" and str(e.get("error", "")).startswith("LLM call failed")
    if llm_err:  # a failed model call: say what kind, and whether it was retried (display only)
        ek = e.get("error_kind") or llm_errors.classify(str(e["error"])).kind
        retried = e.get("retry_in_s") is not None
        kind, tone = ("RETRY", "warn") if retried else ("ERROR", "fail")
        cls = "nd-retry" if retried else cls
        head = {"rate_limit": "provider rate limit", "quota_exhausted": "provider daily quota",
                "transient": "provider temporarily unavailable"}.get(ek, "model call failed")
        head += f"; retried after {e['retry_in_s']} s" if retried else "; not retried"
    why = f"<div class='nd-why'>Why: {esc(visible['why'])}</div>" if visible.get("why") else ""
    trig = (f"<div class='nd-why'>Triggered by {esc(', '.join(f'#{t}' for t in visible['triggered_by']))}</div>"
            if visible.get("triggered_by") else "")
    result = pre(visible["result"]) if "result" in visible else ""
    is_goal = e["type"] == "GOAL" and bool(visible.get("goal"))
    skip = ("why", "result", "outcome", "triggered_by") + (("goal",) if is_goal else ())
    rest = {k: v for k, v in visible.items() if k not in skip}
    details = ""
    if rest:
        body = "".join(f"<div><span class='nd-muted'>{esc(k)}</span>{pre(v)}</div>" for k, v in rest.items())
        details = f"<details><summary>Agent-visible fields: {esc(', '.join(rest))}</summary>{body}</details>"
    evbox = (f"<div class='nd-evalonly'>Evaluation-only, never shown to the agent: "
             f"<span class='nd-mono'>{esc(json.dumps(ev, ensure_ascii=False))}</span></div>") if (ev and show_eval) else ""
    metabox = f"<div class='nd-meta'>{esc(meta_line(meta))}</div>" if meta else ""
    call_cls = "nd-goaltext" if is_goal else "nd-call"
    if is_goal:
        head = visible["goal"]
    ob = outcome_badge(e.get("outcome")) if e["type"] in ("ACT", "OBSERVE", "PLAN", "VERIFY") else ""
    return (f"<div class='nd-ev {cls}'><div class='nd-seq nd-mono'>#{esc(e['seq'])}</div><div>"
            f"<div class='nd-head'><span class='nd-kind nd-k-{tone}'>{esc(kind)}</span>"
            f"<span class='{call_cls}'>{esc(head)}</span>{ob}</div>"
            f"{why}{trig}{result}{details}{evbox}{metabox}</div></div>")
