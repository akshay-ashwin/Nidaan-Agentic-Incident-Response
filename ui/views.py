"""The five dashboard sections. Rendering only: metrics come from evaluation.* (unchanged), recorded-run helpers
from ui.data, live runs from ui.live, HTML from ui.theme.

Nothing here starts a run except the Run Runbook / Run Nidaan button callbacks (_start). Loading, refreshing,
switching sections or choosing a scenario never starts one.
"""
from __future__ import annotations

import glob
import json
import pathlib

import pandas as pd
import streamlit as st

from evaluation.aggregate import ARMS, load_results
from evaluation.metrics import DEFINITIONS, compute_run_metrics
from evaluation.scenarios import DEV_SCENARIOS
from nidaan.logger import read_jsonl
from ui import data as D
from ui import live
from ui import theme as T

ROOT = pathlib.Path(__file__).resolve().parent.parent
RECORDED_RUNS_DIR = ROOT / "runs"
ARM_TITLES = {"nidaan": "Nidaan (LLM agent)", "runbook": "Runbook (deterministic)", "oneshot": "One-shot LLM"}
ARM_NOTES = {"runbook": "Hand-written condition-action rules. No model.",
             "oneshot": "One model call on a full snapshot; its action list is executed blindly.",
             "nidaan": "The model chooses every step, observes the result and revises its plan."}
# Development fault types only (SPEC §2); held-out types are never named in the dashboard.
FAULT_NAMES = {"F1": "Bank credential expired", "F2": "Stale signing key", "F4": "Ledger disk full",
               "F6": "Worker stopped", "F7": "Bank rate limit (latent)"}
PHASE_TONES = {"observe": "teal", "decide": "ink", "replan": "warn", "act": "accent", "final": "ink", "error": "fail",
               "goal": "ink"}


def phase_tone(row: dict, outcomes: dict) -> str:
    """Loop-strip colour from what happened, not from the phase's first word."""
    ph = row["phase"]
    if "rejected" in ph or "refused" in ph:
        return "fail"
    if "new failure" in ph:
        return "warn"
    if row["type"] == "VERIFY":
        return "ok" if outcomes.get(row["seq"]) == "pass" else "fail"
    return PHASE_TONES.get(ph.split(" ")[0], "muted")
GOAL_LABELS = {"G1": "worker running and queue empty", "G2": "ledger up", "G3": "every payout sent exactly once"}
ARM_COLUMNS = [ARM_TITLES[a] for a in ("nidaan", "oneshot", "runbook")]  # same order as the charts (theme.ARM_ORDER)
SECTION_NAMES = ("Overview", "Investigate & Run", "Live Execution", "Recovery Verification", "Trace & Evaluation")


def html(s: str) -> None:
    st.markdown(s, unsafe_allow_html=True)


def h4(text: str) -> None:
    """Sub-section heading (an h2 under the section's h1), styled small, without Streamlit's anchor link."""
    html(f"<h2 class='nd-h4'>{T.esc(text)}</h2>")


def go_to(section: str) -> None:
    """Button callback: switch section (runs before the section control is re-created)."""
    st.session_state["section"] = section


def rel(path: str) -> str:
    p = pathlib.Path(path)
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return p.name


def fault_chips(faults: list[str]) -> str:
    return "<div class='nd-faults'>" + "".join(T.chip(FAULT_NAMES.get(f, f), code=f) for f in faults) + "</div>"


def ci_rows(summary: dict | None, key: str, na: str = "no runs in view") -> list[dict]:
    """Forest-strip rows for one SPEC §9 proportion, in the validated arm order. Values come straight from the
    existing aggregation (Wilson intervals); an arm without a value is shown as such, never estimated."""
    rows = []
    for a in T.ARM_ORDER:
        arm = (summary or {}).get("by_arm", {}).get(a)
        ci = arm["spec"].get(key) if arm else None
        reason = na if not arm else ("n/a (no plans)" if key == "appropriate_replanning" and a != "nidaan"
                                     else "n/a (Nidaan only)" if key == "root_cause_component_accuracy"
                                     else "unavailable")
        rows.append({"label": ARM_TITLES[a], "color": T.ARM_COLORS[a], "ci": ci, "na": reason})
    return rows


# ---------------------------------------------------------------- recorded evidence (sidebar)
def load_context() -> dict:
    sb = st.sidebar
    sb.markdown("### Recorded evidence")
    sb.caption("Applies to Overview, Trace & Evaluation and recorded runs in Recovery Verification. "
               "Viewing recorded evidence never calls a model.")
    saved = sorted(glob.glob(str(ROOT / "results" / "*.json")))
    labels = ["Run logs (runs/)"] + [f"Saved results: {pathlib.Path(p).name}" for p in saved]
    source = sb.selectbox("Data source", labels, key="data_source")
    exclude = sb.checkbox("Exclude runs that ended on an API/quota error or were interrupted", value=False,
                          help="Default: everything is included, so nothing is cherry-picked.")
    if source.startswith("Run logs"):
        all_records = D.build_records(str(RECORDED_RUNS_DIR))  # recorded evidence only; live runs use runs_live/
    else:
        all_records = load_results(saved[labels.index(source) - 1])["records"]
    records, counts = D.prepare(all_records, exclude_infra=exclude)
    summary = D.summarize_records(records) if records else None

    notes = [f"{len(records)} runs in view."]
    if counts["non_development_hidden"]:
        notes.append(f"{counts['non_development_hidden']} non-development log(s) hidden.")
    if counts["live_runs_hidden"]:
        notes.append(f"{counts['live_runs_hidden']} live dashboard run(s) hidden; never evaluation evidence.")
    if counts["infrastructure_failures_total"]:
        notes.append(f"{counts['infrastructure_failures_in_view']} of them ended on an API/quota error or were "
                     f"interrupted ({counts['infrastructure_failures_total']} such runs in total).")
    sb.caption(" ".join(notes))
    selected = None
    log_records = [r for r in records if pathlib.Path(r["log_path"]).exists()]
    if log_records:
        run_labels = [_run_choice(r) for r in log_records]
        selected = log_records[sb.selectbox("Recorded run", range(len(run_labels)), key="recorded_run",
                                            format_func=lambda i: run_labels[i], index=len(run_labels) - 1,
                                            help="Used by Trace & Evaluation and by Recovery Verification.")]
    run = live.current_run()
    if run is not None:
        snap = run.snapshot()
        sb.markdown("### Live run")
        sb.caption(f"{T.STATES[_live_state(snap)][0]}: {snap['mode']} on {snap['scenario']}. "
                   "Live runs are never part of the evaluation.")
    return {"records": records, "counts": counts, "summary": summary, "selected": selected}


def _run_choice(r: dict) -> str:
    """Sidebar label: the distinguishing parts first, so a truncated label is still useful."""
    status = r["metrics"]["supplementary"]["final_outcome"] or "incomplete"
    flag = ", API/quota failure" if r.get("api_failure") else (", interrupted" if r.get("incomplete") else "")
    return f"{r['scenario']} · {r['arm']} · {status}{flag} · {r['run_id']}"


def _live_state(snap: dict) -> str:
    if snap["status"] == "running":
        return "RUNNING"
    if snap["status"] == "not_started":
        return "NOT_STARTED"
    return snap["verdict"] or "INCOMPLETE"


# ---------------------------------------------------------------- 1. overview
def overview(ctx: dict) -> None:
    records, summary, counts = ctx["records"], ctx["summary"], ctx["counts"]
    run = live.current_run()
    live_label = "Idle" if run is None else T.STATES[_live_state(run.snapshot())][0]
    glance = [(str(len(records)), "recorded development runs in view"),
              (str(len({r["scenario"] for r in records})), "development scenarios with recorded runs"),
              (str(len((summary or {}).get("by_arm", {}))), "approaches compared on the same scenarios")]
    html(T.hero("Incident response that has to show its evidence.",
                "Nidaan is an LLM agent that restores a simulated payment-settlement pipeline. The model decides "
                "each step, the simulator applies it and refuses unsafe requests, and an independent verifier "
                "checks the result.", glance, f"Live run in this session: {live_label}. Live runs are never counted."))

    st.header("How a run works", anchor=False)
    html(T.flow([("Observe", "Read pipeline status, component configuration and logs.", "teal"),
                 ("Plan", "Write a plan, and revise it citing the observation that changed it.", "ink"),
                 ("Act", "Change one thing. The simulator applies it or refuses an unsafe request.", "accent"),
                 ("Verify", "Submit a report. A deterministic verifier checks it against the system.", "ink")]))

    st.header("Recorded evaluation", anchor=False)
    if not records:
        st.info("No recorded development runs are in view. Runs appear once logs exist in `runs/` (or a results "
                "file in `results/`). Nothing is fabricated.")
    else:
        c1, c2 = st.columns(2, gap="medium")
        with c1:
            html(T.forest("Goal met", "Runs where the simulator goal check held at the end.",
                          ci_rows(summary, "goal_success"), level=3))
        with c2:
            html(T.forest("No duplicate payouts", "Runs that paid every merchant at most once (safety).",
                          ci_rows(summary, "runs_with_zero_duplicates"), level=3))
        notes = []
        for a in T.ARM_ORDER:
            infra = sum(1 for r in records if r["arm"] == a and D.is_infra_failure(r))
            if infra:
                n = (summary["by_arm"].get(a) or {}).get("n_runs", 0)
                notes.append(f"{ARM_TITLES[a]}: {infra} of {n} runs ended on an API/quota error or were interrupted "
                             "and count as failures (sidebar toggle excludes them).")
        st.caption("Dots: observed rate. Bands: Wilson 95% confidence interval. Small n: indicative, not "
                   "statistically significant. " + " ".join(notes))
    html(T.defs([(ARM_TITLES[a], ARM_NOTES[a]) for a in T.ARM_ORDER], [T.ARM_COLORS[a] for a in T.ARM_ORDER]))

    st.header("Go to the evidence", anchor=False)
    b1, b2 = st.columns(2, gap="medium")
    with b1:
        html("<div class='nd-launch'><h3 class='nd-lt'>Recovery evidence</h3><p>The agent's claim, the independent verifier and "
             "the simulator's own goal check, side by side for any run.</p></div>")
        st.button("Open Recovery Verification", key="ov_to_verify", on_click=go_to, args=("Recovery Verification",))
    with b2:
        html("<div class='nd-launch'><h3 class='nd-lt'>Full evaluation</h3><p>Every SPEC §9 metric with confidence intervals, "
             "per-scenario comparisons, traces and raw logs.</p></div>")
        st.button("Open Trace & Evaluation", key="ov_to_trace", on_click=go_to, args=("Trace & Evaluation",))

    st.header("Two kinds of evidence", anchor=False)
    n_live_logs = len(glob.glob(str(live.LIVE_RUNS_DIR / "*.jsonl")))
    html(T.defs([(f"Recorded runs: {len(records)} in view",
                  "Logs in runs/ (or saved results). Every metric in this dashboard is computed from these."),
                 (f"Live runs: {n_live_logs} logged",
                  "Started from Investigate & Run and logged to runs_live/. Never counted in any metric.")],
                [T.TOKENS["ink"], T.TOKENS["accent"]]))


# ---------------------------------------------------------------- 2. investigate & run
def _start(mode: str, scenario: str) -> None:
    """The only place a run is started: called by the Run Runbook / Run Nidaan buttons."""
    try:
        live.start_live_run(mode, scenario, runs_dir=live.LIVE_RUNS_DIR)
    except (live.LiveRunBusy, ValueError, RuntimeError) as e:
        st.session_state["start_error"] = live.redact(str(e))
        return
    st.session_state["start_error"] = None
    if mode == "nidaan":
        st.session_state["confirm_quota"] = False  # confirmation is required again for the next run
    go_to("Live Execution")


def _nidaan_duration_text(records: list[dict]) -> str:
    walls = [r["metrics"]["supplementary"]["wall_clock_s"] for r in records
             if r["arm"] == "nidaan" and not D.is_infra_failure(r)]
    if not walls:
        return "No completed recorded Nidaan runs are in view to indicate a duration."
    return (f"Completed recorded Nidaan runs in view took {min(walls) / 60:.1f} to {max(walls) / 60:.1f} minutes "
            f"(n={len(walls)}).")


def investigate(ctx: dict) -> None:
    import config
    html(T.section_title("Investigate & Run",
                         "Choose a development scenario, inspect its starting state, then start a live run. "
                         "Held-out scenarios cannot be selected or run here."))
    names = list(live.dev_scenarios())
    stored = st.session_state.get("live_scenario", names[0])

    def keep():
        st.session_state["live_scenario"] = st.session_state["w_live_scenario"]
    left, right = st.columns([4, 8], gap="large")
    with left:
        html(T.step_label(1, "Choose a scenario"))
        name = st.selectbox("Scenario", names, index=names.index(stored) if stored in names else 0,
                            key="w_live_scenario", on_change=keep)
        st.session_state["live_scenario"] = name
        preview = live.LiveRun("runbook", name)  # builds the simulator only; nothing is started or logged
        st.markdown(f"Seed `{preview.scenario.seed}`")
        html(T.step_label(2, "Injected faults"))
        html(fault_chips(preview.scenario.faults))
        st.caption("Evaluation-only: the agent is never told these. It has to find them from observations.")
    with right:
        html(T.step_label(3, "Starting state"))
        st.caption("Read from a freshly generated simulator for this scenario. Nothing has run.")
        html(T.env_tiles(preview.initial_state))
        html(T.ledger_strip(preview.initial_state["payouts"]))

    html(T.step_label(4, "Start a live run"))
    busy = live.is_busy()
    st.caption("A live run cannot be stopped once started. One live run at a time. Live runs are logged to "
               "`runs_live/` and never enter the recorded evaluation.")
    if busy:
        html(T.callout("accent", "A live run is in progress.", "Wait for it to finish before starting another; "
                       "follow it in Live Execution."))
    if st.session_state.get("start_error"):
        st.error(f"The run was not started: {st.session_state['start_error']}")
    c1, c2 = st.columns(2, gap="medium")
    with c1, st.container(border=True, key="launch_runbook"):
        html("<div class='nd-launch'><h3 class='nd-lt'>Runbook</h3><p>Deterministic rule-based baseline. "
             "<strong>Makes no model calls</strong> and finishes in seconds.</p></div>")
        st.button("Run Runbook", key="run_runbook", disabled=busy, on_click=_start, args=("runbook", name))
    with c2, st.container(border=True, key="launch_nidaan"):
        html(f"<div class='nd-launch'><h3 class='nd-lt'>Nidaan agent</h3><p>The LLM agent. Sends requests to "
             f"<span class='nd-mono'>{T.esc(config.PROVIDER)}</span> "
             f"(<span class='nd-mono'>{T.esc(config.MODEL_NAME)}</span>).</p></div>")
        html(T.callout("warn", "This run uses API quota",
                       "Every step is a model request against the provider's limits. Confirm below to enable it."))
        key_ok = live.provider_key_present()
        if key_ok:
            st.caption("An API key for this provider is present in `.env`; its value is never shown.")
        else:
            html(T.callout("fail", "No API key for this provider in .env",
                           f"Nidaan cannot run live without a {config.PROVIDER} key."))
        st.caption(_nidaan_duration_text(ctx["records"]))
        confirmed = st.checkbox("I understand this run uses API quota.", key="confirm_quota",
                                disabled=busy or not key_ok, width="stretch")
        st.button("Run Nidaan", key="run_nidaan", type="primary",
                  disabled=busy or not key_ok or not confirmed, on_click=_start, args=("nidaan", name))


# ---------------------------------------------------------------- 3. live execution
def _spine(events: list[dict], show_eval: bool) -> str:
    parts = []
    for e in events:
        vis, meta, ev = D.split_event_fields(e)
        parts.append(T.spine_event(e, vis, meta, ev, D.event_style(e), D.headline(e), show_eval))
    return "<div class='nd-spine'>" + "".join(parts) + "</div>"


def _live_body(polling: bool) -> None:
    run = live.current_run()
    snap = run.snapshot()
    running = snap["status"] == "running"
    state_key = _live_state(snap)
    log = pathlib.Path(snap["log_path"]).name if snap["log_path"] else "no log"
    html(T.provenance("live", f"{snap['run_id']}  ·  runs_live/{log}"))
    detail = f"{snap['mode'].capitalize()} on scenario {snap['scenario']}, started {snap['started_at']} UTC."
    fail = snap.get("llm_failure")
    if snap["status"] == "error":
        detail += " The run stopped before completing; see the error below."
    elif fail:
        detail += (" The incident was not finished, so it is not verified. The simulator state below is real; "
                   "the stop was caused by the model provider, not by the simulator.")
    elif not running and snap["result"]:
        detail += f" Reason recorded by the run: {str(snap['result'].get('reason', ''))[:300]}"
    html(T.banner(state_key, detail, live=True))
    if snap["error"]:
        st.error(snap["error"])  # already redacted by ui.live
    if fail:
        html(T.callout("fail", fail["title"] + ".", f"{fail['text']} {fail['action']}"))
        with st.expander("Diagnostic details (redacted)"):
            st.code(fail["message"], language=None)
    wait = snap.get("waiting")
    if wait:
        what = ("the model provider's tokens-per-minute limit was reached" if wait["kind"] == "rate_limit"
                else "the model provider returned a temporary error")
        html(T.callout("warn", f"Waiting {wait['retry_in_s']} s before retrying (attempt {wait['attempt']})",
                       f"Because {what}. The run continues automatically; nothing has been lost."))
    if snap.get("rate_limit_retries"):
        html(T.callout("warn", f"{snap['rate_limit_retries']} provider rate-limit rejection(s) retried automatically",
                       "Each was retried after the provider's suggested wait. Retries are recorded in the timeline."))

    state = snap["final_state"] if not running else live.sim_state(run.sim)
    sent, total = state["payouts_sent"], state["payouts_total"]
    html(T.stats([
        T.stat("Payouts sent", f"{sent}/{total}", T.rupees(state["settled_amount"]) + " settled",
               meter=sent / total if total else 0.0, meter_tone="accent" if running else "ink"),
        T.stat("Duplicate payouts", str(state["duplicates"]), "must stay 0",
               "fail" if state["duplicates"] else ("ink" if running else "ok")),
        T.stat("Events logged", str(len(snap["events"])), "plans, observations, actions, checks"),
        T.stat("Snapshot", "updating" if running else "after run",
               "read while the run changes it" if running else "read once the run had finished",
               "accent" if running else "ink"),
    ]))
    h4("Payout ledger")
    html(T.ledger_strip(state["payouts"]))
    html("<div class='nd-legend'>Each cell is one payout. 0× not sent, 1× sent once, 2× or more sent more than once "
         "(a duplicate).</div>")
    h4("Components")
    html(T.env_tiles(state, components_only=True))

    st.header("Execution timeline", anchor=False)
    show_eval = st.toggle("Show evaluation-only annotations", value=False, key="live_show_eval",
                          help="Annotations the agent never sees (for example, whether an action exposed a new "
                               "failure). Off by default during a run.")
    if snap["events"]:
        html(_spine(snap["events"], show_eval))
    else:
        st.caption("No events yet.")
    if polling and not running:
        st.rerun()  # the run just finished: one full rerun stops the polling


def live_execution(ctx: dict) -> None:
    html(T.section_title("Live Execution", "The live run started from Investigate & Run, as it happens. "
                                           "Every number below is read from the simulator or the run log."))
    run = live.current_run()
    if run is None:
        html(T.banner("NOT_STARTED", "Start one from Investigate & Run."))
        st.button("Go to Investigate & Run", key="goto_investigate", on_click=go_to, args=("Investigate & Run",))
        return
    polling = run.running
    st.fragment(run_every=1.0 if polling else None)(_live_body)(polling)
    if not polling:
        # Outside the fragment on purpose: a button inside it would only rerun the fragment, not switch section.
        st.button("Open Recovery Verification", key="open_verification", type="primary", on_click=go_to,
                  args=("Recovery Verification",))


# ---------------------------------------------------------------- 4. recovery verification
def _claim_html(claim: dict | None, arm: str) -> str:
    if not claim:
        why = ("This arm does not submit a report." if arm != "nidaan"
               else "No report was submitted in this run.")
        return f"<p class='nd-muted'>No report. {T.esc(why)}</p>"
    rcs = "".join(
        f"<li><span class='nd-mono'>{T.esc(rc.get('component', '?'))}</span>: {T.esc(rc.get('description', ''))}"
        f" <span class='nd-muted'>(evidence {T.esc(', '.join(f'#{x}' for x in rc.get('evidence', [])))})</span></li>"
        for rc in claim.get("root_causes", []))
    acts = ", ".join(f"#{a}" for a in claim.get("actions", []))
    return (f"<p>Claimed status: <span class='nd-mono'>{T.esc(claim.get('status_claimed', '?'))}</span></p>"
            f"<div class='nd-panel-h'>Root causes named by the agent</div><ul>{rcs or '<li>none</li>'}</ul>"
            f"<div class='nd-panel-h'>Actions the agent says it performed</div>"
            f"<p class='nd-mono'>{T.esc(acts or 'none')}</p>"
            f"<div class='nd-panel-h'>Summary</div><p>{T.esc(claim.get('summary', ''))}</p>")


def _evhead(title: str, label: str, tone: str, note: str = "") -> str:
    glyph = {"ok": "✓", "fail": "✕", "idle": "○"}.get(tone, "○")
    style = "nd-fill" if tone in ("ok", "fail") else "nd-dashed"
    n = f"<div class='nd-src' style='margin:2px 0 0'>{T.esc(note)}</div>" if note else ""
    return (f"<div class='nd-evhead'><h2 class='nd-evt'>{T.esc(title)}</h2><span class='nd-badge nd-t-{tone} {style}'>"
            f"<span aria-hidden='true'>{glyph}</span><span>{T.esc(label)}</span></span></div>{n}")


def _verifier_html(history: list[dict], arm: str) -> str:
    if not history:
        return ("<p class='nd-muted'>The verifier did not run"
                + (": this arm submits no report.</p>" if arm != "nidaan" else ".</p>"))
    out = []
    for i, v in enumerate(history, 1):
        badge = T.outcome_badge(v["outcome"]) if len(history) > 1 else ""  # the header already says pass/fail
        out.append(f"<div class='nd-panel-h'>Attempt {i}, event <span class='nd-mono'>#{T.esc(v['seq'])}</span> "
                   f"{badge}</div>{T.checks_list(v['checks'])}"
                   f"<p class='nd-muted'>{T.esc(v['message'] or '')}</p>")
    return "".join(out)


def _ground_truth_html(gt: dict | None, goals: dict | None) -> str:
    if gt is None:
        return "<p class='nd-muted'>No final simulator state (the run has not finished or the log has no FINAL event).</p>"
    rows = ""
    if goals:
        rows = "".join(f"<li><span class='nd-t-{'ok' if ok else 'fail'}' aria-hidden='true'>{'✓' if ok else '✕'}</span> "
                       f"<span class='nd-mono'>{T.esc(g)}</span> {T.esc(GOAL_LABELS.get(g, ''))}: "
                       f"{'holds' if ok else 'does not hold'}</li>" for g, ok in goals.items())
        rows = f"<ul class='nd-checks'>{rows}</ul>"
    met = gt.get("goal_met")
    faults = gt.get("faults_active")
    return (rows + f"<p>Goal check overall: <b class='nd-t-{'ok' if met else 'fail'}'>"
            f"<span aria-hidden='true'>{'✓' if met else '✕'}</span> {'holds' if met else 'does not hold'}</b></p>"
            f"<p>Duplicate payouts: <span class='nd-mono'>{T.esc(gt.get('duplicates'))}</span></p>"
            f"<p>Faults still active: <span class='nd-mono'>{T.esc(', '.join(faults) if faults else 'none')}</span></p>")


def verification(ctx: dict) -> None:
    html(T.section_title("Recovery Verification",
                         "Three sources of evidence, kept apart: what the agent claims, what the independent "
                         "verifier checked, and what the simulator itself reports."))
    run = live.current_run()
    options = ["Latest live run", "Recorded run"]
    default = st.session_state.get("verify_source", options[0] if run else options[1])

    def keep():
        if st.session_state["w_verify_source"]:
            st.session_state["verify_source"] = st.session_state["w_verify_source"]
    source = st.segmented_control("Evidence", options, default=default, key="w_verify_source", on_change=keep,
                                  required=True) or default
    st.session_state["verify_source"] = source

    if source == options[0]:
        if run is None:
            html(T.banner("NOT_STARTED", "Start one from Investigate & Run, or choose Recorded run above."))
            return
        snap = run.snapshot()
        arm, state_key = snap["mode"], _live_state(snap)
        log = pathlib.Path(snap["log_path"]).name if snap["log_path"] else "no log"
        prov = T.provenance("live", f"{snap['run_id']}  ·  runs_live/{log}")
        fs = snap["final_state"]
        gt = ({"goal_met": fs["goal_met"], "duplicates": fs["duplicates"], "faults_active": fs["faults_active"]}
              if fs else None)
        goals = fs["goals"] if fs else None
        claim, history = snap["agent_claim"], snap["verify_history"]
        rc = None
        if fs and arm == "nidaan" and snap["events"] and snap["events"][0]["type"] == "GOAL":
            rc = compute_run_metrics(snap["events"])["spec"]["root_cause_exact"]
        payouts = fs["payouts"] if fs else None
        detail = "The run is still in progress; the verdict appears when it finishes." if state_key == "RUNNING" else ""
        if snap.get("llm_failure"):
            detail = (f"{snap['llm_failure']['title']}. The incident was not finished, so it is not verified; "
                      "the simulator's real state is shown below.")
    else:
        rec = ctx["selected"]
        if rec is None:
            st.info("No recorded run is available. Select one in the sidebar once logs exist.")
            return
        events = read_jsonl(rec["log_path"])
        v = D.recorded_verification(rec, events)
        arm, state_key = rec["arm"], v["verdict"]
        prov = T.provenance("recorded", f"{rec['run_id']}  ·  {rel(rec['log_path'])}")
        claim, history, gt, goals, rc, payouts = (v["agent_claim"], v["verify_history"], v["ground_truth"], None,
                                                  v["root_cause_exact"], None)
        detail = "Change the recorded run in the sidebar."

    html(prov)
    html(T.banner(state_key, detail))
    v_tone = ("idle" if not history else "ok" if history[-1]["outcome"] == "pass" else "fail")
    s_tone = "idle" if not gt else ("ok" if gt.get("goal_met") else "fail")
    c1, c2, c3 = st.columns(3, gap="medium")
    with c1, st.container(border=True, key="ev_claim"):
        html(_evhead("Agent report", "Claim, not independently proven", "idle"))
        html("<div class='nd-src'>What the agent says happened, in its own submitted report.</div>")
        html("<div class='nd-panel-body'>" + _claim_html(claim, arm) + "</div>")
    with c2, st.container(border=True, key=f"ev_verifier_{v_tone}"):
        html(_evhead("Independent verifier", {"ok": "Passed", "fail": "Failed", "idle": "Did not run"}[v_tone], v_tone))
        html("<div class='nd-src'>Deterministic checks. V1 goal invariants and no duplicates. V2 claimed "
             "actions exist in the log. V3 'resolved' only if V1 passes. Root causes are not judged.</div>")
        html("<div class='nd-panel-body'>" + _verifier_html(history, arm) + "</div>")
    with c3, st.container(border=True, key=f"ev_sim_{s_tone}"):
        html(_evhead("Simulator goal check", {"ok": "Holds", "fail": "Does not hold", "idle": "No final state"}[s_tone],
                     s_tone))
        html("<div class='nd-src'>The simulator's own state. Evaluation-only; never shown to the agent.</div>")
        html("<div class='nd-panel-body'>" + _ground_truth_html(gt, goals) + "</div>")
        if source != options[0]:
            st.caption("Recorded logs store the overall goal check, not G1-G3 individually.")

    h4("Is the agent's explanation right?")
    st.caption("Evaluation-only, and separate from whether the recovery worked. "
               + DEFINITIONS["root_cause_component_accuracy"])
    if rc is None:
        html(T.callout("ink", "Not applicable or not available for this run.",
                       "Only Nidaan submits root causes." if arm != "nidaan" else ""))
    elif rc:
        html(T.callout("teal", "Explanation matches",
                       "The components named in the agent's last report match the injected faults' components."))
    else:
        html(T.callout("warn", "Explanation does not match",
                       "The components named in the agent's last report do not match the injected faults' "
                       "components. A verified recovery can still come with a wrong explanation."))
    h4("Payout ledger")
    if payouts:
        html(T.ledger_strip(payouts))
    elif source == options[0]:
        st.caption("Shown when the live run has finished.")
    else:
        st.caption("Payout-level state is not stored in recorded logs, so no ledger is shown for recorded runs.")


# ---------------------------------------------------------------- 5. trace & evaluation (recorded)
def _results_at_a_glance(summary: dict) -> None:
    """SPEC §9 proportions grouped by what they measure, drawn from the same aggregation as the tables below."""
    st.header("Results at a glance", anchor=False)
    st.caption("Dots: observed rate. Bands: Wilson 95% confidence interval. Each arm is reported as recorded; "
               "nothing is pooled across prompt versions beyond what the data source in the sidebar contains.")
    groups = [("Performance", [("Goal met", "Simulator goal check held at the end.", "goal_success")]),
              ("Safety", [("No duplicate payouts", "Every merchant paid at most once.", "runs_with_zero_duplicates"),
                          ("Batch status checked before every settlement run", "Checked before resuming or rerunning.",
                           "batch_status_checked_before_every_settlement")]),
              ("Reasoning", [("Appropriate replanning", "Pooled over falsifying events.", "appropriate_replanning"),
                             ("Root-cause component accuracy", "Last report names the right components.",
                              "root_cause_component_accuracy")])]
    for name, items in groups:
        html(f"<h3 class='nd-group'>{T.esc(name)}</h3>")
        cols = st.columns(len(items), gap="medium")
        for col, (title, sub, key) in zip(cols, items):
            with col:
                html(T.forest(title, sub, ci_rows(summary, key)))
    html("<h3 class='nd-group'>Cost</h3>")
    items = []
    for a in T.ARM_ORDER:
        arm = summary["by_arm"].get(a)
        if not arm:
            items.append(T.stat(ARM_TITLES[a], "no runs", "nothing recorded in view", "idle"))
            continue
        c = arm["spec"]["counts"]
        tok, calls = c["total_tokens"], c["llm_calls"]
        no_model = bool(calls and calls.get("mean") == 0)
        value = f"{tok['mean']:,.0f}" if tok and tok.get("mean") is not None else "unavailable"
        sub = ("Tokens per run, mean. Makes no model calls." if no_model else
               f"Tokens per run, mean (n={tok['n_available'] if tok else 0}). LLM calls "
               f"{D.fmt_count(calls)} per run; LLM time {D.fmt_count(c['llm_latency_s'])} s.")
        items.append(T.stat(ARM_TITLES[a], value, sub, "idle" if no_model else "ink"))
    html(T.stats(items))
def trace_and_evaluation(ctx: dict) -> None:
    html(T.section_title("Trace & Evaluation", "Recorded evaluation evidence only. Live dashboard runs never "
                                               "appear here. The data source and run are chosen in the sidebar."))
    records, summary, counts, selected = ctx["records"], ctx["summary"], ctx["counts"], ctx["selected"]
    t_metrics, t_cmp, t_trace, t_evid, t_scn = st.tabs(["Metrics", "Comparison", "Run trace", "Evidence", "Scenarios"])

    with t_metrics:
        if not records:
            st.info("No development runs found yet. Runs appear here once logs exist in `runs/` "
                    "(or a results file in `results/`). Nothing is fabricated.")
        else:
            if counts["infrastructure_failures_in_view"]:
                html(T.callout("warn", f"{counts['infrastructure_failures_in_view']} run(s) in view ended on an "
                               "API/quota error or were interrupted",
                               "They are counted as failures unless excluded in the sidebar."))
            _results_at_a_glance(summary)
            rows = D.comparison_rows(summary["by_arm"])
            spec = pd.DataFrame([r for r in rows if r["Type"] == "SPEC §9"]).drop(columns="Type").rename(
                columns=ARM_TITLES)
            supp = pd.DataFrame([r for r in rows if r["Type"] != "SPEC §9"]).drop(columns="Type").rename(
                columns=ARM_TITLES)
            st.subheader("SPEC §9 metrics", anchor=False)
            st.caption("Proportions show k/n with a Wilson 95% confidence interval. Means show (n = runs with the "
                       "value available). 'unavailable' / 'no runs' / 'n/a' mean exactly that; nothing is estimated.")
            st.table(spec.set_index("Metric")[ARM_COLUMNS])
            st.subheader("Supplementary measurements", anchor=False)
            st.caption("Descriptive only. These are NOT SPEC §9 metrics.")
            st.table(supp.set_index("Metric")[ARM_COLUMNS])
            with st.expander("Definitions and operationalisations"):
                for k, v in DEFINITIONS.items():
                    st.markdown(f"**{k.replace('_', ' ')}** - {v}")

    with t_cmp:
        st.subheader("Side by side, by scenario", anchor=False)
        st.caption("Every development scenario and arm is listed. 'no runs' means that combination has not been run.")
        st.dataframe(pd.DataFrame(D.scenario_matrix(records, DEV_SCENARIOS)).rename(columns=ARM_TITLES)[
                     ["Scenario"] + ARM_COLUMNS], hide_index=True, width="stretch")
        st.subheader("Every run in view", anchor=False)
        if records:
            st.dataframe(pd.DataFrame([{
                "Arm": ARM_TITLES[r["arm"]], "Scenario": r["scenario"], "Repeat": r["repeat"],
                "Goal met": "met" if r["metrics"]["spec"]["goal_success"] else "not met",
                "Duplicates": r["metrics"]["spec"]["duplicate_payouts"],
                "Actions": r["metrics"]["spec"]["actions"],
                "LLM calls": str(r["metrics"]["spec"]["llm_calls"]) if r["metrics"]["spec"]["llm_calls"] is not None
                else "unavailable",
                # One display type per column (mixed int/str breaks Arrow serialisation); values unchanged.
                "Tokens": str(r["metrics"]["spec"]["total_tokens"]) if r["metrics"]["spec"]["total_tokens"] is not None
                else "unavailable",
                "Ended": r["metrics"]["supplementary"]["final_outcome"] or "interrupted",
                "API/quota failure": bool(r.get("api_failure")), "Run": r["run_id"]} for r in records]),
                hide_index=True, width="stretch")
        else:
            st.info("No runs yet.")

    with t_trace:
        if not selected:
            st.info("Select a run in the sidebar once logs exist.")
        else:
            events = read_jsonl(selected["log_path"])
            html(T.provenance("recorded", f"{selected['run_id']}  ·  {rel(selected['log_path'])}"))
            html(T.badge(D.recorded_verdict(selected["arm"], events)))
            st.caption("Logs hold structured events only (plans, reasons, tool calls, results, verification). "
                       "No hidden reasoning is stored or shown. Grey lines are run metadata (tokens, latency, "
                       "errors); dashed boxes are evaluation-only annotations never shown to the agent.")
            show_eval = st.toggle("Show evaluation-only annotations", value=True, key="trace_show_eval")
            html(_spine(events, show_eval))

    with t_evid:
        if not selected:
            st.info("Select a run in the sidebar once logs exist.")
        else:
            events = read_jsonl(selected["log_path"])
            ev = D.evidence_summary(events)
            html(T.provenance("recorded", f"{selected['run_id']}  ·  {rel(selected['log_path'])}"))
            st.download_button("Download this JSONL log", pathlib.Path(selected["log_path"]).read_bytes(),
                               file_name=pathlib.Path(selected["log_path"]).name)
            st.subheader("The loop, as it happened", anchor=False)
            st.caption("observe → decide → act → environment changes → re-observe → replan → verify")
            tl = D.loop_timeline(events)
            outcomes = {e["seq"]: e.get("outcome") for e in events}
            chips = "".join(
                f"<span class='nd-badge nd-plain nd-t-{phase_tone(r, outcomes)}'>"
                f"#{T.esc(r['seq'])} {T.esc(r['phase'].replace('->', '→'))}</span>" for r in tl)
            html(f"<div class='nd-row' style='margin-bottom:16px'>{chips}</div>")
            st.dataframe(pd.DataFrame(tl).rename(columns={"seq": "Event", "phase": "Phase", "event": "What",
                                                          "type": "Type"}),
                         hide_index=True, width="stretch")
            html(T.stats([T.stat("Events", str(sum(ev["event_counts"].values()))),
                          T.stat("Actions", str(len(ev["actions"]))),
                          T.stat("Replans accepted", str(ev["replans"]))]))
            st.caption("Event counts: " + ", ".join(f"{k}={v}" for k, v in sorted(ev["event_counts"].items())) +
                       f" | rejected plan updates: {ev['plan_updates_rejected']}")
            if ev["actions"]:
                st.markdown("**Actions**")
                st.table(pd.DataFrame(ev["actions"]).set_index("seq"))
            if ev["replan_events"]:
                st.markdown("**Replans** (each cites the observation events that triggered it)")
                st.table(pd.DataFrame(ev["replan_events"]).set_index("seq"))
            st.subheader("Final state", anchor=False)
            if ev["final"]:
                f = ev["final"]
                st.markdown(f"**Outcome:** `{f['outcome']}` - {T.esc(str(f['reason'])[:300])}")
                st.markdown("Simulator state at the end (**evaluation-only**, not shown to the agent):")
                st.json(f["state_eval_only"])
                st.markdown("Measured LLM usage:")
                st.json(f["llm_metrics"])
            else:
                st.warning("This run has no FINAL event (it was interrupted).")
            with st.expander("Raw JSONL"):
                st.code("\n".join(json.dumps(e, ensure_ascii=False) for e in events), language="json")

    with t_scn:
        st.subheader("Development scenarios", anchor=False)
        st.caption("Scenario name, seed and injected faults are evaluation-only: the agent is never told them. "
                   "Only development scenarios are shown in this dashboard.")
        st.table(pd.DataFrame([{"Scenario": s.name, "Seed": s.seed, "Faults (evaluation-only)": " + ".join(s.faults),
                                "Fault names": ", ".join(FAULT_NAMES.get(f, f) for f in s.faults)}
                               for s in DEV_SCENARIOS]).set_index("Scenario"))
        if selected:
            st.markdown(f"**Selected run:** scenario `{selected['scenario']}`, seed `{selected['seed']}`, "
                        f"faults `{' + '.join(selected['faults'])}` (evaluation-only).")


SECTIONS = dict(zip(SECTION_NAMES, (overview, investigate, live_execution, verification, trace_and_evaluation)))
