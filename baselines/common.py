"""Shared plumbing for baseline arms: SettleSim tool calls logged in the same JSONL format as Nidaan."""
from __future__ import annotations

from nidaan.logger import RunLogger
from nidaan.prompt import GOAL
from settlesim.sim import SettleSim
from settlesim.tools import ACT, OBSERVE, SettleSimTools, ToolResult

ACT_TOOLS = ("restart", "set_config", "run_task", "run_settlement")
NO_LLM = {"llm_calls": 0, "llm_errors": 0, "input_tokens": 0, "output_tokens": 0, "total_tokens": 0,
          "latency_s": 0.0}


class LoggedTools:
    def __init__(self, sim: SettleSim, logger: RunLogger):
        self.sim, self.logger, self.tools = sim, logger, SettleSimTools(sim)

    def call(self, name: str, why: str, **args) -> ToolResult:
        res = getattr(self.tools, name)(**args, why=why)
        self.logger.log(ACT if name in ACT_TOOLS else OBSERVE, tool=name, args=res.args, why=why,
                        result=res.text, outcome=res.outcome, eval=res.annotations or None)
        return res


def start_run(logger: RunLogger, arm: str, scenario_info: dict, model: str | None = None) -> None:
    logger.log("GOAL", goal=GOAL, model=model, eval={**scenario_info, "arm": arm})


def finish_run(logger: RunLogger, sim: SettleSim, llm_metrics: dict, reason: str) -> None:
    logger.log("FINAL", outcome="GOAL_MET" if sim.goal_met() else "GOAL_NOT_MET", result=reason,
               metrics=llm_metrics,
               eval={"goal_met": sim.goal_met(), "duplicates": len(sim.duplicates()),
                     "faults_active": sim.active_faults()})
    logger.close()
