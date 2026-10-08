"""Nidaan judge dashboard (Streamlit). Read-only over existing artifacts:
runs/*.jsonl logs, evaluation metrics/aggregation, and the development scenario definitions.
It never calls an LLM and never starts a run.

    streamlit run ui/app.py
"""
import glob
import html
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from evaluation.aggregate import ARMS, load_results  # noqa: E402
from evaluation.metrics import DEFINITIONS  # noqa: E402
from evaluation.scenarios import DEV_SCENARIOS  # noqa: E402
from nidaan.logger import read_jsonl  # noqa: E402
from ui import data as D  # noqa: E402

st.set_page_config(page_title="Nidaan judge dashboard", layout="wide")

ARM_TITLES = {"nidaan": "Nidaan (LLM agent)", "runbook": "Runbook (deterministic)", "oneshot": "One-shot LLM"}
PHASE_COLORS = {"observe": "#6b7280", "decide": "#4f46e5", "replan": "#d97706", "act": "#0d9488",
                "verify": "#16a34a", "final": "#1f2937", "error": "#dc2626", "goal": "#0ea5e9", "plan": "#dc2626"}


def esc(x) -> str:
    return html.escape(str(x))


def pretty(v) -> str:
    return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------- sidebar
st.sidebar.title("Nidaan")
st.sidebar.caption("Judge dashboard - read-only. No model is called from here.")
saved = sorted(glob.glob(str(ROOT / "results" / "*.json")))
source = st.sidebar.radio("Data source", ["Run logs (runs/)"] + [f"Saved results: {pathlib.Path(p).name}" for p in saved])
exclude = st.sidebar.checkbox("Exclude runs that ended on an API/quota error or were interrupted", value=False,
                              help="Default: everything is included, so nothing is cherry-picked.")

if source.startswith("Run logs"):
    all_records = D.build_records(str(ROOT / "runs"))
else:
    all_records = load_results(saved[[f"Saved results: {pathlib.Path(p).name}" for p in saved].index(source)])["records"]
records, counts = D.prepare(all_records, exclude_infra=exclude)
summary = D.summarize_records(records) if records else None

st.sidebar.markdown(f"**Runs in view:** {len(records)}")
if counts["non_development_hidden"]:
    st.sidebar.caption(f"{counts['non_development_hidden']} non-development log(s) hidden.")
if counts["infrastructure_failures_total"]:
    st.sidebar.caption(f"{counts['infrastructure_failures_total']} run(s) ended on an API/quota error or were "
                       f"interrupted ({counts['infrastructure_failures_in_view']} in view).")

selected = None
log_records = [r for r in records if pathlib.Path(r["log_path"]).exists()]
if log_records:
    labels = [D.run_label(r) for r in log_records]
    selected = log_records[st.sidebar.selectbox("Run for Trace / Evidence", range(len(labels)),
                                                format_func=lambda i: labels[i], index=len(labels) - 1)]

st.title("Nidaan - autonomous incident response, evaluated")
st.caption("An LLM agent decides; SettleSim changes state and enforces safety; a deterministic verifier checks. "
           "Small n: results are indicative, not statistically significant.")

tab_over, tab_trace, tab_scn, tab_cmp, tab_evid = st.tabs(
    ["Overview", "Run Trace", "Scenario", "Comparison", "Evidence"])

# ---------------------------------------------------------------- overview
with tab_over:
    if not records:
        st.info("No development runs found yet. Runs appear here once logs exist in `runs/` "
                "(or a results file in `results/`). Nothing is fabricated.")
    else:
        if counts["infrastructure_failures_in_view"]:
            st.warning(f"{counts['infrastructure_failures_in_view']} run(s) in view ended on an API/quota error "
                       "or were interrupted. They are counted as failures unless excluded in the sidebar.")
        rows = D.comparison_rows(summary["by_arm"])
        cols = {"nidaan": ARM_TITLES["nidaan"], "runbook": ARM_TITLES["runbook"], "oneshot": ARM_TITLES["oneshot"]}
        spec = pd.DataFrame([r for r in rows if r["Type"] == "SPEC §9"]).drop(columns="Type").rename(columns=cols)
        supp = pd.DataFrame([r for r in rows if r["Type"] != "SPEC §9"]).drop(columns="Type").rename(columns=cols)
        st.subheader("SPEC §9 metrics")
        st.caption("Proportions show k/n with a Wilson 95% confidence interval. Means show (n = runs with the "
                   "value available). 'unavailable' / 'no runs' / 'n/a' mean exactly that; nothing is estimated.")
        st.dataframe(spec, hide_index=True, use_container_width=True)
        st.subheader("Supplementary measurements")
        st.caption("Descriptive only. These are NOT SPEC §9 metrics.")
        st.dataframe(supp, hide_index=True, use_container_width=True)

        chart_rows = []
        for a in ARMS:
            if a in summary["by_arm"]:
                for label, key in (("Goal success", "goal_success"), ("Zero duplicates", "runs_with_zero_duplicates")):
                    ci = summary["by_arm"][a]["spec"][key]
                    if ci:
                        chart_rows.append({"arm": ARM_TITLES[a], "metric": label, "rate": ci["rate"],
                                           "low": ci["ci_low"], "high": ci["ci_high"]})
        if chart_rows:
            import altair as alt
            df = pd.DataFrame(chart_rows)
            base = alt.Chart(df).encode(x=alt.X("arm:N", title=None, axis=alt.Axis(labelAngle=0)),
                                        xOffset="metric:N", color=alt.Color("metric:N", title=None))
            st.altair_chart(base.mark_bar().encode(y=alt.Y("rate:Q", scale=alt.Scale(domain=[0, 1]), title="rate"))
                            + base.mark_errorbar(color="#374151").encode(y="low:Q", y2="high:Q"),
                            use_container_width=True)
            st.caption("Bars: observed rate. Whiskers: Wilson 95% CI.")
        with st.expander("Definitions and operationalisations"):
            for k, v in DEFINITIONS.items():
                st.markdown(f"**{k.replace('_', ' ')}** - {v}")

# ---------------------------------------------------------------- run trace
with tab_trace:
    if not selected:
        st.info("Select a run in the sidebar once logs exist.")
    else:
        events = read_jsonl(selected["log_path"])
        m = selected["metrics"]
        st.markdown(f"**{D.run_label(selected)}**")
        st.caption("Logs hold structured events only (plans, reasons, tool calls, results, verification). "
                   "No hidden reasoning is stored or shown.")
        st.markdown(
            "<span style='border-left:4px solid #6366f1;padding-left:6px'>agent-visible</span> &nbsp; "
            "<span style='border:1px dashed #9ca3af;padding:1px 6px'>evaluation-only (never shown to the agent)</span>"
            " &nbsp; <span style='color:#9ca3af'>run metadata (tokens, latency, errors)</span>",
            unsafe_allow_html=True)
        for e in events:
            vis, meta, ev = D.split_event_fields(e)
            s = D.event_style(e)
            badge = (f" <span style='background:{s['border']};color:#fff;border-radius:4px;padding:0 6px;"
                     f"font-size:0.75em'>{esc(s['badge'])}</span>") if s["badge"] else ""
            body = ""
            for k, v in vis.items():
                if k in ("outcome",):
                    continue
                body += f"<div><b>{esc(k)}</b>: <pre style='white-space:pre-wrap;margin:0'>{esc(pretty(v))}</pre></div>"
            evbox = ""
            if ev:
                evbox = ("<div style='border:1px dashed #9ca3af;margin-top:6px;padding:4px 8px;font-size:0.85em'>"
                         "<b>evaluation-only</b> " + esc(json.dumps(ev, ensure_ascii=False)) + "</div>")
            metabox = (f"<div style='color:#9ca3af;font-size:0.8em;margin-top:4px'>"
                       f"{esc(json.dumps(meta, ensure_ascii=False))}</div>") if meta else ""
            st.markdown(
                f"<div style='border-left:5px solid {s['border']};border-radius:3px;padding:6px 12px;margin:6px 0;"
                f"{'outline:2px solid #dc2626;' if s['refused'] else ''}background:rgba(128,128,128,0.06)'>"
                f"<div><span style='color:{s['color']};font-weight:700'>#{e['seq']} {esc(s['label'])}</span> "
                f"&nbsp;{esc(D.headline(e))}{badge}</div>{body}{evbox}{metabox}</div>", unsafe_allow_html=True)

# ---------------------------------------------------------------- scenario
with tab_scn:
    st.subheader("Development scenarios")
    st.caption("Scenario name, seed and injected faults are evaluation-only: the agent is never told them. "
               "Only development scenarios are shown in this dashboard.")
    st.dataframe(pd.DataFrame([{"Scenario": s.name, "Seed": s.seed, "Faults (evaluation-only)": " + ".join(s.faults)}
                               for s in DEV_SCENARIOS]), hide_index=True, use_container_width=True)
    if selected:
        st.markdown(f"**Selected run:** scenario `{selected['scenario']}`, seed `{selected['seed']}`, "
                    f"faults `{' + '.join(selected['faults'])}` (evaluation-only).")

# ---------------------------------------------------------------- comparison
with tab_cmp:
    st.subheader("Side by side, by scenario")
    st.caption("Every development scenario and arm is listed. 'no runs' means that combination has not been run.")
    st.dataframe(pd.DataFrame(D.scenario_matrix(records, DEV_SCENARIOS)).rename(columns=ARM_TITLES),
                 hide_index=True, use_container_width=True)
    st.subheader("Every run in view")
    if records:
        st.dataframe(pd.DataFrame([{
            "Arm": ARM_TITLES[r["arm"]], "Scenario": r["scenario"], "Repeat": r["repeat"],
            "Goal met": r["metrics"]["spec"]["goal_success"], "Duplicates": r["metrics"]["spec"]["duplicate_payouts"],
            "Actions": r["metrics"]["spec"]["actions"], "LLM calls": r["metrics"]["spec"]["llm_calls"],
            "Tokens": r["metrics"]["spec"]["total_tokens"] if r["metrics"]["spec"]["total_tokens"] is not None
            else "unavailable",
            "Ended": r["metrics"]["supplementary"]["final_outcome"] or "interrupted",
            "API/quota failure": bool(r.get("api_failure")), "Run": r["run_id"]} for r in records]),
            hide_index=True, use_container_width=True)
    else:
        st.info("No runs yet.")

# ---------------------------------------------------------------- evidence
with tab_evid:
    if not selected:
        st.info("Select a run in the sidebar once logs exist.")
    else:
        events = read_jsonl(selected["log_path"])
        ev = D.evidence_summary(events)
        st.markdown(f"**Log:** `{pathlib.Path(selected['log_path']).relative_to(ROOT)}`")
        st.download_button("Download this JSONL log", pathlib.Path(selected["log_path"]).read_bytes(),
                           file_name=pathlib.Path(selected["log_path"]).name)
        st.subheader("The loop, as it happened")
        st.caption("observe -> decide -> act -> environment changes -> re-observe -> replan -> verify")
        tl = D.loop_timeline(events)
        chips = ""
        for r in tl:
            key = r["phase"].split(" ")[0]
            color = PHASE_COLORS.get(key, "#6b7280")
            chips += (f"<span style='display:inline-block;margin:2px;padding:2px 8px;border-radius:12px;"
                      f"background:{color};color:#fff;font-size:0.8em'>#{r['seq']} {esc(r['phase'])}</span>")
        st.markdown(chips, unsafe_allow_html=True)
        st.dataframe(pd.DataFrame(tl).rename(columns={"seq": "Event", "phase": "Phase", "event": "What", "type": "Type"}),
                     hide_index=True, use_container_width=True)
        c1, c2, c3 = st.columns(3)
        c1.metric("Events", sum(ev["event_counts"].values()))
        c2.metric("Actions", len(ev["actions"]))
        c3.metric("Replans (accepted)", ev["replans"])
        st.caption("Event counts: " + ", ".join(f"{k}={v}" for k, v in sorted(ev["event_counts"].items())) +
                   f" | rejected plan updates: {ev['plan_updates_rejected']}")
        if ev["actions"]:
            st.markdown("**Actions**")
            st.dataframe(pd.DataFrame(ev["actions"]), hide_index=True, use_container_width=True)
        if ev["replan_events"]:
            st.markdown("**Replans** (each cites the observation events that triggered it)")
            st.dataframe(pd.DataFrame(ev["replan_events"]), hide_index=True, use_container_width=True)
        st.subheader("Final state")
        if ev["final"]:
            f = ev["final"]
            st.markdown(f"**Outcome:** `{f['outcome']}` - {esc(str(f['reason'])[:300])}")
            st.markdown("Simulator state at the end (**evaluation-only**, not shown to the agent):")
            st.json(f["state_eval_only"])
            st.markdown("Measured LLM usage:")
            st.json(f["llm_metrics"])
        else:
            st.warning("This run has no FINAL event (it was interrupted).")
        with st.expander("Raw JSONL"):
            st.code("\n".join(json.dumps(e, ensure_ascii=False) for e in events), language="json")
