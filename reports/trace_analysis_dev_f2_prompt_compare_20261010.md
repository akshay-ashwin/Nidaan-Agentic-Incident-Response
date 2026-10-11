# Nidaan execution-trace analysis

Generated offline from run logs; no LLM or API calls. Evidence classes: **measured** (read from logged events), **derived** (computed by a rule in Definitions), **unavailable / n/a** (not recorded or not applicable; never estimated). No qualitative judgement is generated and no hidden reasoning is inferred. Reasons shown are logged text only: for Nidaan the LLM's `why` argument; for the runbook and one-shot baselines fixed scripted strings, **not** LLM-generated reasoning. Fields marked *evaluation-only* come from the annotation channel the agent never saw; they are used here only after the run.

**Inputs** (2 runs): `runs/nidaan-dev_f2-s11-r1-20261010T130437328361.jsonl`, `runs/nidaan-dev_f2-s11-r1-20261010T135920634391.jsonl`

## Comparison (one row per run)

| scenario | arm | final_outcome | goal_met | duplicates | payouts | actions | ok | refused | rejected | unnecessary | batch_checked | replan_in_time | llm_calls | tokens | llm_latency_s | wall_clock_s | run_id |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| dev_f2 | nidaan | FAILED | False | 0 | 0/20 | 13 | 6 | 0 | 7 | 5 | 1/3 | 3/5 | 30 | 77715 | 25.71 | 318.65 | nidaan-dev_f2-s11-r1-20261010T130437328361 |
| dev_f2 | nidaan | VERIFIED | True | 0 | 20/20 | 10 | 6 | 0 | 4 | 4 | 0/4 | 0/4 | 23 | 56709 | 19.14 | 564.62 | nidaan-dev_f2-s11-r1-20261010T135920634391 |


Columns: `goal_met`, `duplicates` = evaluation-only state at FINAL; `payouts` = last count shown in the log; `ok/refused/rejected` = ACT outcomes; `unnecessary`, `batch_checked` (runs with a batch-status check / settlement runs), `replan_in_time` (falsifying events followed by a plan within 2 steps / falsifying events) = SPEC §9 metrics from evaluation/metrics.py, unchanged; `tokens`, `llm_latency_s` = FINAL.metrics; `n/a` = not applicable to the arm; `—` = not recorded.

## nidaan · dev_f2 · `nidaan-dev_f2-s11-r1-20261010T130437328361`

- Source: `runs/nidaan-dev_f2-s11-r1-20261010T130437328361.jsonl` (56 events; complete)
- Arm: nidaan — source: GOAL.eval.arm; model: `groq:openai/gpt-oss-120b`; faults: F2
- Reasons in the timeline: agent-supplied: the `why` argument the LLM attached to each tool call (stated text, not verified)

**Measured**

- Final: **FAILED** — step limit (30 LLM steps) reached
- Goal met: False; duplicate payouts: 0; faults active at end: none *(evaluation-only state, read after the run)*
- Payouts last shown in the log: 0/20
- Actions: 13 (6 ok, 0 refused, 7 rejected)
- Verifier: not invoked (no report submitted)
- LLM: 30 successful calls, 24 failed attempts; tokens 74043 in + 3672 out = 77715; LLM latency 25.71 s
- Errors: 24 rate-limit retries, 0 other failed LLM attempts, 1 nudge; wall-clock 318.65 s

**Derived**

- Action validity: 0.46
- Component inspected before acting on it: 10/10 (weak evidence: says nothing about whether the target was right)
- Failure responses: 12 failure events (5 falsifying per SPEC §9 + 7 rejections or other); accepted plan within 2 steps after 4 of them. SPEC §9 appropriate replanning (falsifying events only): 3/5
- Repeated rejected actions: none
- All faults cleared *(evaluation-only)*: at #39 by `restart(component=bank)`; afterwards settlement: none; check_pipeline: none (6 steps after)
- Time outside successful LLM calls: 292.94 s; tokens per LLM call: 2590.5

**Report diagnostics** *(descriptive; not SPEC §9 metrics; verifier pass/fail unchanged; no-effect annotations are evaluation-only, read after the run)*

- n/a — no incident report was submitted

`set_config` grounding (key / value seen in an earlier observation; `—` = value too short to be evidence):

| seq | component | key | value | outcome | key_seen_before | value_seen_before |
|---|---|---|---|---|---|---|
| 29 | settlement | bank_credential_id | cred-a101 | rejected | False | True |
| 31 | settlement | credential_id | cred-a101 | rejected | False | True |
| 55 | bank | credential.id | cred-a101 | rejected | True | True |


Replan triggers (events cited by each accepted plan update):

- plan v2 (#4): #3 OBSERVE `check_pipeline()` [ok]
- plan v3 (#8): #7 ACT `run_settlement(mode=resume)` [ok]
- plan v4 (#23): #19 ACT `run_settlement(mode=resume)` [ok], #21 OBSERVE `inspect(component=settlement)` [ok]
- plan v5 (#50): #48 ACT `run_task(component=settlement, task=rotate_logs)` [rejected]

**Unavailable / not applicable**

- verifier: no report was submitted, so the verifier never ran

Timeline (`errors before` = folded ERROR events; `eval flags` = evaluation-only):

| seq | errors before | stage | event | stated why (LLM) | environment response | eval flags |
|---|---|---|---|---|---|---|
| 1 | — | goal | model groq:openai/gpt-oss-120b | — | — | — |
| 2 | — | plan | plan v1 | — | +7/-0 steps; reason: Initial investigation plan | — |
| 3 | — | observe | check_pipeline() | Determine if pipeline is healthy and batch progress | Components: / ledger: up / worker: running (queue depth: 0) / bank: up / settlement: idle / Payouts sent: 0/2… | — |
| 4 | — | replan | plan v2 <- triggered by [3] | — | +6/-7 steps; reason: Plan next steps based on pipeline idle and no payouts | — |
| 5 | — | observe | get_batch_status() | Identify pending payouts and checkpoint | Batch: 0 sent, 20 pending / Checkpoint: next payout to send is payout #1 (PO-1001) / Payouts sent more than o… | — |
| 6 | — | observe | read_logs(component=settlement, n=20) | Check for errors causing stall | [t=0000] INFO batch of 20 payouts loaded | — |
| 7 | — | act [ok] | run_settlement(mode=resume) | Start settlement batch from checkpoint | run_settlement(resume): sent 0 payouts this run. Stopped at payout #1 (PO-1001): 401 Unauthorized. Total sent… | new_failure_exposed, no_effect |
| 8 | — | replan | plan v3 <- triggered by [7] | — | +6/-6 steps; reason: Investigate unauthorized error before retrying | — |
| 9 | — | observe | inspect(component=settlement) | Check settlement config for credentials | settlement: / checkpoint: 0 / payouts_sent: 0 / last_run: last run stopped (401) | — |
| 11 | rate_limit_retries=1 | observe | inspect(component=bank) | Check bank config for auth credentials | bank: / server_time: 2026-09-21T14:13:20Z / credential.id: cred-e79e / credential.expires_at: 2026-10-19T14:1… | — |
| 13 | rate_limit_retries=1 | act [rejected] | run_task(component=settlement, task=rotate_credential) | Refresh settlement's bank credential to fix 401 | rejected: task 'rotate_credential' is not available on settlement | — |
| 15 | rate_limit_retries=1 | act [ok] | run_task(component=bank, task=rotate_credential) | Refresh bank credential used by settlement | rotate_credential: issued cred-a101, expires 2026-10-21T14:13:20Z | no_effect |
| 17 | rate_limit_retries=1 | act [rejected] | restart(component=settlement) | Restart settlement to load new bank credential | rejected: settlement is a batch job, not a restartable service; use run_settlement | — |
| 19 | rate_limit_retries=1 | act [ok] | run_settlement(mode=resume) | Retry settlement after rotating bank credential | run_settlement(resume): sent 0 payouts this run. Stopped at payout #1 (PO-1001): 401 Unauthorized. Total sent… | no_effect |
| 21 | rate_limit_retries=1 | observe | inspect(component=settlement) | Check settlement config for bank credential reference | settlement: / checkpoint: 0 / payouts_sent: 0 / last_run: last run stopped (401) | — |
| 23 | rate_limit_retries=1 | replan | plan v4 <- triggered by [19, 21] | — | +3/-6 steps; reason: Apply new bank credential to settlement and retry | — |
| 25 | rate_limit_retries=1 | observe | read_logs(component=settlement, n=30) | Look for config usage errors | [t=0000] INFO batch of 20 payouts loaded / [t=0001] ERROR payout PO-1001 stopped: 401 Unauthorized / [t=0005]… | — |
| 27 | rate_limit_retries=1 | observe | inspect(component=settlement) | List all config keys | settlement: / checkpoint: 0 / payouts_sent: 0 / last_run: last run stopped (401) | — |
| 29 | rate_limit_retries=1 | act [rejected] | set_config(component=settlement, key=bank_credential_id, value=cred-a101) | Configure settlement to use new bank credential | rejected: 'bank_credential_id' is not a settable key on settlement; settable: none | — |
| 31 | rate_limit_retries=1 | act [rejected] | set_config(component=settlement, key=credential_id, value=cred-a101) | Set settlement's credential to new bank credential | rejected: 'credential_id' is not a settable key on settlement; settable: none | — |
| 33 | rate_limit_retries=1 | observe | read_logs(component=bank, n=30) | Find auth failures for settlement | [t=0000] INFO gateway connected / [t=0001] ERROR 401 Unauthorized (payout PO-1001) / [t=0003] INFO credential… | — |
| 35 | rate_limit_retries=1 | act [ok] | run_settlement(mode=full) | Run full batch to load fresh credential after rotation | run_settlement(full): sent 0 payouts this run. Stopped at payout #1 (PO-1001): 401 Unauthorized. Total sent: … | no_effect |
| 37 | rate_limit_retries=1 | act [rejected] | run_task(component=settlement, task=sync_clock) | Ensure settlement clock matches bank for auth | rejected: unknown task 'sync_clock'; tasks: rotate_credential, rotate_logs | — |
| 39 | rate_limit_retries=1 | act [ok] | restart(component=bank) | Restart bank to apply new credential | bank restarted: signing key reloaded from vault | — |
| 44 | rate_limit_retries=3, nudges=1 | observe | read_logs(component=bank, n=30) | Inspect detailed auth failure logs | [t=0000] INFO gateway connected / [t=0001] ERROR 401 Unauthorized (payout PO-1001) / [t=0003] INFO credential… | — |
| 46 | rate_limit_retries=1 | act [ok] | restart(component=bank) | Restart bank again to ensure credential propagation | bank restarted: signing key reloaded from vault | no_effect |
| 48 | rate_limit_retries=1 | act [rejected] | run_task(component=settlement, task=rotate_logs) | Refresh settlement internal state possibly clearing credential cache | rejected: task 'rotate_logs' is not available on settlement | — |
| 50 | rate_limit_retries=1 | replan | plan v5 <- triggered by [48] | — | +3/-3 steps; reason: Attempt to set settlement API key to new credential and retry batch | — |
| 53 | rate_limit_retries=2 | observe | read_logs(component=settlement, n=50) | Search for config key name in logs | [t=0000] INFO batch of 20 payouts loaded / [t=0001] ERROR payout PO-1001 stopped: 401 Unauthorized / [t=0005]… | — |
| 55 | rate_limit_retries=1 | act [rejected] | set_config(component=bank, key=credential.id, value=cred-a101) | Ensure bank reports new credential id | rejected: 'credential.id' is not a settable key on bank; settable: key_in_use, max_concurrency | — |
| 56 | — | final | FAILED | — | step limit (30 LLM steps) reached | — |


## nidaan · dev_f2 · `nidaan-dev_f2-s11-r1-20261010T135920634391`

- Source: `runs/nidaan-dev_f2-s11-r1-20261010T135920634391.jsonl` (44 events; complete)
- Arm: nidaan — source: GOAL.eval.arm; model: `groq:openai/gpt-oss-120b`; faults: F2
- Reasons in the timeline: agent-supplied: the `why` argument the LLM attached to each tool call (stated text, not verified)

**Measured**

- Final: **VERIFIED** — goal verified
- Goal met: True; duplicate payouts: 0; faults active at end: none *(evaluation-only state, read after the run)*
- Payouts last shown in the log: 20/20
- Actions: 10 (6 ok, 0 refused, 4 rejected)
- Verifier: 1 submitted, 1 passed; last: V1✓ V2✓ V3✓
- LLM: 23 successful calls, 19 failed attempts; tokens 54110 in + 2599 out = 56709; LLM latency 19.14 s
- Errors: 19 rate-limit retries, 0 other failed LLM attempts, 1 nudge; wall-clock 564.62 s

**Derived**

- Action validity: 0.60
- Component inspected before acting on it: 6/6 (weak evidence: says nothing about whether the target was right)
- Failure responses: 8 failure events (4 falsifying per SPEC §9 + 4 rejections or other); accepted plan within 2 steps after 1 of them. SPEC §9 appropriate replanning (falsifying events only): 0/4
- Repeated rejected actions: none
- All faults cleared *(evaluation-only)*: at #36 by `set_config(component=bank, key=key_in_use, value=key-326ml6)`; afterwards settlement: #38; check_pipeline: #39 (3 steps after)
- Time outside successful LLM calls: 545.48 s; tokens per LLM call: 2465.6

**Report diagnostics** *(descriptive; not SPEC §9 metrics; verifier pass/fail unchanged; no-effect annotations are evaluation-only, read after the run)*

- Report: VERIFY #43 (verifier: pass; 1 submitted; the last is analysed)
- Action coverage: 3/6 executed actions listed; omitted: #5, #16, #34; listed but not executed: none; invalid references: none; duplicates: none
- Root cause 1 (bank), cites #5, #7, #10: **flag** — cites action(s) recorded as no effect: #5, #10 *(review; not a verdict)*
- Root cause 2 (bank), cites #34, #32, #36: **flag** — cites action(s) recorded as no effect: #34 *(review; not a verdict)*

`set_config` grounding (key / value seen in an earlier observation; `—` = value too short to be evidence):

| seq | component | key | value | outcome | key_seen_before | value_seen_before |
|---|---|---|---|---|---|---|
| 22 | settlement | credential.id | cred-a101 | rejected | True | True |
| 26 | bank | credential.id | cred-a101 | rejected | True | True |
| 30 | bank | key_in_use | cred-a101 | rejected | True | True |
| 36 | bank | key_in_use | key-326ml6 | ok | True | True |


Replan triggers (events cited by each accepted plan update):

- plan v2 (#28): #26 ACT `set_config(component=bank, key=credential.id, value=cred-a101)` [rejected]

Timeline (`errors before` = folded ERROR events; `eval flags` = evaluation-only):

| seq | errors before | stage | event | stated why (LLM) | environment response | eval flags |
|---|---|---|---|---|---|---|
| 1 | — | goal | model groq:openai/gpt-oss-120b | — | — | — |
| 2 | — | plan | plan v1 | — | +7/-0 steps; reason: Initial investigation of stalled payout settlement batch | — |
| 3 | — | observe | check_pipeline() | Determine if batch completed and component health | Components: / ledger: up / worker: running (queue depth: 0) / bank: up / settlement: idle / Payouts sent: 0/2… | — |
| 4 | — | observe | read_logs(component=settlement, n=30) | Look for errors causing batch not to start | [t=0000] INFO batch of 20 payouts loaded | — |
| 5 | — | act [ok] | run_settlement(mode=full) | Start settlement batch to process payouts | run_settlement(full): sent 0 payouts this run. Stopped at payout #1 (PO-1001): 401 Unauthorized. Total sent: … | new_failure_exposed, no_effect |
| 7 | rate_limit_retries=1 | observe | inspect(component=bank) | Check bank credentials config | bank: / server_time: 2026-09-21T14:13:20Z / credential.id: cred-e79e / credential.expires_at: 2026-10-19T14:1… | — |
| 10 | rate_limit_retries=2 | act [ok] | run_task(component=bank, task=rotate_credential) | Refresh bank API credential causing 401 | rotate_credential: issued cred-a101, expires 2026-10-21T14:13:20Z | no_effect |
| 12 | rate_limit_retries=1 | observe | inspect(component=settlement) | Check settlement config for auth | settlement: / checkpoint: 0 / payouts_sent: 0 / last_run: last run stopped (401) | — |
| 14 | rate_limit_retries=1 | act [rejected] | restart(component=settlement) | Reload config after bank credential rotation | rejected: settlement is a batch job, not a restartable service; use run_settlement | — |
| 16 | rate_limit_retries=1 | act [ok] | run_settlement(mode=resume) | Continue batch after credential refreshed | run_settlement(resume): sent 0 payouts this run. Stopped at payout #1 (PO-1001): 401 Unauthorized. Total sent… | no_effect |
| 18 | rate_limit_retries=1 | observe | inspect(component=settlement) | List settlement config keys | settlement: / checkpoint: 0 / payouts_sent: 0 / last_run: last run stopped (401) | — |
| 20 | rate_limit_retries=1 | observe | read_logs(component=settlement, n=30) | Find auth error details | [t=0000] INFO batch of 20 payouts loaded / [t=0001] ERROR payout PO-1001 stopped: 401 Unauthorized / [t=0004]… | — |
| 22 | rate_limit_retries=1 | act [rejected] | set_config(component=settlement, key=credential.id, value=cred-a101) | Set settlement to use new bank credential | rejected: 'credential.id' is not a settable key on settlement; settable: none | — |
| 24 | rate_limit_retries=1 | observe | read_logs(component=worker, n=30) | Check worker logs for auth errors | [t=0000] INFO worker started | — |
| 26 | rate_limit_retries=1 | act [rejected] | set_config(component=bank, key=credential.id, value=cred-a101) | Update bank credential id to new value | rejected: 'credential.id' is not a settable key on bank; settable: key_in_use, max_concurrency | — |
| 28 | rate_limit_retries=1 | replan | plan v2 <- triggered by [26] | — | +3/-7 steps; reason: Adjust bank config to use new credential | — |
| 30 | rate_limit_retries=1 | act [rejected] | set_config(component=bank, key=key_in_use, value=cred-a101) | Configure bank to use refreshed credential | rejected: key_in_use must look like 'key-xxxxxx' (6 lowercase alphanumerics) | — |
| 32 | rate_limit_retries=1 | observe | inspect(component=bank) | Get list of settable keys | bank: / server_time: 2026-09-21T14:13:20Z / credential.id: cred-a101 / credential.expires_at: 2026-10-21T14:1… | — |
| 34 | rate_limit_retries=1 | act [ok] | run_settlement(mode=full) | Retry full batch after bank credential rotation | run_settlement(full): sent 0 payouts this run. Stopped at payout #1 (PO-1001): 401 Unauthorized. Total sent: … | no_effect |
| 36 | rate_limit_retries=1 | act [ok] | set_config(component=bank, key=key_in_use, value=key-326ml6) | Set bank to use active vault key | applied: bank.key_in_use = key-326ml6 | — |
| 38 | rate_limit_retries=1 | act [ok] | run_settlement(mode=full) | Run batch after fixing bank key | run_settlement(full): sent 20 payouts this run (#1-#20). Run complete. Total sent: 20/20. | — |
| 39 | — | observe | check_pipeline() | Confirm all payouts settled and components healthy | Components: / ledger: up / worker: running (queue depth: 0) / bank: up / settlement: last run complete / Payo… | — |
| 43 | rate_limit_retries=2, nudges=1 | verify [pass] | submit_incident_report | — | V1✓ V2✓ V3✓ | — |
| 44 | — | final | VERIFIED | — | goal verified | — |


## Definitions

- **final_outcome**: FINAL.outcome (VERIFIED/FAILED for nidaan; GOAL_MET/GOAL_NOT_MET for baselines). JSON null if no FINAL; shown as 'none (no FINAL event)'.
- **stop_reason**: FINAL.result text.
- **verifier**: VERIFY events: number submitted, number passed, checks of the last one. Nidaan only.
- **goal_met / duplicates / faults_active_at_end**: FINAL.eval (evaluation-only channel), set by SettleSim.
- **payouts_sent_last_observed**: Last 'Total sent: x/y' or 'Payouts sent: x/y' in an agent-visible tool result. What the log showed, not a separate ground truth.
- **actions_by_outcome**: ACT events counted by outcome: ok (applied), refused (safety guard), rejected (schema/target/key invalid; not executed).
- **tool_calls**: OBSERVE/ACT events counted by tool name.
- **llm**: FINAL.metrics as logged by the run (calls, failed attempts, tokens, LLM latency).
- **rate_limit_retries**: ERROR events of failed LLM attempts rejected by the provider rate limit (text contains 'RateLimit' or 'RESOURCE_EXHAUSTED').
- **other_llm_errors**: ERROR events of other failed LLM attempts (e.g. 503, timeout).
- **nudges**: ERROR events 'agent replied without a tool call'.
- **wall_clock_s**: Last event ts minus first event ts.
- **action_validity_rate**: (ok + refused) / ACT events: share of actions whose tool, target and parameters were accepted (a refusal is a valid request blocked by a safety guard).
- **failure_responses**: For each ACT that was rejected or annotated new_failure_exposed / no_effect / harmful / refusal: the next step (OBSERVE/ACT/PLAN/VERIFY; ERROR is not a step) and whether an accepted PLAN followed within 2 steps (same window as SPEC §9 metric).
- **repeated_rejected_actions**: ACT whose tool and args (excluding `why`) equal an earlier rejected ACT.
- **set_config_grounding**: For each set_config: key_seen_before = '<key>:' occurs in an earlier OBSERVE result; value_seen_before = the value occurs as a whole word in an earlier tool result. Values of <= 2 characters are 'insufficient': JSON null, shown as '—'.
- **inspected_before_act**: Share of component-targeted ACT events (restart/set_config/run_task) preceded at any earlier point by inspect or read_logs of the same component.
- **replan_citations**: For each accepted PLAN v2+: the cited events' type, tool and outcome.
- **after_all_faults_cleared**: Evaluation-only: first ACT after which SettleSim reports no active fault; whether a run_settlement ACT and a check_pipeline OBSERVE follow it.
- **non_llm_wall_clock_s**: wall_clock_s - LLM latency: time spent outside successful LLM calls (rate-limit waits, failed attempts, tool execution).
- **tokens_per_llm_call**: total_tokens / llm_calls.
- **report_action_coverage**: Last submitted report's `actions` vs ACT events executed (outcome ok) before it: claimed executed, omitted executed, claimed but not executed (rejected/refused), invalid references (not an ACT event before the report, or not an integer), duplicates.
- **report_root_cause_evidence**: Per reported root cause: cited ACT events whose evaluation-only annotation is no_effect. A flag marks the citation for review; it is not a verdict, because a no-effect action can be valid evidence (e.g. a retry that still fails). 'uncertain' = no evidence cited, cited ACT without the annotation, or a citation that is not an OBSERVE/ACT event before the report.
