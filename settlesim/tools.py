"""Thin tool wrappers over SettleSim: 4 observe + 4 act.

`text` is the only thing the agent ever sees. `annotations` is evaluation-only.
Every call requires a non-empty `why` of at most 25 words. Control tools (update_plan,
submit_incident_report) belong to the agent layer, not here.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from settlesim.sim import MAX_LOG_LINES, Result, SettleSim

OBSERVE, ACT = "OBSERVE", "ACT"
MAX_WHY_WORDS = 25


@dataclass
class ToolResult:
    tool: str
    kind: str
    args: dict
    why: str
    text: str  # agent-visible
    outcome: str  # ok | refused | rejected
    annotations: dict = field(default_factory=dict)  # evaluation-only


class SettleSimTools:
    def __init__(self, sim: SettleSim):
        self.sim = sim
        self.history: list[ToolResult] = []

    def _call(self, kind: str, tool: str, args: dict, why: str, fn) -> ToolResult:
        if not isinstance(why, str) or not why.strip():
            res = Result("rejected: 'why' is required (one short sentence, <= 25 words)", "rejected")
        elif len(why.split()) > MAX_WHY_WORDS:
            res = Result(f"rejected: 'why' must be <= {MAX_WHY_WORDS} words (got {len(why.split())})",
                         "rejected")
        else:
            res = fn()
        tr = ToolResult(tool, kind, args, why, res.text, res.outcome,
                        res.annotations if kind == ACT else {})
        self.history.append(tr)
        return tr

    # ---- OBSERVE ----
    def check_pipeline(self, why: str) -> ToolResult:
        """Show component statuses, queue depth, payouts sent, and goal invariants."""
        return self._call(OBSERVE, "check_pipeline", {}, why, self.sim.check_pipeline)

    def inspect(self, component: str, why: str) -> ToolResult:
        """Show configuration and metric fields of a component."""
        return self._call(OBSERVE, "inspect", {"component": component}, why,
                          lambda: self.sim.inspect(component))

    def read_logs(self, component: str, why: str, grep: str | None = None,
                  n: int = MAX_LOG_LINES) -> ToolResult:
        """Show recent log lines of a component, optionally filtered by substring (n <= 30)."""
        return self._call(OBSERVE, "read_logs", {"component": component, "grep": grep, "n": n}, why,
                          lambda: self.sim.read_logs(component, grep, n))

    def get_batch_status(self, why: str) -> ToolResult:
        """Show sent/pending payouts, the checkpoint, and any payout sent more than once."""
        return self._call(OBSERVE, "get_batch_status", {}, why, self.sim.get_batch_status)

    # ---- ACT ----
    def restart(self, component: str, why: str) -> ToolResult:
        """Restart a component. May be refused."""
        return self._call(ACT, "restart", {"component": component}, why,
                          lambda: self.sim.restart(component))

    def set_config(self, component: str, key: str, value, why: str) -> ToolResult:
        """Set a configuration value on a component. May be rejected."""
        return self._call(ACT, "set_config", {"component": component, "key": key, "value": value}, why,
                          lambda: self.sim.set_config(component, key, value))

    def run_task(self, component: str, task: str, why: str) -> ToolResult:
        """Run a maintenance task on a component. May have no effect."""
        return self._call(ACT, "run_task", {"component": component, "task": task}, why,
                          lambda: self.sim.run_task(component, task))

    def run_settlement(self, mode: str, why: str) -> ToolResult:
        """Run the settlement batch. mode='resume' continues from the checkpoint; 'full' restarts at payout 1."""
        return self._call(ACT, "run_settlement", {"mode": mode}, why,
                          lambda: self.sim.run_settlement(mode))
