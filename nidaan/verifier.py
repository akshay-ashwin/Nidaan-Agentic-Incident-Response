"""Deterministic verifier (SPEC §5). Does not judge root-cause correctness."""
from __future__ import annotations

from dataclasses import dataclass, field

from settlesim.sim import SettleSim


@dataclass
class VerifyResult:
    passed: bool
    checks: dict = field(default_factory=dict)  # {"V1": bool, ...}
    failures: list[str] = field(default_factory=list)

    def message(self) -> str:
        if self.passed:
            return "verification PASSED"
        return "verification FAILED: " + "; ".join(self.failures)


def verify(report: dict, events: list[dict], sim: SettleSim) -> VerifyResult:
    failures, checks = [], {}

    # V1: environment goal check passes (G1-G3); a duplicate payout fails G3 and so V1.
    goals = sim.goals()
    checks["V1"] = all(goals.values())
    if not checks["V1"]:
        names = {"G1": "worker running and queue empty", "G2": "ledger up",
                 "G3": "every payout sent exactly once"}
        bad = [f"{g} ({names[g]})" for g, ok in goals.items() if not ok]
        failures.append("V1: goal check failed: " + ", ".join(bad))

    # V2: every claimed action step exists in the log and is an ACT event.
    by_seq = {e["seq"]: e for e in events}
    bad_steps = [s for s in report.get("actions", []) if by_seq.get(s, {}).get("type") != "ACT"]
    checks["V2"] = not bad_steps
    if bad_steps:
        failures.append(f"V2: claimed action steps that are not ACT events in the log: {bad_steps}")

    # V3: status_claimed = resolved only if V1 passes.
    checks["V3"] = not (report.get("status_claimed") == "resolved" and not checks["V1"])
    if not checks["V3"]:
        failures.append("V3: status_claimed is 'resolved' but the goal check does not pass")

    return VerifyResult(all(checks.values()), checks, failures)
