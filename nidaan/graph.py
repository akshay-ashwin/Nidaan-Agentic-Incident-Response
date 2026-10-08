"""3-node LangGraph: agent (LLM decides) -> tools (SettleSim acts) -> verifier (deterministic checks).

Limits (SPEC §1): 30 LLM steps, 2 nudges, 2 verifier retries; values live in config.py.
Only structured events are logged; free-form model text is never stored.
"""
from __future__ import annotations

import re
import time
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

import config
from nidaan.logger import RunLogger
from nidaan.prompt import GOAL, NUDGE, SYSTEM_PROMPT
from nidaan.tools import ToolExecutor, build_langchain_tools
from nidaan.verifier import verify
from settlesim.sim import SettleSim
from settlesim.tools import SettleSimTools

TRANSIENT = ("503", "429", "UNAVAILABLE", "RESOURCE_EXHAUSTED", "DEADLINE", "timed out", "timeout")


def is_transient(msg: str) -> bool:
    """Retry-worthy errors. A per-day quota will not clear within the backoff window, so it is not."""
    return any(t in msg for t in TRANSIENT) and "PerDay" not in msg


RETRY_DELAY_RE = re.compile(r"retryDelay['\"]?\s*:\s*['\"]?([\d.]+)s|retry in ([\d.]+)s")


def retry_delay_s(msg: str, attempt: int) -> float | None:
    """Seconds to wait before retrying, or None to give up.
    A server-provided retry delay is respected (plus 1s margin); otherwise exponential backoff.
    A server delay longer than LLM_MAX_RETRY_DELAY_S (e.g. a daily quota) is not waited out."""
    if not is_transient(msg):
        return None
    m = RETRY_DELAY_RE.search(msg)
    if m:
        delay = float(m.group(1) or m.group(2)) + 1
        return delay if delay <= config.LLM_MAX_RETRY_DELAY_S else None
    return config.LLM_BACKOFF_BASE_S * 2 ** attempt


class State(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    llm_steps: int
    nudges: int
    retries: int
    status: str | None  # None while running; VERIFIED | FAILED when ended
    reason: str | None


def make_llm() -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(model=config.MODEL_NAME, temperature=config.TEMPERATURE,
                                  thinking_level=config.THINKING_LEVEL, max_retries=0,
                                  timeout=config.LLM_TIMEOUT_S).bind_tools(build_langchain_tools())


class NidaanAgent:
    def __init__(self, sim: SettleSim, logger: RunLogger, llm=None, scenario_info: dict | None = None):
        self.sim, self.logger = sim, logger
        self.llm = llm or make_llm()
        self.executor = ToolExecutor(SettleSimTools(sim), logger)
        self.scenario_info = scenario_info or {}
        self.metrics = {"llm_calls": 0, "llm_errors": 0, "input_tokens": 0, "output_tokens": 0,
                        "total_tokens": 0, "tokens_available": True, "latency_s": 0.0}
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
        for attempt in range(config.LLM_RETRIES + 1):
            t0 = time.perf_counter()
            try:
                resp = self.llm.invoke(messages)
                return resp, time.perf_counter() - t0, None
            except Exception as e:  # noqa: BLE001 - classify by message, never log secrets
                msg = f"{type(e).__name__}: {str(e)[:1500]}"
                self.metrics["llm_errors"] += 1
                self.logger.log("ERROR", error=f"LLM call failed (attempt {attempt + 1}): {msg}",
                                model=config.MODEL_NAME)
                delay = retry_delay_s(msg, attempt)
                if attempt == config.LLM_RETRIES or delay is None:
                    return None, 0.0, msg
                time.sleep(delay)
        return None, 0.0, "exhausted"

    def _agent(self, s: State):
        if s["llm_steps"] >= config.MAX_LLM_STEPS:
            return {"status": "FAILED", "reason": f"step limit ({config.MAX_LLM_STEPS} LLM steps) reached"}
        resp, latency, err = self._invoke(s["messages"])
        if resp is None:
            return {"status": "FAILED", "reason": f"LLM error: {err}"}
        m = self.metrics
        m["llm_calls"] += 1
        m["latency_s"] += latency
        usage = getattr(resp, "usage_metadata", None)
        if usage:
            m["input_tokens"] += usage.get("input_tokens", 0)
            m["output_tokens"] += usage.get("output_tokens", 0)
            m["total_tokens"] += usage.get("total_tokens", 0)
        else:
            m["tokens_available"] = False
        self._meta = {"llm_call": m["llm_calls"], "latency_ms": round(latency * 1000),
                      "tokens": (dict(input=usage.get("input_tokens"), output=usage.get("output_tokens"),
                                      total=usage.get("total_tokens")) if usage else "unavailable"),
                      "model": config.MODEL_NAME}
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
        self.logger.log("GOAL", goal=GOAL, model=config.MODEL_NAME, eval=self.scenario_info or None)
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
                     "latency_s": round(m["latency_s"], 2)},
            eval={"goal_met": self.sim.goal_met(), "duplicates": len(self.sim.duplicates()),
                  "faults_active": self.sim.active_faults()})
        self.logger.close()
        return {"status": status, "reason": final.get("reason"), "metrics": m, "log_path": self.logger.path}
