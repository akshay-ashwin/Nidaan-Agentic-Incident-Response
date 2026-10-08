"""Agent-facing tool schemas and the executor that dispatches tool calls.

The executor is deterministic and LLM-free: it gates calls on plan v1, validates
plans, calls the SettleSim wrappers, and writes events. Tool descriptions are
general; they name no faults, parameter values, or scenario specifics.
"""
from __future__ import annotations

from typing import Literal, Optional

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field, ValidationError

from nidaan.logger import RunLogger
from nidaan.plan import PlanManager
from settlesim.tools import SettleSimTools

Component = Literal["ledger", "worker", "bank", "settlement"]
# SPEC §3: run_task accepts exactly these four tasks (no distractors). A static enum keeps the tool
# schema identical for the whole project; which task applies to which problem is not stated here.
RUN_TASKS = ("rotate_credential", "sync_clock", "rotate_logs", "kill_idle_connections")
Task = Literal[RUN_TASKS]
WHY = Field(description="One sentence (<= 25 words) saying why you are making this call.")


class CheckPipelineArgs(BaseModel):
    why: str = WHY


class InspectArgs(BaseModel):
    component: Component
    why: str = WHY


class ReadLogsArgs(BaseModel):
    component: Component
    why: str = WHY
    grep: Optional[str] = Field(default=None, description="Optional case-insensitive substring filter.")
    n: int = Field(default=30, description="Number of most recent lines, at most 30.")


class GetBatchStatusArgs(BaseModel):
    why: str = WHY


class RestartArgs(BaseModel):
    component: Component
    why: str = WHY


class SetConfigArgs(BaseModel):
    component: Component
    key: str
    value: str = Field(description="New value, written as a string.")
    why: str = WHY


class RunTaskArgs(BaseModel):
    component: Component
    task: Task = Field(description="The maintenance task to run.")
    why: str = WHY


class RunSettlementArgs(BaseModel):
    mode: Literal["resume", "full"] = Field(
        description="'resume' continues from the batch checkpoint; 'full' restarts from the first payout.")
    why: str = WHY


class UpdatePlanArgs(BaseModel):
    steps: list[str] = Field(description="The complete ordered list of plan steps.")
    reason: str = Field(description="Short reason for this plan or change.")
    triggered_by: list[int] = Field(
        default_factory=list,
        description="Event numbers [N] of tool results that prompted a replan. Required for replans.")


class RootCause(BaseModel):
    component: Component
    description: str
    evidence: list[int] = Field(description="Event numbers [N] supporting this root cause.")


class SubmitReportArgs(BaseModel):
    status_claimed: Literal["resolved", "unresolved"]
    root_causes: list[RootCause]
    actions: list[int] = Field(description="Event numbers [N] of the actions you actually performed.")
    summary: str


SPECS = [
    ("update_plan", UpdatePlanArgs,
     "Record or revise your plan. A plan must exist before any observe or act call. Replans must cite "
     "triggered_by event numbers of results newer than the previous plan, and must change the steps."),
    ("check_pipeline", CheckPipelineArgs,
     "Observe component statuses, queue depth, payouts sent, and the goal invariants."),
    ("inspect", InspectArgs, "Observe the configuration and metric fields of one component."),
    ("read_logs", ReadLogsArgs, "Observe recent log lines of one component, optionally filtered."),
    ("get_batch_status", GetBatchStatusArgs,
     "Observe sent/pending payouts, the batch checkpoint, and any payout sent more than once."),
    ("restart", RestartArgs, "Act: restart a component. May be refused."),
    ("set_config", SetConfigArgs, "Act: set a configuration key on a component. May be rejected."),
    ("run_task", RunTaskArgs, "Act: run a maintenance task on a component. May have no effect."),
    ("run_settlement", RunSettlementArgs,
     "Act: run the settlement batch. May be refused or stop part-way."),
    ("submit_incident_report", SubmitReportArgs,
     "Submit the final incident report for verification. Only claim 'resolved' if the goal is confirmed."),
]


def build_langchain_tools() -> list[StructuredTool]:
    return [StructuredTool.from_function(func=lambda **kw: None, name=n, description=d, args_schema=m)
            for n, m, d in SPECS]


_ARGS = {n: m for n, m, _ in SPECS}
_SIM_TOOLS = {"check_pipeline", "inspect", "read_logs", "get_batch_status",
              "restart", "set_config", "run_task", "run_settlement"}


class ToolExecutor:
    def __init__(self, sim_tools: SettleSimTools, logger: RunLogger):
        self.sim_tools, self.logger = sim_tools, logger
        self.plans = PlanManager()
        self.pending_report: dict | None = None

    def execute(self, name: str, args: dict, meta: dict) -> str | None:
        """Run one tool call. Returns the text for the agent, or None if a report was submitted
        (the verifier node answers that call). `meta` carries llm_call/latency/tokens/model."""
        model = _ARGS.get(name)
        if model is None:
            return self._error(f"unknown tool '{name}'", meta)
        try:
            parsed = model(**args).model_dump()
        except ValidationError as e:
            msgs = "; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors())
            return self._error(f"invalid arguments for {name}: {msgs}", meta)
        if name == "update_plan":
            return self._update_plan(parsed, meta)
        if name == "submit_incident_report":
            self.pending_report = parsed
            return None
        return self._sim_call(name, parsed, meta)

    def _error(self, message: str, meta: dict) -> str:
        ev = self.logger.log("ERROR", error=message, **meta)
        return f"[{ev['seq']}] rejected: {message}"

    def _update_plan(self, a: dict, meta: dict) -> str:
        v = self.plans.validate(a["steps"], a["triggered_by"], self.logger.tool_event_seqs())
        ev = self.logger.log("PLAN", plan_version=v.version or self.plans.current_version or None,
                             steps=a["steps"], reason=a["reason"], triggered_by=a["triggered_by"],
                             diff=v.diff or None, result=v.message,
                             outcome="ok" if v.ok else "rejected", **meta)
        if v.ok:
            self.plans.commit(a["steps"], ev["seq"])
        return f"[{ev['seq']}] {v.message}"

    def _sim_call(self, name: str, a: dict, meta: dict) -> str:
        kind = "ACT" if name in ("restart", "set_config", "run_task", "run_settlement") else "OBSERVE"
        if not self.plans.has_plan():
            ev = self.logger.log(kind, tool=name, args={k: v for k, v in a.items() if k != "why"},
                                 why=a.get("why"), outcome="rejected",
                                 result="rejected: no plan yet; call update_plan first", **meta)
            return f"[{ev['seq']}] {ev['result']}"
        why = a.pop("why", "")
        res = getattr(self.sim_tools, name)(**a, why=why)
        ev = self.logger.log(kind, tool=name, args=res.args, why=why,
                             plan_version=self.plans.current_version, result=res.text,
                             outcome=res.outcome, eval=res.annotations or None, **meta)
        return f"[{ev['seq']}] {res.text}"
