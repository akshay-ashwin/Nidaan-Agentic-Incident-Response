# Nidaan

An LLM agent for autonomous incident response, evaluated in a controlled, simulated payment-settlement environment
(SettleSim). IA-II Activity 1, Artificial Intelligence.

- Report: `docs/Nidaan_IA2_Report.pdf` (source `docs/Nidaan_IA2_Report.md`)
- Frozen specification: `SPEC.md`; progress log: `PROGRESS.md`; submission checklist and demo script:
  `docs/SUBMISSION_CHECKLIST.md`

## Layout

| Path | Contents |
|---|---|
| `settlesim/` | Deterministic environment, scenario generator, tool wrappers (safety guards) |
| `nidaan/` | LangGraph agent: graph, system prompt, tools/executor, plan validation, verifier, JSONL logger |
| `baselines/` | Classical rule-based runbook; one-shot LLM planner |
| `evaluation/`, `scripts/` | Metrics, Wilson intervals, evaluation driver, offline trace analyser |
| `ui/` | Read-only Streamlit dashboard over recorded runs (never calls a model) |
| `tests/` | Offline tests (no LLM calls) |
| `results/`, `reports/` | Measured results and trace-analysis reports (2026-10-10) |
| `runs/` | JSONL agent interaction logs (gitignored; see the checklist for the evidence logs) |

## Setup

```
python3.13 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env   # add GROQ_API_KEY only for live agent runs; never commit .env
```

## Offline checks (no API use)

```
.venv/bin/python -m pytest -q
.venv/bin/python scripts/analyse_traces.py --log runs/hero-s323-20261010T122852.jsonl --print-timeline
.venv/bin/streamlit run ui/app.py
```

## Live agent run (uses API quota)

```
.venv/bin/python run.py --scenario hero
```

Recorded runs must be presented as recorded (date and run ID), never as live.
