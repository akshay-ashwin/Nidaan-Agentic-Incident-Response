"""3-node LangGraph: agent (LLM decides) -> tools (SettleSim acts) -> verifier (deterministic checks).

Limits (SPEC §1): 30 LLM steps, 2 nudges, 2 verifier retries; values live in config.py.
Only structured events are logged; free-form model text is never stored.
"""
from __future__ import annotations

import time
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

import config
from nidaan import llm_errors as E
from nidaan.llm import make_chat_model
from nidaan.logger import RunLogger
from nidaan.prompt import GOAL, NUDGE, SYSTEM_PROMPT
from nidaan.tools import ToolExecutor, build_langchain_tools
from nidaan.verifier import verify
from settlesim.sim import SettleSim
from settlesim.tools import SettleSimTools

_sleep = time.sleep  # module-level so tests can replace it; never called at import


def redact(msg: str) -> str:
    """Remove credentials and account identifiers that provider error messages may contain."""
    return E.redact(msg)


def is_transient(msg: str) -> bool:
    """Retry-worthy errors: per-minute rate limits and temporary provider failures (not daily quotas)."""
    return E.classify(msg).kind in (E.RATE_LIMIT, E.TRANSIENT)


def retry_delay_s(msg: str, attempt: int) -> float | None:
    """Seconds to wait before retry number `attempt`, or None to give up (used by the one-shot baseline).
    Provider guidance is respected (plus a margin); otherwise jittered exponential backoff. Delays longer than
    LLM_MAX_RETRY_DELAY_S (e.g. a daily quota) are not waited out. See nidaan.llm_errors.next_delay_s."""
    return E.next_delay_s(E.classify(msg), attempt, attempt, 0.0)


class State(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    llm_steps: int
    nudges: int
    retries: int
    status: str | None  # None while running; VERIFIED | FAILED when ended
    reason: str | None


def make_llm():
    return make_chat_model().bind_tools(build_langchain_tools())


class NidaanAgent:
    def __init__(self, sim: SettleSim, logger: RunLogger, llm=None, scenario_info: dict | None = None):
        self.sim, self.logger = sim, logger
        self.llm = llm or make_llm()
        self.executor = ToolExecutor(SettleSimTools(sim), logger)
        self.scenario_info = scenario_info or {}
        self.metrics = {"llm_calls": 0, "llm_errors": 0, "input_tokens": 0, "output_tokens": 0,
                        "total_tokens": 0, "tokens_available": True, "latency_s": 0.0,
                        "rate_limit_retries": 0, "retry_wait_s": 0.0, "paced_wait_s": 0.0}
        self.llm_failure: E.LLMError | None = None  # set when the run stops on an LLM error
        self._pacer = E.TokenPacer(config.LLM_TPM_LIMIT)
        self._next_estimate = 0  # tokens the next request is expected to use (from the previous call)
        self.graph = self._build()

    # ---- graph ---------------------------------------------------------
    def _build(self):
        g = StateGraph(State)
        g.add_node("agent", self._agent)
        g.add_node("tools", self._tools)
        g.add_node("verifier", self._verifier)
        g.set_entry_point("agent")
        g.add_conditional_edges("agent", self._after_agent, {"tools": "tools", "agent": "agent", END: END})
        g.add_conditional_edges("tools", lambda s: "verifier" if self.executor.pending_report else "agent",
                                {"verifier": "verifier", "agent": "agent"})
        g.add_conditional_edges("verifier", lambda s: END if s["status"] else "agent",
                                {"agent": "agent", END: END})
        return g.compile()

    @staticmethod
    def _after_agent(s: State):
        if s["status"]:
            return END
        last = s["messages"][-1]
        return "tools" if isinstance(last, AIMessage) and last.tool_calls else "agent"

    # ---- node: agent ---------------------------------------------------
    def _invoke(self, messages):
        """One model call with the application's retry policy (the only retry layer: SDK retries are off).
        Returns (response, latency_s, None) or (None, 0.0, LLMError) when the policy says stop."""
        pace = self._pacer.wait_s(self._next_estimate)
        if pace > 0:  # stay under the provider's tokens-per-minute window instead of provoking a 429
            self.metrics["paced_wait_s"] += pace
            _sleep(pace)
        rate_retries = other_retries = 0
        waited = 0.0
        while True:  # bounded: next_delay_s returns None once a retry count or the wait budget is spent
            attempt = rate_retries + other_retries + 1
            t0 = time.perf_counter()
            try:
                resp = self.llm.invoke(messages)
                return resp, time.perf_counter() - t0, None
            except Exception as e:  # noqa: BLE001 - classified by message; redacted before logging
                err = E.classify(f"{type(e).__name__}: {str(e)[:1500]}")
                self.metrics["llm_errors"] += 1
                delay = E.next_delay_s(err, rate_retries, other_retries, waited)
                if attempt > config.LLM_RETRIES + config.LLM_RATE_LIMIT_RETRIES:  # belt and braces
                    delay = None
                self.logger.log("ERROR", error=f"LLM call failed (attempt {attempt}): {err.message}",
                                model=config.MODEL_ID, error_kind=err.kind, attempt=attempt,
                                retry_in_s=round(delay, 2) if delay is not None else None)
                if delay is None:
                    return None, 0.0, err
                if err.kind == E.RATE_LIMIT:
                    rate_retries += 1
                    self.metrics["rate_limit_retries"] += 1
                else:
                    other_retries += 1
                waited += delay
                self.metrics["retry_wait_s"] += delay
                _sleep(delay)

    def _agent(self, s: State):
        if s["llm_steps"] >= config.MAX_LLM_STEPS:
            return {"status": "FAILED", "reason": f"step limit ({config.MAX_LLM_STEPS} LLM steps) reached"}
        resp, latency, err = self._invoke(s["messages"])
        if resp is None:
            # The run stops here. The simulator keeps its real state; no fresh agent resumes the incident.
            self.llm_failure = err
            return {"status": "FAILED", "reason": f"LLM error: {err.message}"}
        m = self.metrics
        m["llm_calls"] += 1
        m["latency_s"] += latency
        usage = getattr(resp, "usage_metadata", None)
        if usage:
            m["input_tokens"] += usage.get("input_tokens", 0)
            m["output_tokens"] += usage.get("output_tokens", 0)
            m["total_tokens"] += usage.get("total_tokens", 0)
            self._pacer.record(usage.get("total_tokens"))
            # The next request resends this context plus the reply and tool results; 200 tokens covers those.
            self._next_estimate = (usage.get("input_tokens") or 0) + (usage.get("output_tokens") or 0) + 200
        else:
            m["tokens_available"] = False
        self._meta = {"llm_call": m["llm_calls"], "latency_ms": round(latency * 1000),
                      "tokens": (dict(input=usage.get("input_tokens"), output=usage.get("output_tokens"),
                                      total=usage.get("total_tokens")) if usage else "unavailable"),
                      "model": config.MODEL_ID}
        out = {"messages": [resp], "llm_steps": s["llm_steps"] + 1}
        if not resp.tool_calls:
            if s["nudges"] >= config.MAX_NUDGES:
                self.logger.log("ERROR", error="agent replied without a tool call; nudges exhausted",
                                **self._meta)
                return {**out, "status": "FAILED", "reason": "no tool call after nudges"}
            self.logger.log("ERROR", error="agent replied without a tool call; nudged", **self._meta)
            out["messages"] = [resp, HumanMessage(NUDGE)]
            out["nudges"] = s["nudges"] + 1
        return out

    # ---- node: tools ---------------------------------------------------
    def _tools(self, s: State):
        ai: AIMessage = s["messages"][-1]
        replies, meta, submitted = [], dict(self._meta), False
        for call in ai.tool_calls:
            if submitted:  # a report ends the turn; later calls in the same response are not run
                replies.append(ToolMessage("not executed: report was submitted", tool_call_id=call["id"],
                                           name=call["name"]))
                continue
            text = self.executor.execute(call["name"], call["args"], meta)
            meta = {"llm_call": meta["llm_call"]}  # latency/tokens belong to the first event of a call
            if text is None:
                submitted = True
                self._report_call = call
            else:
                replies.append(ToolMessage(text, tool_call_id=call["id"], name=call["name"]))
        return {"messages": replies}

    # ---- node: verifier ------------------------------------------------
    def _verifier(self, s: State):
        report, call = self.executor.pending_report, self._report_call
        self.executor.pending_report = None
        res = verify(report, self.logger.events, self.sim)
        retries_left = config.MAX_VERIFIER_RETRIES - s["retries"]
        ev = self.logger.log("VERIFY", args=report, result=res.message(),
                             outcome="pass" if res.passed else "fail", checks=res.checks,
                             retries_left=retries_left if not res.passed else None)
        if res.passed:
            reply = f"[{ev['seq']}] {res.message()}"
            return {"messages": [ToolMessage(reply, tool_call_id=call["id"], name=call["name"])],
                    "status": "VERIFIED"}
        if retries_left <= 0:
            reply = f"[{ev['seq']}] {res.message()}. No retries left."
            return {"messages": [ToolMessage(reply, tool_call_id=call["id"], name=call["name"])],
                    "status": "FAILED", "reason": "verification failed; no retries left"}
        reply = f"[{ev['seq']}] {res.message()}. You may continue repairing ({retries_left} retries left)."
        return {"messages": [ToolMessage(reply, tool_call_id=call["id"], name=call["name"])],
                "retries": s["retries"] + 1}

    # ---- run -----------------------------------------------------------
    def run(self) -> dict:
        self.logger.log("GOAL", goal=GOAL, model=config.MODEL_ID, eval=self.scenario_info or None)
        init: State = {"messages": [SystemMessage(SYSTEM_PROMPT), HumanMessage(GOAL)], "llm_steps": 0,
                       "nudges": 0, "retries": 0, "status": None, "reason": None}
        final = self.graph.invoke(init, {"recursion_limit": 200})
        status = final["status"] or "FAILED"
        m = self.metrics
        self.logger.log(
            "FINAL", outcome=status, result=final.get("reason") or "goal verified",
            metrics={"llm_calls": m["llm_calls"], "llm_errors": m["llm_errors"],
                     "input_tokens": m["input_tokens"] if m["tokens_available"] else "unavailable",
                     "output_tokens": m["output_tokens"] if m["tokens_available"] else "unavailable",
                     "total_tokens": m["total_tokens"] if m["tokens_available"] else "unavailable",
                     "latency_s": round(m["latency_s"], 2),
                     "rate_limit_retries": m["rate_limit_retries"], "retry_wait_s": round(m["retry_wait_s"], 1),
                     "paced_wait_s": round(m["paced_wait_s"], 1)},
            error_kind=self.llm_failure.kind if self.llm_failure else None,
            eval={"goal_met": self.sim.goal_met(), "duplicates": len(self.sim.duplicates()),
                  "faults_active": self.sim.active_faults()})
        self.logger.close()
        return {"status": status, "reason": final.get("reason"), "metrics": m, "log_path": self.logger.path}
