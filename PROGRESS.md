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
- Phase 0: COMPLETE. Smoke test PASS on gemini-3.8-flash.
- Phase 1: COMPLETE (awaiting user "go"). SettleSim (dev faults F1,F2,F4,F6,F7), S1-S4, generator, 8 tool wrappers; `pytest` 34 passed (incl. hero solved by hand).

- Phase 2: BUILT, GATE NOT MET. Code complete (logger, control tools, plan validation, 3-node graph, verifier V1-V3, CLI, prompt); `pytest` 54 passed. Live hero run has not completed: blocked by the Gemini free-tier daily quota (see Risks). Phase 2 gate is BLOCKED (not complete); awaiting a model/key with available quota. Config stays on gemini-3.8-flash until the user says otherwise; no further hero runs, no extra model probing, no Phase 3.

## Decisions
- Python 3.13.15 venv (`.venv`); 3.14 is also installed but avoided for dependency compatibility.
- Pinned via `pip freeze` into `requirements.txt` (langchain-google-genai 4.4.0, langgraph 1.2.14, langchain-core 1.6.7, pytest 9.1.1, streamlit 1.65.0, python-dotenv 1.2.4).

- Model: `gemini-3.8-flash` (config.py::MODEL_NAME). Newest stable (non-preview) text Flash; function calling and free tier confirmed by real calls. Also passed: 3.7-flash, 3.5-flash. `gemini-2.5-flash` returns 404 (no longer available to new users). Other candidates seen but not chosen: 3.6-flash, 3.5/3.1-flash-lite, preview/image/TTS/omni variants.
- Measured (3.8-flash, 4 LLM calls): ~1.8-2.0k total tokens, 11.6-16.3s total latency across two runs (per-call 2.1-7.1s). Token usage exposed via usage_metadata.
- Note for Phase 2: `response.content` is a list of blocks with thought signatures; use `.text`, and keep full AIMessages in history for multi-turn tool calls.
- Risk: a transient 503 "high demand" occurred once on 3.8-flash; Phase 2 needs retry/backoff (SPEC). Thinking-level setting ("minimal thinking") not yet configured; do in Phase 2.

- Phase 1 design decisions (within SPEC):
  - Package `settlesim/` (sim.py, generator.py, tools.py). `Result.text` is agent-visible; `annotations` (the six SPEC eval-only keys) are kept separate and never in observation text.
  - Dev-only state: bank/ledger fields for held-out-only fault types are not present. `run_task` accepts only the two dev tasks; unknown tasks are rejected generically. Settlement stages live in an ordered list (ledger, auth, rate) so the held-out session can extend it.
  - F7 rule: a client with max_concurrency > rate_limit gets rate_limit + ceil(rate_limit/2) payouts through per run, then 429 with `X-RateLimit-Limit`. (limit 5 -> 8 sent, matching SPEC hero). `inspect(bank)` shows max_concurrency but not rate_limit (limit learned from the 429).
  - S3 uses ledger `conn_used > 0` as "sessions active"; generator gives conn_used 2-8, so ledger restart is always refused in dev scenarios (S2 checked first).
  - Component set: ledger, worker, bank, settlement (4 tiles). `restart(settlement)` is rejected.
  - Wrappers require a non-empty `why` of <= 25 words (SPEC §3); longer `why` is rejected and the call is not executed. (Initially only non-empty was enforced; fixed after review, test `test_why_over_25_words_is_rejected_and_25_is_accepted`.)
  - Hero = seed 323 + (F6,F1,F7): chosen so numbers match the SPEC narrative (queue 37, limit 5, 8 sent). Cosmetic; difficulty unchanged. The 6 dev scenarios are defined in Phase 3.
  - Control tools (`update_plan`, `submit_incident_report`) are Phase 2.

## Deviations from SPEC.md
- **THINKING_LEVEL = "low" instead of "minimal" (SPEC §4 "minimal thinking").** `gemini-3.8-flash` rejects "minimal" with HTTP 400 ("Thinking level MINIMAL is not supported for this model"); "low" is the lowest accepted (0 reasoning tokens on a trivial prompt). Set in `config.py::THINKING_LEVEL`. **Approved by user.**

## Evaluation infrastructure (built; no Gemini calls made, nothing run live)
- `evaluation/` (wilson.py, metrics.py, aggregate.py, harness.py) and `baselines/` (common.py, runbook.py, oneshot.py). All arms write the same JSONL event format; metrics are computed from the logs; results are saved as JSON (`records` + `summary`) for the later UI.
- Runbook: deterministic, no LLM, solves all 31 dev-fault combinations x 3 seeds in tests with 0 duplicates, 0 harmful/refused/rejected actions. One-shot: written, not run (needs Gemini). Nidaan arm: wired via `run_arm`, not run.
- Metrics are split into a `spec` block (only SPEC §9: goal success, duplicate payouts, refused unsafe attempts, actions, unnecessary, harmful, appropriate replanning, batch-status-before-settlement, root-cause component accuracy, LLM calls/tokens/latency; Wilson 95% CIs for proportions) and a `supplementary` block labelled as NOT SPEC metrics (wall-clock, tool steps, action-outcome breakdown, input/output token split, descriptive replan detail). Tokens "unavailable" are excluded from means and counted via `n_available`.
- Operationalisations SPEC §9 does not define (falsifying event, "within 2 steps", unnecessary action, root-cause accuracy) are written out in `evaluation/metrics.py::DEFINITIONS` and included in every results file.
- **Spurious replans: UNDEFINED in SPEC; not reported as a metric.** Only descriptive counts are kept in `supplementary.replan_detail` (replans after a falsifying event / without one / rejected plan updates); a replan after evidence-gathering is never labelled spurious.
- Dev-only ground truth (root-cause components) is isolated in `evaluation/ground_truth.py`; a test asserts nidaan/, settlesim/ and baselines/ never import `evaluation` or reference the truth map. No held-out mapping exists. No scenario set was invented; the harness takes any `Scenario(name, seed, faults)`.
- Prompt wording tightened (replan before further evidence-gathering after an unanticipated failure); not yet validated live.
- `pytest` 104 passed.

## Development scenarios (defined; nothing run)
- `evaluation/scenarios.py::DEV_SCENARIOS` (plain data, no hints): hero (seed 323, F6+F1+F7), dev_f2 (11, F2), dev_f4 (12, F4), dev_f7 (13, F7), dev_f1_f2 (14, F1+F2), dev_f4_f6 (15, F4+F6). Seeds fixed up front, not tuned; the runbook solves all six (local test).
- Protocol constants quoted from SPEC: held-out runs per scenario Nidaan x3 (x2 if quota short), runbook x1, one-shot x3 (SPEC §9); hero rehearsal 10 runs with >= 9 successes (SPEC §7).
- **Open question:** SPEC does not state repeats for the dev scenarios (the 3/1/3 protocol is given for held-out scenarios). Not encoded as a dev setting; awaiting user decision.

## Judge dashboard (built; read-only, no LLM)
- `streamlit run ui/app.py`. `ui/data.py` (non-UI helpers, unit-tested) + `ui/app.py` (tabs: Overview, Run Trace, Scenario, Comparison, Evidence). Reads `runs/*.jsonl` or `results/*.json`; metrics come from `evaluation.metrics.compute_run_metrics` and `evaluation.aggregate.aggregate` (no recalculation).
- SPEC §9 metrics and supplementary measurements are shown in separate tables; Wilson 95% CIs shown; missing data shown as `no runs` / `n/a` / `unavailable`, never estimated. All runs are included by default (API/quota failures are flagged; an explicit sidebar toggle excludes them and the count is shown).
- Only development scenarios are surfaced: runs with an empty or non-development fault set are hidden and counted; there is no held-out view.
- Trace separates agent-visible fields, evaluation-only annotations (dashed box) and run metadata; no free-text reasoning exists in the logs to display.
- `pytest` 127 passed (incl. headless AppTest render).

## Post-block fixes (no live run performed; Phase 2 gate still PENDING)
- **run_task schema:** `task` is now a static enum of the four SPEC §3 tasks (`nidaan/tools.py::RUN_TASKS`: rotate_credential, sync_clock, rotate_logs, kill_idle_connections) so the model cannot guess names such as "help"; invalid values are rejected at schema validation before reaching SettleSim. Tool descriptions stay general (no fault names, mappings or hints). Per the user's instruction the enum lists all four, so the tool schema is identical before and after the held-out session. SettleSim is unchanged and still rejects the two non-dev tasks as unknown in dev scenarios.
- **Rate-limit handling:** `nidaan/graph.py::retry_delay_s` respects a server-provided retry delay (`retryDelay` / "retry in Ns", +1s margin); falls back to 2/4/8/16s backoff when none is given; gives up if the delay exceeds `config.LLM_MAX_RETRY_DELAY_S` (120s) or the quota is per-day. Unit-tested without any API call.
- Tests: `pytest` 59 passed. Prompt, graph structure, SettleSim, verifier, SPEC.md unchanged.

## Risks / blockers
- **Hero attempt 2 (2026-10-08, 3.8-flash, low): FAILED, quota.** 13 successful LLM calls, 31,731 tokens, 70.5s LLM latency, 186s wall-clock; 17 error events (503 UNAVAILABLE + 429). Final 429 = `GenerateRequestsPerMinutePerProjectPerModel-FreeTier`, limit 5/min, server retryDelay 53s; our backoff (2/4/8/16s) is shorter than that. Run ended after PLAN v1, 9 OBSERVE, 3 ACT (all rejected `run_task` probes of task name 'help'); no replan, no verifier, 0/20 sent. Free tier is therefore 5 req/min AND 20 req/day for this model; a hero run needs ~15-20 calls. Gate still NOT met.
- **Free-tier daily quota:** `gemini-3.8-flash` = 20 requests/day/project (quotaId GenerateRequestsPerDayPerProject PerModel-FreeTier, limit 20); exhausted on 2026-10-08, resets ~19.5h later. A hero run needs roughly 15-20 LLM calls; SPEC §9 evaluation needs hundreds. Other Flash models have separate per-model quotas, limits unknown. Needs a user decision (billing/another key, different model, or wait).
- A request with no timeout hung ~9.5 min once; fixed with `LLM_TIMEOUT_S=60` (retryable).
- Per-day quota errors now fail fast (`is_transient`); small error-handling fix, not architectural.

## Next step
Wait for the user to supply an available model/key or instruct a model switch; then re-run the hero from the CLI to meet the Phase 2 gate. No other phase until then.
