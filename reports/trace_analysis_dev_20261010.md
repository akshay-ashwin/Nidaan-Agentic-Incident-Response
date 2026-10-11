# Nidaan execution-trace analysis

Generated offline from run logs; no LLM or API calls. Evidence classes: **measured** (read from logged events), **derived** (computed by a rule in Definitions), **unavailable / n/a** (not recorded or not applicable; never estimated). No qualitative judgement is generated and no hidden reasoning is inferred. Reasons shown are logged text only: for Nidaan the LLM's `why` argument; for the runbook and one-shot baselines fixed scripted strings, **not** LLM-generated reasoning. Fields marked *evaluation-only* come from the annotation channel the agent never saw; they are used here only after the run.

**Inputs** (14 runs): `results/dev_runbook.json`, `results/dev_oneshot_hero_r1.json`, `results/dev_oneshot_remaining_r1.json`, `results/dev_nidaan_dev_f2_r1.json`, `runs/hero-s323-20261010T122852.jsonl`

## Comparison (one row per run)

| scenario | arm | final_outcome | goal_met | duplicates | payouts | actions | ok | refused | rejected | unnecessary | batch_checked | replan_in_time | llm_calls | tokens | llm_latency_s | wall_clock_s | run_id |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| dev_f1_f2 | oneshot | GOAL_NOT_MET | False | 0 | 0/20 | 2 | 2 | 0 | 0 | 1 | 0/1 | n/a | 1 | 739 | 0.77 | 0.79 | oneshot-dev_f1_f2-s14-r1-20261010T125929699326 |
| dev_f1_f2 | runbook | GOAL_MET | True | 0 | 20/20 | 4 | 4 | 0 | 0 | 1 | 2/2 | n/a | 0 | n/a | n/a | 0.0 | runbook-dev_f1_f2-s14-r1-20261010T123930386388 |
| dev_f2 | nidaan | FAILED | False | 0 | 0/20 | 13 | 6 | 0 | 7 | 5 | 1/3 | 3/5 | 30 | 77715 | 25.71 | 318.65 | nidaan-dev_f2-s11-r1-20261010T130437328361 |
| dev_f2 | oneshot | GOAL_NOT_MET | False | 0 | 0/20 | 1 | 1 | 0 | 0 | 1 | 0/1 | n/a | 1 | 665 | 0.69 | 0.77 | oneshot-dev_f2-s11-r1-20261010T125927665564 |
| dev_f2 | runbook | GOAL_MET | True | 0 | 20/20 | 3 | 3 | 0 | 0 | 1 | 2/2 | n/a | 0 | n/a | n/a | 0.0 | runbook-dev_f2-s11-r1-20261010T123930382597 |
| dev_f4 | oneshot | GOAL_MET | True | 0 | 20/20 | 4 | 3 | 1 | 0 | 1 | 0/1 | n/a | 1 | 776 | 0.8 | 0.81 | oneshot-dev_f4-s12-r1-20261010T125928438467 |
| dev_f4 | runbook | GOAL_MET | True | 0 | 20/20 | 2 | 2 | 0 | 0 | 0 | 1/1 | n/a | 0 | n/a | n/a | 0.0 | runbook-dev_f4-s12-r1-20261010T123930383764 |
| dev_f4_f6 | oneshot | GOAL_NOT_MET | False | 0 | 0/20 | 2 | 1 | 1 | 0 | 0 | 0/1 | n/a | 1 | 723 | 0.64 | 0.65 | oneshot-dev_f4_f6-s15-r1-20261010T125930487358 |
| dev_f4_f6 | runbook | GOAL_MET | True | 0 | 20/20 | 3 | 3 | 0 | 0 | 0 | 1/1 | n/a | 0 | n/a | n/a | 0.0 | runbook-dev_f4_f6-s15-r1-20261010T123930387877 |
| dev_f7 | oneshot | GOAL_NOT_MET | False | 0 | 6/20 | 1 | 1 | 0 | 0 | 0 | 0/1 | n/a | 1 | 657 | 0.42 | 0.44 | oneshot-dev_f7-s13-r1-20261010T125929258626 |
| dev_f7 | runbook | GOAL_MET | True | 0 | 20/20 | 3 | 3 | 0 | 0 | 0 | 2/2 | n/a | 0 | n/a | n/a | 0.0 | runbook-dev_f7-s13-r1-20261010T123930385074 |
| hero | nidaan | VERIFIED | True | 0 | 20/20 | 9 | 6 | 0 | 3 | 1 | 0/3 | 0/2 | 23 | 52492 | 18.04 | 244.12 | hero-s323-20261010T122852 |
| hero | oneshot | GOAL_NOT_MET | False | 0 | 8/20 | 3 | 3 | 0 | 0 | 0 | 0/1 | n/a | 1 | 775 | 0.95 | 1.02 | oneshot-hero-s323-r1-20261010T125814820721 |
| hero | runbook | GOAL_MET | True | 0 | 20/20 | 6 | 6 | 0 | 0 | 1 | 3/3 | n/a | 0 | n/a | n/a | 0.0 | runbook-hero-s323-r1-20261010T123930379786 |


Columns: `goal_met`, `duplicates` = evaluation-only state at FINAL; `payouts` = last count shown in the log; `ok/refused/rejected` = ACT outcomes; `unnecessary`, `batch_checked` (runs with a batch-status check / settlement runs), `replan_in_time` (falsifying events followed by a plan within 2 steps / falsifying events) = SPEC §9 metrics from evaluation/metrics.py, unchanged; `tokens`, `llm_latency_s` = FINAL.metrics; `n/a` = not applicable to the arm; `—` = not recorded.

## oneshot · dev_f1_f2 · `oneshot-dev_f1_f2-s14-r1-20261010T125929699326`

- Source: `runs/oneshot-dev_f1_f2-s14-r1-20261010T125929699326.jsonl` (13 events; complete)
- Arm: oneshot — source: GOAL.eval.arm; model: `groq:openai/gpt-oss-120b`; faults: F1, F2
- Reasons in the timeline: scripted: fixed strings in baselines/oneshot.py; the LLM produced only the action list

**Measured**

- Final: **GOAL_NOT_MET** — executed 2 listed actions blindly (0 malformed)
- Goal met: False; duplicate payouts: 0; faults active at end: F2 *(evaluation-only state, read after the run)*
- Payouts last shown in the log: 0/20
- Actions: 2 (2 ok, 0 refused, 0 rejected)
- Verifier: n/a (arm does not submit a report)
- LLM: 1 successful calls, 0 failed attempts; tokens 614 in + 125 out = 739; LLM latency 0.77 s
- Errors: 0 rate-limit retries, 0 other failed LLM attempts, 0 nudges; wall-clock 0.79 s

**Derived**

- Action validity: 1.00
- Component inspected before acting on it: 1/1 (weak evidence: says nothing about whether the target was right)
- Failure responses: 1 failure events; replanning n/a (arm does not plan)
- Repeated rejected actions: none
- All faults cleared *(evaluation-only)*: never — still active at end: F2
- Time outside successful LLM calls: 0.02 s; tokens per LLM call: 739.0

**Report diagnostics** *(descriptive; not SPEC §9 metrics; verifier pass/fail unchanged; no-effect annotations are evaluation-only, read after the run)*

- n/a — oneshot arm does not submit an incident report

**Unavailable / not applicable**

- plans_and_replanning: oneshot arm does not plan
- verifier: oneshot arm does not submit an incident report

Timeline (`errors before` = folded ERROR events; `eval flags` = evaluation-only):

| seq | errors before | stage | event | scripted reason | environment response | eval flags |
|---|---|---|---|---|---|---|
| 1 | — | goal | model groq:openai/gpt-oss-120b | — | — | — |
| 2 | — | observe | check_pipeline() | t0 snapshot: overall status. | Components: / ledger: up / worker: running (queue depth: 0) / bank: up / settlement: idle / Payouts sent: 0/2… | — |
| 3 | — | observe | inspect(component=ledger) | t0 snapshot: inspect ledger. | ledger: / up: true / disk_pct: 57 / conn_used: 4 / conn_max: 20 / records: 0 | — |
| 4 | — | observe | inspect(component=worker) | t0 snapshot: inspect worker. | worker: / running: true / queue_depth: 0 | — |
| 5 | — | observe | inspect(component=bank) | t0 snapshot: inspect bank. | bank: / server_time: 2026-09-21T14:13:20Z / credential.id: cred-36b2 / credential.expires_at: 2026-09-17T06:5… | — |
| 6 | — | observe | inspect(component=settlement) | t0 snapshot: inspect settlement. | settlement: / checkpoint: 0 / payouts_sent: 0 / last_run: none | — |
| 7 | — | observe | read_logs(component=ledger, n=30) | t0 snapshot: logs of ledger. | [t=0000] INFO ledger started | — |
| 8 | — | observe | read_logs(component=worker, n=30) | t0 snapshot: logs of worker. | [t=0000] INFO worker started | — |
| 9 | — | observe | read_logs(component=bank, n=30) | t0 snapshot: logs of bank. | [t=0000] INFO gateway connected | — |
| 10 | — | observe | read_logs(component=settlement, n=30) | t0 snapshot: logs of settlement. | [t=0000] INFO batch of 20 payouts loaded | — |
| 11 | — | act [ok] | run_task(component=bank, task=rotate_credential) | One-shot action 1 of 2. | rotate_credential: issued cred-f489, expires 2026-10-21T14:13:20Z | — |
| 12 | — | act [ok] | run_settlement(mode=full) | One-shot action 2 of 2. | run_settlement(full): sent 0 payouts this run. Stopped at payout #1 (PO-1001): 401 Unauthorized. Total sent: … | new_failure_exposed, no_effect |
| 13 | — | final | GOAL_NOT_MET | — | executed 2 listed actions blindly (0 malformed) | — |


## runbook · dev_f1_f2 · `runbook-dev_f1_f2-s14-r1-20261010T123930386388`

- Source: `runs/runbook-dev_f1_f2-s14-r1-20261010T123930386388.jsonl` (13 events; complete)
- Arm: runbook — source: GOAL.eval.arm; model: `none`; faults: F1, F2
- Reasons in the timeline: scripted: fixed strings in baselines/runbook.py (no LLM)

**Measured**

- Final: **GOAL_MET** — goal confirmed by check_pipeline
- Goal met: True; duplicate payouts: 0; faults active at end: none *(evaluation-only state, read after the run)*
- Payouts last shown in the log: 20/20
- Actions: 4 (4 ok, 0 refused, 0 rejected)
- Verifier: n/a (arm does not submit a report)
- LLM: none (runbook makes no LLM calls)
- Errors: 0 rate-limit retries, 0 other failed LLM attempts, 0 nudges; wall-clock 0.0 s

**Derived**

- Action validity: 1.00
- Component inspected before acting on it: 2/2 (weak evidence: says nothing about whether the target was right)
- Failure responses: 1 failure events; replanning n/a (arm does not plan)
- Repeated rejected actions: none
- All faults cleared *(evaluation-only)*: at #8 by `set_config(component=bank, key=key_in_use, value=key-7prqse)`; afterwards settlement: #11; check_pipeline: #9, #12 (4 steps after)
- Time outside successful LLM calls: n/a; tokens per LLM call: n/a

**Report diagnostics** *(descriptive; not SPEC §9 metrics; verifier pass/fail unchanged; no-effect annotations are evaluation-only, read after the run)*

- n/a — runbook arm does not submit an incident report

`set_config` grounding (key / value seen in an earlier observation; `—` = value too short to be evidence):

| seq | component | key | value | outcome | key_seen_before | value_seen_before |
|---|---|---|---|---|---|---|
| 8 | bank | key_in_use | key-7prqse | ok | True | True |


**Unavailable / not applicable**

- plans_and_replanning: runbook arm does not plan
- verifier: runbook arm does not submit an incident report
- llm_tokens_latency: not applicable: runbook makes no LLM calls (0 calls logged)

Timeline (`errors before` = folded ERROR events; `eval flags` = evaluation-only):

| seq | errors before | stage | event | scripted reason | environment response | eval flags |
|---|---|---|---|---|---|---|
| 1 | — | goal | model none | — | — | — |
| 2 | — | observe | check_pipeline() | Find the first failing stage. | Components: / ledger: up / worker: running (queue depth: 0) / bank: up / settlement: idle / Payouts sent: 0/2… | — |
| 3 | — | observe | get_batch_status() | Check progress and checkpoint before settling. | Batch: 0 sent, 20 pending / Checkpoint: next payout to send is payout #1 (PO-1001) / Payouts sent more than o… | — |
| 4 | — | act [ok] | run_settlement(mode=full) | Settle remaining payouts. | run_settlement(full): sent 0 payouts this run. Stopped at payout #1 (PO-1001): 401 Unauthorized. Total sent: … | new_failure_exposed, no_effect |
| 5 | — | observe | read_logs(component=bank, n=10) | Settlement stopped on authentication; read bank logs. | [t=0000] INFO gateway connected / [t=0001] ERROR 401 Unauthorized (payout PO-1001) | — |
| 6 | — | observe | inspect(component=bank) | Disambiguate authentication failure causes from bank config. | bank: / server_time: 2026-09-21T14:13:20Z / credential.id: cred-36b2 / credential.expires_at: 2026-09-17T06:5… | — |
| 7 | — | act [ok] | run_task(component=bank, task=rotate_credential) | Credential is expired; rotate it. | rotate_credential: issued cred-f489, expires 2026-10-21T14:13:20Z | — |
| 8 | — | act [ok] | set_config(component=bank, key=key_in_use, value=key-7prqse) | Signing key differs from the vault's active key; set it from the vault value. | applied: bank.key_in_use = key-7prqse | — |
| 9 | — | observe | check_pipeline() | Find the first failing stage. | Components: / ledger: up / worker: running (queue depth: 0) / bank: up / settlement: last run stopped (401) /… | — |
| 10 | — | observe | get_batch_status() | Check progress and checkpoint before settling. | Batch: 0 sent, 20 pending / Checkpoint: next payout to send is payout #1 (PO-1001) / Payouts sent more than o… | — |
| 11 | — | act [ok] | run_settlement(mode=full) | Settle remaining payouts. | run_settlement(full): sent 20 payouts this run (#1-#20). Run complete. Total sent: 20/20. | — |
| 12 | — | observe | check_pipeline() | Find the first failing stage. | Components: / ledger: up / worker: running (queue depth: 0) / bank: up / settlement: last run complete / Payo… | — |
| 13 | — | final | GOAL_MET | — | goal confirmed by check_pipeline | — |


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


## oneshot · dev_f2 · `oneshot-dev_f2-s11-r1-20261010T125927665564`

- Source: `runs/oneshot-dev_f2-s11-r1-20261010T125927665564.jsonl` (12 events; complete)
- Arm: oneshot — source: GOAL.eval.arm; model: `groq:openai/gpt-oss-120b`; faults: F2
- Reasons in the timeline: scripted: fixed strings in baselines/oneshot.py; the LLM produced only the action list

**Measured**

- Final: **GOAL_NOT_MET** — executed 1 listed actions blindly (0 malformed)
- Goal met: False; duplicate payouts: 0; faults active at end: F2 *(evaluation-only state, read after the run)*
- Payouts last shown in the log: 0/20
- Actions: 1 (1 ok, 0 refused, 0 rejected)
- Verifier: n/a (arm does not submit a report)
- LLM: 1 successful calls, 0 failed attempts; tokens 611 in + 54 out = 665; LLM latency 0.69 s
- Errors: 0 rate-limit retries, 0 other failed LLM attempts, 0 nudges; wall-clock 0.77 s

**Derived**

- Action validity: 1.00
- Component inspected before acting on it: 0/0
- Failure responses: 1 failure events; replanning n/a (arm does not plan)
- Repeated rejected actions: none
- All faults cleared *(evaluation-only)*: never — still active at end: F2
- Time outside successful LLM calls: 0.08 s; tokens per LLM call: 665.0

**Report diagnostics** *(descriptive; not SPEC §9 metrics; verifier pass/fail unchanged; no-effect annotations are evaluation-only, read after the run)*

- n/a — oneshot arm does not submit an incident report

**Unavailable / not applicable**

- plans_and_replanning: oneshot arm does not plan
- verifier: oneshot arm does not submit an incident report

Timeline (`errors before` = folded ERROR events; `eval flags` = evaluation-only):

| seq | errors before | stage | event | scripted reason | environment response | eval flags |
|---|---|---|---|---|---|---|
| 1 | — | goal | model groq:openai/gpt-oss-120b | — | — | — |
| 2 | — | observe | check_pipeline() | t0 snapshot: overall status. | Components: / ledger: up / worker: running (queue depth: 0) / bank: up / settlement: idle / Payouts sent: 0/2… | — |
| 3 | — | observe | inspect(component=ledger) | t0 snapshot: inspect ledger. | ledger: / up: true / disk_pct: 37 / conn_used: 5 / conn_max: 20 / records: 0 | — |
| 4 | — | observe | inspect(component=worker) | t0 snapshot: inspect worker. | worker: / running: true / queue_depth: 0 | — |
| 5 | — | observe | inspect(component=bank) | t0 snapshot: inspect bank. | bank: / server_time: 2026-09-21T14:13:20Z / credential.id: cred-e79e / credential.expires_at: 2026-10-19T14:1… | — |
| 6 | — | observe | inspect(component=settlement) | t0 snapshot: inspect settlement. | settlement: / checkpoint: 0 / payouts_sent: 0 / last_run: none | — |
| 7 | — | observe | read_logs(component=ledger, n=30) | t0 snapshot: logs of ledger. | [t=0000] INFO ledger started | — |
| 8 | — | observe | read_logs(component=worker, n=30) | t0 snapshot: logs of worker. | [t=0000] INFO worker started | — |
| 9 | — | observe | read_logs(component=bank, n=30) | t0 snapshot: logs of bank. | [t=0000] INFO gateway connected | — |
| 10 | — | observe | read_logs(component=settlement, n=30) | t0 snapshot: logs of settlement. | [t=0000] INFO batch of 20 payouts loaded | — |
| 11 | — | act [ok] | run_settlement(mode=full) | One-shot action 1 of 1. | run_settlement(full): sent 0 payouts this run. Stopped at payout #1 (PO-1001): 401 Unauthorized. Total sent: … | new_failure_exposed, no_effect |
| 12 | — | final | GOAL_NOT_MET | — | executed 1 listed actions blindly (0 malformed) | — |


## runbook · dev_f2 · `runbook-dev_f2-s11-r1-20261010T123930382597`

- Source: `runs/runbook-dev_f2-s11-r1-20261010T123930382597.jsonl` (12 events; complete)
- Arm: runbook — source: GOAL.eval.arm; model: `none`; faults: F2
- Reasons in the timeline: scripted: fixed strings in baselines/runbook.py (no LLM)

**Measured**

- Final: **GOAL_MET** — goal confirmed by check_pipeline
- Goal met: True; duplicate payouts: 0; faults active at end: none *(evaluation-only state, read after the run)*
- Payouts last shown in the log: 20/20
- Actions: 3 (3 ok, 0 refused, 0 rejected)
- Verifier: n/a (arm does not submit a report)
- LLM: none (runbook makes no LLM calls)
- Errors: 0 rate-limit retries, 0 other failed LLM attempts, 0 nudges; wall-clock 0.0 s

**Derived**

- Action validity: 1.00
- Component inspected before acting on it: 1/1 (weak evidence: says nothing about whether the target was right)
- Failure responses: 1 failure events; replanning n/a (arm does not plan)
- Repeated rejected actions: none
- All faults cleared *(evaluation-only)*: at #7 by `set_config(component=bank, key=key_in_use, value=key-326ml6)`; afterwards settlement: #10; check_pipeline: #8, #11 (4 steps after)
- Time outside successful LLM calls: n/a; tokens per LLM call: n/a

**Report diagnostics** *(descriptive; not SPEC §9 metrics; verifier pass/fail unchanged; no-effect annotations are evaluation-only, read after the run)*

- n/a — runbook arm does not submit an incident report

`set_config` grounding (key / value seen in an earlier observation; `—` = value too short to be evidence):

| seq | component | key | value | outcome | key_seen_before | value_seen_before |
|---|---|---|---|---|---|---|
| 7 | bank | key_in_use | key-326ml6 | ok | True | True |


**Unavailable / not applicable**

- plans_and_replanning: runbook arm does not plan
- verifier: runbook arm does not submit an incident report
- llm_tokens_latency: not applicable: runbook makes no LLM calls (0 calls logged)

Timeline (`errors before` = folded ERROR events; `eval flags` = evaluation-only):

| seq | errors before | stage | event | scripted reason | environment response | eval flags |
|---|---|---|---|---|---|---|
| 1 | — | goal | model none | — | — | — |
| 2 | — | observe | check_pipeline() | Find the first failing stage. | Components: / ledger: up / worker: running (queue depth: 0) / bank: up / settlement: idle / Payouts sent: 0/2… | — |
| 3 | — | observe | get_batch_status() | Check progress and checkpoint before settling. | Batch: 0 sent, 20 pending / Checkpoint: next payout to send is payout #1 (PO-1001) / Payouts sent more than o… | — |
| 4 | — | act [ok] | run_settlement(mode=full) | Settle remaining payouts. | run_settlement(full): sent 0 payouts this run. Stopped at payout #1 (PO-1001): 401 Unauthorized. Total sent: … | new_failure_exposed, no_effect |
| 5 | — | observe | read_logs(component=bank, n=10) | Settlement stopped on authentication; read bank logs. | [t=0000] INFO gateway connected / [t=0001] ERROR 401 Unauthorized (payout PO-1001) | — |
| 6 | — | observe | inspect(component=bank) | Disambiguate authentication failure causes from bank config. | bank: / server_time: 2026-09-21T14:13:20Z / credential.id: cred-e79e / credential.expires_at: 2026-10-19T14:1… | — |
| 7 | — | act [ok] | set_config(component=bank, key=key_in_use, value=key-326ml6) | Signing key differs from the vault's active key; set it from the vault value. | applied: bank.key_in_use = key-326ml6 | — |
| 8 | — | observe | check_pipeline() | Find the first failing stage. | Components: / ledger: up / worker: running (queue depth: 0) / bank: up / settlement: last run stopped (401) /… | — |
| 9 | — | observe | get_batch_status() | Check progress and checkpoint before settling. | Batch: 0 sent, 20 pending / Checkpoint: next payout to send is payout #1 (PO-1001) / Payouts sent more than o… | — |
| 10 | — | act [ok] | run_settlement(mode=full) | Settle remaining payouts. | run_settlement(full): sent 20 payouts this run (#1-#20). Run complete. Total sent: 20/20. | — |
| 11 | — | observe | check_pipeline() | Find the first failing stage. | Components: / ledger: up / worker: running (queue depth: 0) / bank: up / settlement: last run complete / Payo… | — |
| 12 | — | final | GOAL_MET | — | goal confirmed by check_pipeline | — |


## oneshot · dev_f4 · `oneshot-dev_f4-s12-r1-20261010T125928438467`

- Source: `runs/oneshot-dev_f4-s12-r1-20261010T125928438467.jsonl` (15 events; complete)
- Arm: oneshot — source: GOAL.eval.arm; model: `groq:openai/gpt-oss-120b`; faults: F4
- Reasons in the timeline: scripted: fixed strings in baselines/oneshot.py; the LLM produced only the action list

**Measured**

- Final: **GOAL_MET** — executed 4 listed actions blindly (0 malformed)
- Goal met: True; duplicate payouts: 0; faults active at end: none *(evaluation-only state, read after the run)*
- Payouts last shown in the log: 20/20
- Actions: 4 (3 ok, 1 refused, 0 rejected)
- Verifier: n/a (arm does not submit a report)
- LLM: 1 successful calls, 0 failed attempts; tokens 652 in + 124 out = 776; LLM latency 0.8 s
- Errors: 0 rate-limit retries, 0 other failed LLM attempts, 0 nudges; wall-clock 0.81 s

**Derived**

- Action validity: 1.00
- Component inspected before acting on it: 3/3 (weak evidence: says nothing about whether the target was right)
- Failure responses: 2 failure events; replanning n/a (arm does not plan)
- Repeated rejected actions: none
- All faults cleared *(evaluation-only)*: at #11 by `run_task(component=ledger, task=rotate_logs)`; afterwards settlement: #14; check_pipeline: none (3 steps after)
- Time outside successful LLM calls: 0.01 s; tokens per LLM call: 776.0

**Report diagnostics** *(descriptive; not SPEC §9 metrics; verifier pass/fail unchanged; no-effect annotations are evaluation-only, read after the run)*

- n/a — oneshot arm does not submit an incident report

**Unavailable / not applicable**

- plans_and_replanning: oneshot arm does not plan
- verifier: oneshot arm does not submit an incident report

Timeline (`errors before` = folded ERROR events; `eval flags` = evaluation-only):

| seq | errors before | stage | event | scripted reason | environment response | eval flags |
|---|---|---|---|---|---|---|
| 1 | — | goal | model groq:openai/gpt-oss-120b | — | — | — |
| 2 | — | observe | check_pipeline() | t0 snapshot: overall status. | Components: / ledger: up / worker: running (queue depth: 27) / bank: up / settlement: idle / Payouts sent: 0/… | — |
| 3 | — | observe | inspect(component=ledger) | t0 snapshot: inspect ledger. | ledger: / up: true / disk_pct: 97 / conn_used: 3 / conn_max: 20 / records: 0 | — |
| 4 | — | observe | inspect(component=worker) | t0 snapshot: inspect worker. | worker: / running: true / queue_depth: 27 | — |
| 5 | — | observe | inspect(component=bank) | t0 snapshot: inspect bank. | bank: / server_time: 2026-09-21T14:13:20Z / credential.id: cred-f2fa / credential.expires_at: 2026-09-30T14:1… | — |
| 6 | — | observe | inspect(component=settlement) | t0 snapshot: inspect settlement. | settlement: / checkpoint: 0 / payouts_sent: 0 / last_run: none | — |
| 7 | — | observe | read_logs(component=ledger, n=30) | t0 snapshot: logs of ledger. | [t=0000] INFO ledger started / [t=0000] ERROR write failed: no space left on device (disk 97%) | — |
| 8 | — | observe | read_logs(component=worker, n=30) | t0 snapshot: logs of worker. | [t=0000] INFO worker started / [t=0000] ERROR write to ledger failed: no space left on device (queue=27) | — |
| 9 | — | observe | read_logs(component=bank, n=30) | t0 snapshot: logs of bank. | [t=0000] INFO gateway connected | — |
| 10 | — | observe | read_logs(component=settlement, n=30) | t0 snapshot: logs of settlement. | [t=0000] INFO batch of 20 payouts loaded | — |
| 11 | — | act [ok] | run_task(component=ledger, task=rotate_logs) | One-shot action 1 of 4. | rotate_logs: archived old logs; disk usage 97% -> 57% | — |
| 12 | — | act [refused] | restart(component=ledger) | One-shot action 2 of 4. | refused: ledger has 3 active sessions | refusal |
| 13 | — | act [ok] | restart(component=worker) | One-shot action 3 of 4. | worker restarted: running; queue depth now 0 | no_effect |
| 14 | — | act [ok] | run_settlement(mode=full) | One-shot action 4 of 4. | run_settlement(full): sent 20 payouts this run (#1-#20). Run complete. Total sent: 20/20. | — |
| 15 | — | final | GOAL_MET | — | executed 4 listed actions blindly (0 malformed) | — |


## runbook · dev_f4 · `runbook-dev_f4-s12-r1-20261010T123930383764`

- Source: `runs/runbook-dev_f4-s12-r1-20261010T123930383764.jsonl` (11 events; complete)
- Arm: runbook — source: GOAL.eval.arm; model: `none`; faults: F4
- Reasons in the timeline: scripted: fixed strings in baselines/runbook.py (no LLM)

**Measured**

- Final: **GOAL_MET** — goal confirmed by check_pipeline
- Goal met: True; duplicate payouts: 0; faults active at end: none *(evaluation-only state, read after the run)*
- Payouts last shown in the log: 20/20
- Actions: 2 (2 ok, 0 refused, 0 rejected)
- Verifier: n/a (arm does not submit a report)
- LLM: none (runbook makes no LLM calls)
- Errors: 0 rate-limit retries, 0 other failed LLM attempts, 0 nudges; wall-clock 0.0 s

**Derived**

- Action validity: 1.00
- Component inspected before acting on it: 1/1 (weak evidence: says nothing about whether the target was right)
- Failure responses: 0 failure events; replanning n/a (arm does not plan)
- Repeated rejected actions: none
- All faults cleared *(evaluation-only)*: at #6 by `run_task(component=ledger, task=rotate_logs)`; afterwards settlement: #9; check_pipeline: #7, #10 (4 steps after)
- Time outside successful LLM calls: n/a; tokens per LLM call: n/a

**Report diagnostics** *(descriptive; not SPEC §9 metrics; verifier pass/fail unchanged; no-effect annotations are evaluation-only, read after the run)*

- n/a — runbook arm does not submit an incident report

**Unavailable / not applicable**

- plans_and_replanning: runbook arm does not plan
- verifier: runbook arm does not submit an incident report
- llm_tokens_latency: not applicable: runbook makes no LLM calls (0 calls logged)

Timeline (`errors before` = folded ERROR events; `eval flags` = evaluation-only):

| seq | errors before | stage | event | scripted reason | environment response | eval flags |
|---|---|---|---|---|---|---|
| 1 | — | goal | model none | — | — | — |
| 2 | — | observe | check_pipeline() | Find the first failing stage. | Components: / ledger: up / worker: running (queue depth: 27) / bank: up / settlement: idle / Payouts sent: 0/… | — |
| 3 | — | observe | inspect(component=worker) | Check whether the worker is running. | worker: / running: true / queue_depth: 27 | — |
| 4 | — | observe | read_logs(component=worker, n=10) | Worker is running but the queue is not draining; read its errors. | [t=0000] INFO worker started / [t=0000] ERROR write to ledger failed: no space left on device (queue=27) | — |
| 5 | — | observe | inspect(component=ledger) | Confirm ledger disk usage before freeing space. | ledger: / up: true / disk_pct: 97 / conn_used: 3 / conn_max: 20 / records: 0 | — |
| 6 | — | act [ok] | run_task(component=ledger, task=rotate_logs) | Disk is full; rotate logs to free space. | rotate_logs: archived old logs; disk usage 97% -> 57% | — |
| 7 | — | observe | check_pipeline() | Find the first failing stage. | Components: / ledger: up / worker: running (queue depth: 0) / bank: up / settlement: idle / Payouts sent: 0/2… | — |
| 8 | — | observe | get_batch_status() | Check progress and checkpoint before settling. | Batch: 0 sent, 20 pending / Checkpoint: next payout to send is payout #1 (PO-1001) / Payouts sent more than o… | — |
| 9 | — | act [ok] | run_settlement(mode=full) | Settle remaining payouts. | run_settlement(full): sent 20 payouts this run (#1-#20). Run complete. Total sent: 20/20. | — |
| 10 | — | observe | check_pipeline() | Find the first failing stage. | Components: / ledger: up / worker: running (queue depth: 0) / bank: up / settlement: last run complete / Payo… | — |
| 11 | — | final | GOAL_MET | — | goal confirmed by check_pipeline | — |


## oneshot · dev_f4_f6 · `oneshot-dev_f4_f6-s15-r1-20261010T125930487358`

- Source: `runs/oneshot-dev_f4_f6-s15-r1-20261010T125930487358.jsonl` (13 events; complete)
- Arm: oneshot — source: GOAL.eval.arm; model: `groq:openai/gpt-oss-120b`; faults: F4, F6
- Reasons in the timeline: scripted: fixed strings in baselines/oneshot.py; the LLM produced only the action list

**Measured**

- Final: **GOAL_NOT_MET** — executed 2 listed actions blindly (0 malformed)
- Goal met: False; duplicate payouts: 0; faults active at end: F4 *(evaluation-only state, read after the run)*
- Payouts last shown in the log: 0/20
- Actions: 2 (1 ok, 1 refused, 0 rejected)
- Verifier: n/a (arm does not submit a report)
- LLM: 1 successful calls, 0 failed attempts; tokens 623 in + 100 out = 723; LLM latency 0.64 s
- Errors: 0 rate-limit retries, 0 other failed LLM attempts, 0 nudges; wall-clock 0.65 s

**Derived**

- Action validity: 1.00
- Component inspected before acting on it: 1/1 (weak evidence: says nothing about whether the target was right)
- Failure responses: 1 failure events; replanning n/a (arm does not plan)
- Repeated rejected actions: none
- All faults cleared *(evaluation-only)*: never — still active at end: F4
- Time outside successful LLM calls: 0.01 s; tokens per LLM call: 723.0

**Report diagnostics** *(descriptive; not SPEC §9 metrics; verifier pass/fail unchanged; no-effect annotations are evaluation-only, read after the run)*

- n/a — oneshot arm does not submit an incident report

**Unavailable / not applicable**

- plans_and_replanning: oneshot arm does not plan
- verifier: oneshot arm does not submit an incident report

Timeline (`errors before` = folded ERROR events; `eval flags` = evaluation-only):

| seq | errors before | stage | event | scripted reason | environment response | eval flags |
|---|---|---|---|---|---|---|
| 1 | — | goal | model groq:openai/gpt-oss-120b | — | — | — |
| 2 | — | observe | check_pipeline() | t0 snapshot: overall status. | Components: / ledger: up / worker: stopped (queue depth: 37) / bank: up / settlement: idle / Payouts sent: 0/… | — |
| 3 | — | observe | inspect(component=ledger) | t0 snapshot: inspect ledger. | ledger: / up: true / disk_pct: 96 / conn_used: 8 / conn_max: 20 / records: 0 | — |
| 4 | — | observe | inspect(component=worker) | t0 snapshot: inspect worker. | worker: / running: false / queue_depth: 37 | — |
| 5 | — | observe | inspect(component=bank) | t0 snapshot: inspect bank. | bank: / server_time: 2026-09-21T14:13:20Z / credential.id: cred-6aff / credential.expires_at: 2026-09-22T14:1… | — |
| 6 | — | observe | inspect(component=settlement) | t0 snapshot: inspect settlement. | settlement: / checkpoint: 0 / payouts_sent: 0 / last_run: none | — |
| 7 | — | observe | read_logs(component=ledger, n=30) | t0 snapshot: logs of ledger. | [t=0000] INFO ledger started | — |
| 8 | — | observe | read_logs(component=worker, n=30) | t0 snapshot: logs of worker. | [t=0000] INFO worker started / [t=0000] WARN worker process exited unexpectedly | — |
| 9 | — | observe | read_logs(component=bank, n=30) | t0 snapshot: logs of bank. | [t=0000] INFO gateway connected | — |
| 10 | — | observe | read_logs(component=settlement, n=30) | t0 snapshot: logs of settlement. | [t=0000] INFO batch of 20 payouts loaded | — |
| 11 | — | act [ok] | restart(component=worker) | One-shot action 1 of 2. | worker restarted: running; queue depth now 37 | — |
| 12 | — | act [refused] | run_settlement(mode=full) | One-shot action 2 of 2. | refused: 37 payments unconfirmed in ledger | refusal |
| 13 | — | final | GOAL_NOT_MET | — | executed 2 listed actions blindly (0 malformed) | — |


## runbook · dev_f4_f6 · `runbook-dev_f4_f6-s15-r1-20261010T123930387877`

- Source: `runs/runbook-dev_f4_f6-s15-r1-20261010T123930387877.jsonl` (14 events; complete)
- Arm: runbook — source: GOAL.eval.arm; model: `none`; faults: F4, F6
- Reasons in the timeline: scripted: fixed strings in baselines/runbook.py (no LLM)

**Measured**

- Final: **GOAL_MET** — goal confirmed by check_pipeline
- Goal met: True; duplicate payouts: 0; faults active at end: none *(evaluation-only state, read after the run)*
- Payouts last shown in the log: 20/20
- Actions: 3 (3 ok, 0 refused, 0 rejected)
- Verifier: n/a (arm does not submit a report)
- LLM: none (runbook makes no LLM calls)
- Errors: 0 rate-limit retries, 0 other failed LLM attempts, 0 nudges; wall-clock 0.0 s

**Derived**

- Action validity: 1.00
- Component inspected before acting on it: 2/2 (weak evidence: says nothing about whether the target was right)
- Failure responses: 0 failure events; replanning n/a (arm does not plan)
- Repeated rejected actions: none
- All faults cleared *(evaluation-only)*: at #9 by `run_task(component=ledger, task=rotate_logs)`; afterwards settlement: #12; check_pipeline: #10, #13 (4 steps after)
- Time outside successful LLM calls: n/a; tokens per LLM call: n/a

**Report diagnostics** *(descriptive; not SPEC §9 metrics; verifier pass/fail unchanged; no-effect annotations are evaluation-only, read after the run)*

- n/a — runbook arm does not submit an incident report

**Unavailable / not applicable**

- plans_and_replanning: runbook arm does not plan
- verifier: runbook arm does not submit an incident report
- llm_tokens_latency: not applicable: runbook makes no LLM calls (0 calls logged)

Timeline (`errors before` = folded ERROR events; `eval flags` = evaluation-only):

| seq | errors before | stage | event | scripted reason | environment response | eval flags |
|---|---|---|---|---|---|---|
| 1 | — | goal | model none | — | — | — |
| 2 | — | observe | check_pipeline() | Find the first failing stage. | Components: / ledger: up / worker: stopped (queue depth: 37) / bank: up / settlement: idle / Payouts sent: 0/… | — |
| 3 | — | observe | inspect(component=worker) | Check whether the worker is running. | worker: / running: false / queue_depth: 37 | — |
| 4 | — | act [ok] | restart(component=worker) | Worker is stopped; restart it. | worker restarted: running; queue depth now 37 | — |
| 5 | — | observe | check_pipeline() | Find the first failing stage. | Components: / ledger: up / worker: running (queue depth: 37) / bank: up / settlement: idle / Payouts sent: 0/… | — |
| 6 | — | observe | inspect(component=worker) | Check whether the worker is running. | worker: / running: true / queue_depth: 37 | — |
| 7 | — | observe | read_logs(component=worker, n=10) | Worker is running but the queue is not draining; read its errors. | [t=0000] INFO worker started / [t=0000] WARN worker process exited unexpectedly / [t=0001] INFO worker starte… | — |
| 8 | — | observe | inspect(component=ledger) | Confirm ledger disk usage before freeing space. | ledger: / up: true / disk_pct: 96 / conn_used: 8 / conn_max: 20 / records: 0 | — |
| 9 | — | act [ok] | run_task(component=ledger, task=rotate_logs) | Disk is full; rotate logs to free space. | rotate_logs: archived old logs; disk usage 96% -> 56% | — |
| 10 | — | observe | check_pipeline() | Find the first failing stage. | Components: / ledger: up / worker: running (queue depth: 0) / bank: up / settlement: idle / Payouts sent: 0/2… | — |
| 11 | — | observe | get_batch_status() | Check progress and checkpoint before settling. | Batch: 0 sent, 20 pending / Checkpoint: next payout to send is payout #1 (PO-1001) / Payouts sent more than o… | — |
| 12 | — | act [ok] | run_settlement(mode=full) | Settle remaining payouts. | run_settlement(full): sent 20 payouts this run (#1-#20). Run complete. Total sent: 20/20. | — |
| 13 | — | observe | check_pipeline() | Find the first failing stage. | Components: / ledger: up / worker: running (queue depth: 0) / bank: up / settlement: last run complete / Payo… | — |
| 14 | — | final | GOAL_MET | — | goal confirmed by check_pipeline | — |


## oneshot · dev_f7 · `oneshot-dev_f7-s13-r1-20261010T125929258626`

- Source: `runs/oneshot-dev_f7-s13-r1-20261010T125929258626.jsonl` (12 events; complete)
- Arm: oneshot — source: GOAL.eval.arm; model: `groq:openai/gpt-oss-120b`; faults: F7
- Reasons in the timeline: scripted: fixed strings in baselines/oneshot.py; the LLM produced only the action list

**Measured**

- Final: **GOAL_NOT_MET** — executed 1 listed actions blindly (0 malformed)
- Goal met: False; duplicate payouts: 0; faults active at end: F7 *(evaluation-only state, read after the run)*
- Payouts last shown in the log: 6/20
- Actions: 1 (1 ok, 0 refused, 0 rejected)
- Verifier: n/a (arm does not submit a report)
- LLM: 1 successful calls, 0 failed attempts; tokens 608 in + 49 out = 657; LLM latency 0.42 s
- Errors: 0 rate-limit retries, 0 other failed LLM attempts, 0 nudges; wall-clock 0.44 s

**Derived**

- Action validity: 1.00
- Component inspected before acting on it: 0/0
- Failure responses: 1 failure events; replanning n/a (arm does not plan)
- Repeated rejected actions: none
- All faults cleared *(evaluation-only)*: never — still active at end: F7
- Time outside successful LLM calls: 0.02 s; tokens per LLM call: 657.0

**Report diagnostics** *(descriptive; not SPEC §9 metrics; verifier pass/fail unchanged; no-effect annotations are evaluation-only, read after the run)*

- n/a — oneshot arm does not submit an incident report

**Unavailable / not applicable**

- plans_and_replanning: oneshot arm does not plan
- verifier: oneshot arm does not submit an incident report

Timeline (`errors before` = folded ERROR events; `eval flags` = evaluation-only):

| seq | errors before | stage | event | scripted reason | environment response | eval flags |
|---|---|---|---|---|---|---|
| 1 | — | goal | model groq:openai/gpt-oss-120b | — | — | — |
| 2 | — | observe | check_pipeline() | t0 snapshot: overall status. | Components: / ledger: up / worker: running (queue depth: 0) / bank: up / settlement: idle / Payouts sent: 0/2… | — |
| 3 | — | observe | inspect(component=ledger) | t0 snapshot: inspect ledger. | ledger: / up: true / disk_pct: 52 / conn_used: 2 / conn_max: 20 / records: 0 | — |
| 4 | — | observe | inspect(component=worker) | t0 snapshot: inspect worker. | worker: / running: true / queue_depth: 0 | — |
| 5 | — | observe | inspect(component=bank) | t0 snapshot: inspect bank. | bank: / server_time: 2026-09-21T14:13:20Z / credential.id: cred-849c / credential.expires_at: 2026-10-01T14:1… | — |
| 6 | — | observe | inspect(component=settlement) | t0 snapshot: inspect settlement. | settlement: / checkpoint: 0 / payouts_sent: 0 / last_run: none | — |
| 7 | — | observe | read_logs(component=ledger, n=30) | t0 snapshot: logs of ledger. | [t=0000] INFO ledger started | — |
| 8 | — | observe | read_logs(component=worker, n=30) | t0 snapshot: logs of worker. | [t=0000] INFO worker started | — |
| 9 | — | observe | read_logs(component=bank, n=30) | t0 snapshot: logs of bank. | [t=0000] INFO gateway connected | — |
| 10 | — | observe | read_logs(component=settlement, n=30) | t0 snapshot: logs of settlement. | [t=0000] INFO batch of 20 payouts loaded | — |
| 11 | — | act [ok] | run_settlement(mode=full) | One-shot action 1 of 1. | run_settlement(full): sent 6 payouts this run (#1-#6). Stopped at payout #7 (PO-1007): 429 Too Many Requests … | new_failure_exposed |
| 12 | — | final | GOAL_NOT_MET | — | executed 1 listed actions blindly (0 malformed) | — |


## runbook · dev_f7 · `runbook-dev_f7-s13-r1-20261010T123930385074`

- Source: `runs/runbook-dev_f7-s13-r1-20261010T123930385074.jsonl` (10 events; complete)
- Arm: runbook — source: GOAL.eval.arm; model: `none`; faults: F7
- Reasons in the timeline: scripted: fixed strings in baselines/runbook.py (no LLM)

**Measured**

- Final: **GOAL_MET** — goal confirmed by check_pipeline
- Goal met: True; duplicate payouts: 0; faults active at end: none *(evaluation-only state, read after the run)*
- Payouts last shown in the log: 20/20
- Actions: 3 (3 ok, 0 refused, 0 rejected)
- Verifier: n/a (arm does not submit a report)
- LLM: none (runbook makes no LLM calls)
- Errors: 0 rate-limit retries, 0 other failed LLM attempts, 0 nudges; wall-clock 0.0 s

**Derived**

- Action validity: 1.00
- Component inspected before acting on it: 0/1 (weak evidence: says nothing about whether the target was right)
- Failure responses: 1 failure events; replanning n/a (arm does not plan)
- Repeated rejected actions: none
- All faults cleared *(evaluation-only)*: at #5 by `set_config(component=bank, key=max_concurrency, value=4)`; afterwards settlement: #8; check_pipeline: #6, #9 (4 steps after)
- Time outside successful LLM calls: n/a; tokens per LLM call: n/a

**Report diagnostics** *(descriptive; not SPEC §9 metrics; verifier pass/fail unchanged; no-effect annotations are evaluation-only, read after the run)*

- n/a — runbook arm does not submit an incident report

`set_config` grounding (key / value seen in an earlier observation; `—` = value too short to be evidence):

| seq | component | key | value | outcome | key_seen_before | value_seen_before |
|---|---|---|---|---|---|---|
| 5 | bank | max_concurrency | 4 | ok | False | — |


**Unavailable / not applicable**

- plans_and_replanning: runbook arm does not plan
- verifier: runbook arm does not submit an incident report
- llm_tokens_latency: not applicable: runbook makes no LLM calls (0 calls logged)

Timeline (`errors before` = folded ERROR events; `eval flags` = evaluation-only):

| seq | errors before | stage | event | scripted reason | environment response | eval flags |
|---|---|---|---|---|---|---|
| 1 | — | goal | model none | — | — | — |
| 2 | — | observe | check_pipeline() | Find the first failing stage. | Components: / ledger: up / worker: running (queue depth: 0) / bank: up / settlement: idle / Payouts sent: 0/2… | — |
| 3 | — | observe | get_batch_status() | Check progress and checkpoint before settling. | Batch: 0 sent, 20 pending / Checkpoint: next payout to send is payout #1 (PO-1001) / Payouts sent more than o… | — |
| 4 | — | act [ok] | run_settlement(mode=full) | Settle remaining payouts. | run_settlement(full): sent 6 payouts this run (#1-#6). Stopped at payout #7 (PO-1007): 429 Too Many Requests … | new_failure_exposed |
| 5 | — | act [ok] | set_config(component=bank, key=max_concurrency, value=4) | Rate limit reported by bank; keep concurrency within it. | applied: bank.max_concurrency = 4 | — |
| 6 | — | observe | check_pipeline() | Find the first failing stage. | Components: / ledger: up / worker: running (queue depth: 0) / bank: up / settlement: last run stopped (429) /… | — |
| 7 | — | observe | get_batch_status() | Check progress and checkpoint before settling. | Batch: 6 sent, 14 pending / Checkpoint: next payout to send is payout #7 (PO-1007) / Payouts sent more than o… | — |
| 8 | — | act [ok] | run_settlement(mode=resume) | Settle remaining payouts. | run_settlement(resume): sent 14 payouts this run (#7-#20). Run complete. Total sent: 20/20. | — |
| 9 | — | observe | check_pipeline() | Find the first failing stage. | Components: / ledger: up / worker: running (queue depth: 0) / bank: up / settlement: last run complete / Payo… | — |
| 10 | — | final | GOAL_MET | — | goal confirmed by check_pipeline | — |


## nidaan · hero · `hero-s323-20261010T122852`

- Source: `runs/hero-s323-20261010T122852.jsonl` (42 events; complete)
- Arm: nidaan — source: default 'nidaan' (no arm in GOAL.eval: CLI run; same default as evaluation.metrics); model: `groq:openai/gpt-oss-120b`; faults: F6, F1, F7
- Reasons in the timeline: agent-supplied: the `why` argument the LLM attached to each tool call (stated text, not verified)

**Measured**

- Final: **VERIFIED** — goal verified
- Goal met: True; duplicate payouts: 0; faults active at end: none *(evaluation-only state, read after the run)*
- Payouts last shown in the log: 20/20
- Actions: 9 (6 ok, 0 refused, 3 rejected)
- Verifier: 1 submitted, 1 passed; last: V1✓ V2✓ V3✓
- LLM: 23 successful calls, 17 failed attempts; tokens 50468 in + 2024 out = 52492; LLM latency 18.04 s
- Errors: 17 rate-limit retries, 0 other failed LLM attempts, 1 nudge; wall-clock 244.12 s

**Derived**

- Action validity: 0.67
- Component inspected before acting on it: 6/6 (weak evidence: says nothing about whether the target was right)
- Failure responses: 5 failure events (2 falsifying per SPEC §9 + 3 rejections or other); accepted plan within 2 steps after 1 of them. SPEC §9 appropriate replanning (falsifying events only): 0/2
- Repeated rejected actions: none
- All faults cleared *(evaluation-only)*: at #33 by `set_config(component=bank, key=max_concurrency, value=1)`; afterwards settlement: #35; check_pipeline: #37 (3 steps after)
- Time outside successful LLM calls: 226.08 s; tokens per LLM call: 2282.3

**Report diagnostics** *(descriptive; not SPEC §9 metrics; verifier pass/fail unchanged; no-effect annotations are evaluation-only, read after the run)*

- Report: VERIFY #41 (verifier: pass; 1 submitted; the last is analysed)
- Action coverage: 6/6 executed actions listed; omitted: none; listed but not executed: none; invalid references: none; duplicates: none
- Root cause 1 (worker), cites #4: no flag
- Root cause 2 (bank), cites #13, #21: no flag
- Root cause 3 (bank), cites #25, #21: no flag

`set_config` grounding (key / value seen in an earlier observation; `—` = value too short to be evidence):

| seq | component | key | value | outcome | key_seen_before | value_seen_before |
|---|---|---|---|---|---|---|
| 19 | settlement | auth_token | newtoken123 | rejected | False | False |
| 33 | bank | max_concurrency | 1 | ok | True | — |


Replan triggers (events cited by each accepted plan update):

- plan v2 (#5): #4 OBSERVE `inspect(component=worker)` [ok]
- plan v3 (#31): #25 ACT `run_settlement(mode=resume)` [ok]

Timeline (`errors before` = folded ERROR events; `eval flags` = evaluation-only):

| seq | errors before | stage | event | stated why (LLM) | environment response | eval flags |
|---|---|---|---|---|---|---|
| 1 | — | goal | model groq:openai/gpt-oss-120b | — | — | — |
| 2 | — | plan | plan v1 | — | +7/-0 steps; reason: Initial investigation of stalled settlement batch | — |
| 3 | — | observe | check_pipeline() | Determine if batch is stalled and components health | Components: / ledger: up / worker: stopped (queue depth: 37) / bank: up / settlement: idle / Payouts sent: 0/… | — |
| 4 | — | observe | inspect(component=worker) | Check worker config for queue handling | worker: / running: false / queue_depth: 37 | — |
| 5 | — | replan | plan v2 <- triggered by [4] | — | +4/-7 steps; reason: Worker stopped causing batch stall | — |
| 6 | — | act [ok] | restart(component=worker) | Start worker to process queue | worker restarted: running; queue depth now 0 | — |
| 7 | — | observe | check_pipeline() | Verify pipeline after worker restart | Components: / ledger: up / worker: running (queue depth: 0) / bank: up / settlement: idle / Payouts sent: 0/2… | — |
| 9 | rate_limit_retries=1 | act [ok] | run_settlement(mode=resume) | Attempt to process pending payouts | run_settlement(resume): sent 0 payouts this run. Stopped at payout #1 (PO-1001): 401 Unauthorized. Total sent… | new_failure_exposed, no_effect |
| 11 | rate_limit_retries=1 | observe | inspect(component=settlement) | Check settlement config for auth credentials | settlement: / checkpoint: 0 / payouts_sent: 0 / last_run: last run stopped (401) | — |
| 13 | rate_limit_retries=1 | observe | read_logs(component=settlement, n=20) | Find auth error details | [t=0000] INFO batch of 20 payouts loaded / [t=0002] ERROR payout PO-1001 stopped: 401 Unauthorized | — |
| 15 | rate_limit_retries=1 | act [rejected] | run_task(component=settlement, task=rotate_credential) | Refresh auth credentials to fix 401 | rejected: task 'rotate_credential' is not available on settlement | — |
| 17 | rate_limit_retries=1 | observe | inspect(component=settlement) | List config keys | settlement: / checkpoint: 0 / payouts_sent: 0 / last_run: last run stopped (401) | — |
| 19 | rate_limit_retries=1 | act [rejected] | set_config(component=settlement, key=auth_token, value=newtoken123) | Set valid auth token to resolve 401 | rejected: 'auth_token' is not a settable key on settlement; settable: none | — |
| 21 | rate_limit_retries=1 | observe | inspect(component=bank) | Check bank auth config | bank: / server_time: 2026-09-21T14:13:20Z / credential.id: cred-3925 / credential.expires_at: 2026-09-17T18:3… | — |
| 23 | rate_limit_retries=1 | act [ok] | run_task(component=bank, task=rotate_credential) | Refresh expired bank credentials | rotate_credential: issued cred-07c2, expires 2026-10-21T14:13:20Z | — |
| 25 | rate_limit_retries=1 | act [ok] | run_settlement(mode=resume) | Retry after rotating bank credentials | run_settlement(resume): sent 8 payouts this run (#1-#8). Stopped at payout #9 (PO-1009): 429 Too Many Request… | new_failure_exposed |
| 27 | rate_limit_retries=1 | observe | inspect(component=settlement) | Check settlement config for rate limit settings | settlement: / checkpoint: 8 / payouts_sent: 8 / last_run: last run stopped (429) | — |
| 29 | rate_limit_retries=1 | act [rejected] | restart(component=settlement) | Restart settlement to reset rate limit handling | rejected: settlement is a batch job, not a restartable service; use run_settlement | — |
| 31 | rate_limit_retries=1 | replan | plan v3 <- triggered by [25] | — | +3/-4 steps; reason: Rate limit causing batch stop; need to lower concurrency | — |
| 33 | rate_limit_retries=1 | act [ok] | set_config(component=bank, key=max_concurrency, value=1) | Reduce concurrency to avoid rate limit | applied: bank.max_concurrency = 1 | — |
| 35 | rate_limit_retries=1 | act [ok] | run_settlement(mode=resume) | Retry settlement after lowering concurrency | run_settlement(resume): sent 12 payouts this run (#9-#20). Run complete. Total sent: 20/20. | — |
| 37 | rate_limit_retries=1 | observe | check_pipeline() | Confirm all payouts settled and components healthy | Components: / ledger: up / worker: running (queue depth: 0) / bank: up / settlement: last run complete / Payo… | — |
| 41 | rate_limit_retries=2, nudges=1 | verify [pass] | submit_incident_report | — | V1✓ V2✓ V3✓ | — |
| 42 | — | final | VERIFIED | — | goal verified | — |


## oneshot · hero · `oneshot-hero-s323-r1-20261010T125814820721`

- Source: `runs/oneshot-hero-s323-r1-20261010T125814820721.jsonl` (14 events; complete)
- Arm: oneshot — source: GOAL.eval.arm; model: `groq:openai/gpt-oss-120b`; faults: F6, F1, F7
- Reasons in the timeline: scripted: fixed strings in baselines/oneshot.py; the LLM produced only the action list

**Measured**

- Final: **GOAL_NOT_MET** — executed 3 listed actions blindly (0 malformed)
- Goal met: False; duplicate payouts: 0; faults active at end: F7 *(evaluation-only state, read after the run)*
- Payouts last shown in the log: 8/20
- Actions: 3 (3 ok, 0 refused, 0 rejected)
- Verifier: n/a (arm does not submit a report)
- LLM: 1 successful calls, 0 failed attempts; tokens 621 in + 154 out = 775; LLM latency 0.95 s
- Errors: 0 rate-limit retries, 0 other failed LLM attempts, 0 nudges; wall-clock 1.02 s

**Derived**

- Action validity: 1.00
- Component inspected before acting on it: 2/2 (weak evidence: says nothing about whether the target was right)
- Failure responses: 1 failure events; replanning n/a (arm does not plan)
- Repeated rejected actions: none
- All faults cleared *(evaluation-only)*: never — still active at end: F7
- Time outside successful LLM calls: 0.07 s; tokens per LLM call: 775.0

**Report diagnostics** *(descriptive; not SPEC §9 metrics; verifier pass/fail unchanged; no-effect annotations are evaluation-only, read after the run)*

- n/a — oneshot arm does not submit an incident report

**Unavailable / not applicable**

- plans_and_replanning: oneshot arm does not plan
- verifier: oneshot arm does not submit an incident report

Timeline (`errors before` = folded ERROR events; `eval flags` = evaluation-only):

| seq | errors before | stage | event | scripted reason | environment response | eval flags |
|---|---|---|---|---|---|---|
| 1 | — | goal | model groq:openai/gpt-oss-120b | — | — | — |
| 2 | — | observe | check_pipeline() | t0 snapshot: overall status. | Components: / ledger: up / worker: stopped (queue depth: 37) / bank: up / settlement: idle / Payouts sent: 0/… | — |
| 3 | — | observe | inspect(component=ledger) | t0 snapshot: inspect ledger. | ledger: / up: true / disk_pct: 39 / conn_used: 5 / conn_max: 20 / records: 0 | — |
| 4 | — | observe | inspect(component=worker) | t0 snapshot: inspect worker. | worker: / running: false / queue_depth: 37 | — |
| 5 | — | observe | inspect(component=bank) | t0 snapshot: inspect bank. | bank: / server_time: 2026-09-21T14:13:20Z / credential.id: cred-3925 / credential.expires_at: 2026-09-17T18:3… | — |
| 6 | — | observe | inspect(component=settlement) | t0 snapshot: inspect settlement. | settlement: / checkpoint: 0 / payouts_sent: 0 / last_run: none | — |
| 7 | — | observe | read_logs(component=ledger, n=30) | t0 snapshot: logs of ledger. | [t=0000] INFO ledger started | — |
| 8 | — | observe | read_logs(component=worker, n=30) | t0 snapshot: logs of worker. | [t=0000] INFO worker started / [t=0000] WARN worker process exited unexpectedly | — |
| 9 | — | observe | read_logs(component=bank, n=30) | t0 snapshot: logs of bank. | [t=0000] INFO gateway connected | — |
| 10 | — | observe | read_logs(component=settlement, n=30) | t0 snapshot: logs of settlement. | [t=0000] INFO batch of 20 payouts loaded | — |
| 11 | — | act [ok] | run_task(component=bank, task=rotate_credential) | One-shot action 1 of 3. | rotate_credential: issued cred-07c2, expires 2026-10-21T14:13:20Z | — |
| 12 | — | act [ok] | restart(component=worker) | One-shot action 2 of 3. | worker restarted: running; queue depth now 0 | — |
| 13 | — | act [ok] | run_settlement(mode=full) | One-shot action 3 of 3. | run_settlement(full): sent 8 payouts this run (#1-#8). Stopped at payout #9 (PO-1009): 429 Too Many Requests … | new_failure_exposed |
| 14 | — | final | GOAL_NOT_MET | — | executed 3 listed actions blindly (0 malformed) | — |


## runbook · hero · `runbook-hero-s323-r1-20261010T123930379786`

- Source: `runs/runbook-hero-s323-r1-20261010T123930379786.jsonl` (19 events; complete)
- Arm: runbook — source: GOAL.eval.arm; model: `none`; faults: F6, F1, F7
- Reasons in the timeline: scripted: fixed strings in baselines/runbook.py (no LLM)

**Measured**

- Final: **GOAL_MET** — goal confirmed by check_pipeline
- Goal met: True; duplicate payouts: 0; faults active at end: none *(evaluation-only state, read after the run)*
- Payouts last shown in the log: 20/20
- Actions: 6 (6 ok, 0 refused, 0 rejected)
- Verifier: n/a (arm does not submit a report)
- LLM: none (runbook makes no LLM calls)
- Errors: 0 rate-limit retries, 0 other failed LLM attempts, 0 nudges; wall-clock 0.0 s

**Derived**

- Action validity: 1.00
- Component inspected before acting on it: 3/3 (weak evidence: says nothing about whether the target was right)
- Failure responses: 2 failure events; replanning n/a (arm does not plan)
- Repeated rejected actions: none
- All faults cleared *(evaluation-only)*: at #14 by `set_config(component=bank, key=max_concurrency, value=5)`; afterwards settlement: #17; check_pipeline: #15, #18 (4 steps after)
- Time outside successful LLM calls: n/a; tokens per LLM call: n/a

**Report diagnostics** *(descriptive; not SPEC §9 metrics; verifier pass/fail unchanged; no-effect annotations are evaluation-only, read after the run)*

- n/a — runbook arm does not submit an incident report

`set_config` grounding (key / value seen in an earlier observation; `—` = value too short to be evidence):

| seq | component | key | value | outcome | key_seen_before | value_seen_before |
|---|---|---|---|---|---|---|
| 14 | bank | max_concurrency | 5 | ok | True | — |


**Unavailable / not applicable**

- plans_and_replanning: runbook arm does not plan
- verifier: runbook arm does not submit an incident report
- llm_tokens_latency: not applicable: runbook makes no LLM calls (0 calls logged)

Timeline (`errors before` = folded ERROR events; `eval flags` = evaluation-only):

| seq | errors before | stage | event | scripted reason | environment response | eval flags |
|---|---|---|---|---|---|---|
| 1 | — | goal | model none | — | — | — |
| 2 | — | observe | check_pipeline() | Find the first failing stage. | Components: / ledger: up / worker: stopped (queue depth: 37) / bank: up / settlement: idle / Payouts sent: 0/… | — |
| 3 | — | observe | inspect(component=worker) | Check whether the worker is running. | worker: / running: false / queue_depth: 37 | — |
| 4 | — | act [ok] | restart(component=worker) | Worker is stopped; restart it. | worker restarted: running; queue depth now 0 | — |
| 5 | — | observe | check_pipeline() | Find the first failing stage. | Components: / ledger: up / worker: running (queue depth: 0) / bank: up / settlement: idle / Payouts sent: 0/2… | — |
| 6 | — | observe | get_batch_status() | Check progress and checkpoint before settling. | Batch: 0 sent, 20 pending / Checkpoint: next payout to send is payout #1 (PO-1001) / Payouts sent more than o… | — |
| 7 | — | act [ok] | run_settlement(mode=full) | Settle remaining payouts. | run_settlement(full): sent 0 payouts this run. Stopped at payout #1 (PO-1001): 401 Unauthorized. Total sent: … | new_failure_exposed, no_effect |
| 8 | — | observe | read_logs(component=bank, n=10) | Settlement stopped on authentication; read bank logs. | [t=0000] INFO gateway connected / [t=0002] ERROR 401 Unauthorized (payout PO-1001) | — |
| 9 | — | observe | inspect(component=bank) | Disambiguate authentication failure causes from bank config. | bank: / server_time: 2026-09-21T14:13:20Z / credential.id: cred-3925 / credential.expires_at: 2026-09-17T18:3… | — |
| 10 | — | act [ok] | run_task(component=bank, task=rotate_credential) | Credential is expired; rotate it. | rotate_credential: issued cred-07c2, expires 2026-10-21T14:13:20Z | — |
| 11 | — | observe | check_pipeline() | Find the first failing stage. | Components: / ledger: up / worker: running (queue depth: 0) / bank: up / settlement: last run stopped (401) /… | — |
| 12 | — | observe | get_batch_status() | Check progress and checkpoint before settling. | Batch: 0 sent, 20 pending / Checkpoint: next payout to send is payout #1 (PO-1001) / Payouts sent more than o… | — |
| 13 | — | act [ok] | run_settlement(mode=full) | Settle remaining payouts. | run_settlement(full): sent 8 payouts this run (#1-#8). Stopped at payout #9 (PO-1009): 429 Too Many Requests … | new_failure_exposed |
| 14 | — | act [ok] | set_config(component=bank, key=max_concurrency, value=5) | Rate limit reported by bank; keep concurrency within it. | applied: bank.max_concurrency = 5 | — |
| 15 | — | observe | check_pipeline() | Find the first failing stage. | Components: / ledger: up / worker: running (queue depth: 0) / bank: up / settlement: last run stopped (429) /… | — |
| 16 | — | observe | get_batch_status() | Check progress and checkpoint before settling. | Batch: 8 sent, 12 pending / Checkpoint: next payout to send is payout #9 (PO-1009) / Payouts sent more than o… | — |
| 17 | — | act [ok] | run_settlement(mode=resume) | Settle remaining payouts. | run_settlement(resume): sent 12 payouts this run (#9-#20). Run complete. Total sent: 20/20. | — |
| 18 | — | observe | check_pipeline() | Find the first failing stage. | Components: / ledger: up / worker: running (queue depth: 0) / bank: up / settlement: last run complete / Payo… | — |
| 19 | — | final | GOAL_MET | — | goal confirmed by check_pipeline | — |


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
