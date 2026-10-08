# Nidaan — PROGRESS

## Phase sequence (revised, approved)

| Phase | Day | Content | Gate |
|---|---|---|---|
| 0 | 1 | Env, deps, `.env`, model discovery, toy-tool smoke test | Dependent tool calls round-trip; measured calls/tokens/latency |
| 1 | 1 | SettleSim, dev faults only (F1, F2, F4, F6, F7), S1–S4, generator, tool wrappers, sim tests | Sim tests pass; hero solvable by hand via wrappers |
| 2 | 1 | Logger, control tools, plan validation, LangGraph (agent/tools/verifier), verifier V1–V3, CLI | Hero end-to-end from CLI, verified, JSONL written |
| 3 | 2 | Prompt iteration on dev + no-leak test; **prompt freeze** | Hero >= 9/10 AND all 6 dev scenarios run with results recorded. Prompt is NOT tuned specifically to the hero |
| 4 | 2 | Baselines (runbook, one-shot) + evaluation harness, metrics, Wilson CIs; run all three arms on dev scenarios | All arms run on dev; metrics + CIs produced |
| 5 | 2 | Held-out session (explicit user start): add F3, F5, F8 + sealed scenarios/live cards in a separate module. Adds faults/scenarios only | Sim tests for new faults pass; scenarios sealed; prompt hash unchanged |
| 6 | 2 | Held-out evaluation: execute the existing harness on held-out scenarios | Results + CIs recorded |
| 7 | 3 | Streamlit UI, saved replays, rehearsal | Replays render; hero rehearsed |

Day mapping: Day 1 = Phases 0–2. Day 2 = Phases 3–6. Day 3 = Phase 7.
Each phase ends with a report and STOP until the user types "go".

## Status
- Phase 0: IN PROGRESS. Env, pinned deps, .gitignore, .env.example done. Blocked on `.env` with GOOGLE_API_KEY (file absent) for model discovery and the live smoke test.

## Decisions
- Python 3.13.15 venv (`.venv`); 3.14 is also installed but avoided for dependency compatibility.
- Pinned via `pip freeze` into `requirements.txt` (langchain-google-genai 4.4.0, langgraph 1.2.14, langchain-core 1.6.7, pytest 9.1.1, streamlit 1.65.0, python-dotenv 1.2.4).

## Deviations from SPEC.md
None.

## Next step
User creates `.env` with GOOGLE_API_KEY; then run model discovery, select model, run smoke test.
