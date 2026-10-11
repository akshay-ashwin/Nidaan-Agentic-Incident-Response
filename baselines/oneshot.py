"""One-shot LLM baseline (SPEC §8): same model, one generous t0 snapshot, one blind action list.

Snapshot = check_pipeline + inspect of all components + all logs. The LLM is called once and
outputs an ordered action list, which is executed blindly (no observation or replanning between
actions); then the goal is checked. Metrics (calls, tokens, latency) are measured.
"""
from __future__ import annotations

import json
import re
import time

import config
from baselines.common import LoggedTools, finish_run, start_run
from nidaan.graph import redact, retry_delay_s
from nidaan.llm import make_chat_model
from nidaan.logger import RunLogger
from nidaan.tools import RUN_TASKS
from settlesim.sim import COMPONENTS, SettleSim

ALLOWED_TOOLS = ("restart", "set_config", "run_task", "run_settlement")

SYSTEM_PROMPT = f"""You are an incident-response assistant for a small payment-settlement system. \
You are given one snapshot of the system. Output an ordered list of actions that resolves the incident. \
The actions will be executed exactly as listed, in order, with no further observation and no changes. \
Goal: every payout in the batch is settled exactly once and all components are healthy.

Action formats (JSON objects):
- {{"tool": "restart", "args": {{"component": C}}}}
- {{"tool": "set_config", "args": {{"component": C, "key": K, "value": V}}}}
- {{"tool": "run_task", "args": {{"component": C, "task": T}}}}  with T one of: {", ".join(RUN_TASKS)}
- {{"tool": "run_settlement", "args": {{"mode": "resume" or "full"}}}}  ('resume' continues from the batch checkpoint; 'full' restarts from the first payout)
Components C: {", ".join(COMPONENTS)}.
Take configuration values from the snapshot; do not guess them. Prefer minimal, safe actions.
Output only a JSON array of action objects, with no other text."""


def build_snapshot(t: LoggedTools) -> str:
    parts = [t.call("check_pipeline", "t0 snapshot: overall status.").text]
    for c in COMPONENTS:
        parts.append(t.call("inspect", f"t0 snapshot: inspect {c}.", component=c).text)
    for c in COMPONENTS:
        parts.append(f"--- logs: {c} ---\n" + t.call("read_logs", f"t0 snapshot: logs of {c}.",
                                                      component=c).text)
    return "\n\n".join(parts)


def parse_action_list(text: str) -> list:
    """Lenient JSON-array extraction. Returns a list (items may be malformed); [] if none found."""
    m = re.search(r"\[.*\]", text, re.S)
    if not m:
        return []
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def execute_actions(t: LoggedTools, actions: list) -> int:
    """Execute blindly in order. Malformed actions are logged as rejected ACT events. Returns #malformed."""
    bad = 0
    for i, a in enumerate(actions, 1):
        why = f"One-shot action {i} of {len(actions)}."
        ok = isinstance(a, dict) and a.get("tool") in ALLOWED_TOOLS and isinstance(a.get("args"), dict)
        if ok:
            try:
                t.call(a["tool"], why, **a["args"])
                continue
            except TypeError:
                pass
        bad += 1
        t.logger.log("ACT", tool=str(a.get("tool")) if isinstance(a, dict) else "malformed",
                     args={}, why=why, result="rejected: malformed action", outcome="rejected")
    return bad


def make_llm():
    return make_chat_model()  # same configured provider and model as Nidaan


def _invoke(llm, messages):
    err = None
    for attempt in range(config.LLM_RETRIES + 1):
        t0 = time.perf_counter()
        try:
            return llm.invoke(messages), time.perf_counter() - t0, 1 + attempt, None
        except Exception as e:  # noqa: BLE001
            err = redact(f"{type(e).__name__}: {str(e)[:500]}")
            delay = retry_delay_s(err, attempt)
            if attempt == config.LLM_RETRIES or delay is None:
                break
            time.sleep(delay)
    return None, 0.0, attempt + 1, err


def run_oneshot(sim: SettleSim, logger: RunLogger, scenario_info: dict, llm=None) -> dict:
    """Requires a live LLM call (configured provider) unless an `llm` is supplied."""
    t = LoggedTools(sim, logger)
    start_run(logger, "oneshot", scenario_info, config.MODEL_ID)
    snapshot = build_snapshot(t)
    llm = llm or make_llm()
    resp, latency, attempts, err = _invoke(llm, [("system", SYSTEM_PROMPT), ("human", snapshot)])
    m = {"llm_calls": 0, "llm_errors": attempts - (1 if resp else 0), "input_tokens": "unavailable",
         "output_tokens": "unavailable", "total_tokens": "unavailable", "latency_s": round(latency, 2)}
    if resp is None:
        logger.log("ERROR", error=f"LLM call failed: {err}", model=config.MODEL_ID)
        finish_run(logger, sim, m, f"LLM error: {err}")
        return {"reason": "llm error"}
    m["llm_calls"] = 1
    u = getattr(resp, "usage_metadata", None)
    if u:
        m.update(input_tokens=u.get("input_tokens"), output_tokens=u.get("output_tokens"),
                 total_tokens=u.get("total_tokens"))
    actions = parse_action_list(resp.text)
    bad = execute_actions(t, actions)
    finish_run(logger, sim, m, f"executed {len(actions)} listed actions blindly ({bad} malformed)")
    return {"reason": "executed", "n_actions": len(actions)}
