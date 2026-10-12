"""Nidaan incident desk (Streamlit).

Recorded evidence: read-only over runs/*.jsonl, results/*.json and the development scenario definitions.
Live runs: started only by an explicit button press in Investigate & Run (Run Runbook; or Run Nidaan after
confirming that it uses model API quota). They are logged to runs_live/ and never mixed into the recorded
evaluation views. Loading, refreshing or switching sections never starts a run or calls a model.

    streamlit run ui/app.py
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

from ui import theme as T  # noqa: E402
from ui import views as V  # noqa: E402

st.set_page_config(page_title="Nidaan", layout="wide")
st.markdown(T.CSS, unsafe_allow_html=True)

ctx = V.load_context()
st.markdown(T.brand("Autonomous incident response, evaluated in a simulated settlement system"),
            unsafe_allow_html=True)
if st.session_state.get("section") is None:
    st.session_state["section"] = V.SECTION_NAMES[0]
section = st.segmented_control("Section", V.SECTION_NAMES, key="section", required=True,
                               label_visibility="collapsed") or V.SECTION_NAMES[0]
V.SECTIONS[section](ctx)
