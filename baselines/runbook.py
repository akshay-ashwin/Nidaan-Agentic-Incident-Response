"""Strong deterministic runbook baseline (SPEC §8). No LLM calls.

Loop (max 20): check_pipeline -> first failing stage -> read_logs + inspect -> ordered rules -> act.
Written only from the development fault set. It disambiguates with `inspect` fields, parses the 429
rate-limit header, always checks batch status before settling, and resumes when progress exists.
"""
from __future__ import annotations

import re

from baselines.common import NO_LLM, LoggedTools, finish_run, start_run
from nidaan.logger import RunLogger
from settlesim.sim import SettleSim

MAX_ITERATIONS = 20


def _field(text: str, name: str) -> str | None:
    m = re.search(rf"^\s*{re.escape(name)}:\s*(.+)$", text, re.M)
    return m.group(1).strip() if m else None


def _goal_met(text: str) -> bool:
    return "FAIL" not in text and text.count("PASS") == 3


def _fix_ledger_space(t: LoggedTools) -> None:
    led = t.call("inspect", "Confirm ledger disk usage before freeing space.", component="ledger").text
    if int(_field(led, "disk_pct") or 0) >= 95:
        t.call("run_task", "Disk is full; rotate logs to free space.", component="ledger", task="rotate_logs")


def _fix_worker_queue(t: LoggedTools) -> None:
    w = t.call("inspect", "Check whether the worker is running.", component="worker").text
    if _field(w, "running") == "false":
        t.call("restart", "Worker is stopped; restart it.", component="worker")
        return
    logs = t.call("read_logs", "Worker is running but the queue is not draining; read its errors.",
                  component="worker", n=10).text
    if "no space left" in logs or "not accepting writes" in logs:
        _fix_ledger_space(t)


def _fix_auth(t: LoggedTools) -> None:
    t.call("read_logs", "Settlement stopped on authentication; read bank logs.", component="bank", n=10)
    bank = t.call("inspect", "Disambiguate authentication failure causes from bank config.", component="bank").text
    expires, now = _field(bank, "credential.expires_at"), _field(bank, "server_time")
    active, in_use = _field(bank, "vault_active_key"), _field(bank, "key_in_use")
    if expires and now and expires < now:  # ISO-8601 strings compare lexicographically
        t.call("run_task", "Credential is expired; rotate it.", component="bank", task="rotate_credential")
    if active and in_use and active != in_use:
        t.call("set_config", "Signing key differs from the vault's active key; set it from the vault value.",
               component="bank", key="key_in_use", value=active)


def _fix_rate_limit(t: LoggedTools, result: str) -> None:
    m = re.search(r"X-RateLimit-Limit:\s*(\d+)", result)
    if m:
        t.call("set_config", "Rate limit reported by bank; keep concurrency within it.",
               component="bank", key="max_concurrency", value=m.group(1))


def run_runbook(sim: SettleSim, logger: RunLogger, scenario_info: dict) -> dict:
    t = LoggedTools(sim, logger)
    start_run(logger, "runbook", scenario_info)
    reason = "iteration limit reached"
    for _ in range(MAX_ITERATIONS):
        pipe = t.call("check_pipeline", "Find the first failing stage.").text
        if _goal_met(pipe):
            reason = "goal confirmed by check_pipeline"
            break
        queue = int(re.search(r"queue depth:\s*(\d+)", pipe).group(1))
        stopped = "worker: stopped" in pipe
        if stopped or queue > 0:
            _fix_worker_queue(t)
            continue
        batch = t.call("get_batch_status", "Check progress and checkpoint before settling.").text
        sent = int(re.search(r"Batch:\s*(\d+) sent", batch).group(1))
        res = t.call("run_settlement", "Settle remaining payouts.",
                     mode="resume" if sent > 0 else "full").text
        if "401" in res:
            _fix_auth(t)
        elif "429" in res:
            _fix_rate_limit(t, res)
        elif "ledger write failed" in res:
            _fix_ledger_space(t)
    finish_run(logger, sim, NO_LLM, reason)
    return {"reason": reason}
