"""Deterministic plan validation (SPEC §4).

1. Plan v1 must exist before any OBSERVE or ACT call.
2. v2+: triggered_by must cite existing observation-event sequence numbers.
3. v2+: at least one cited observation must be newer than the previous plan.
4. v2+: the step list must change (no-op replans rejected).
"""
from __future__ import annotations

import difflib
from dataclasses import dataclass, field


@dataclass
class PlanVerdict:
    ok: bool
    message: str
    version: int | None = None
    diff: dict = field(default_factory=dict)


def _norm(steps: list[str]) -> list[str]:
    return [" ".join(s.split()) for s in steps]


def step_diff(old: list[str], new: list[str]) -> dict:
    old, new = _norm(old), _norm(new)
    added = [s for s in new if s not in old]
    removed = [s for s in old if s not in new]
    return {"added": added, "removed": removed, "reordered": not added and not removed and old != new}


class PlanManager:
    def __init__(self):
        self.versions: list[dict] = []  # {version, steps, seq}

    @property
    def current_version(self) -> int:
        return len(self.versions)

    def has_plan(self) -> bool:
        return bool(self.versions)

    def validate(self, steps: list[str], triggered_by: list[int], tool_event_seqs: set[int]) -> PlanVerdict:
        if not steps or not all(isinstance(s, str) and s.strip() for s in steps):
            return PlanVerdict(False, "rejected: steps must be a non-empty list of non-empty strings")
        if not self.versions:
            return PlanVerdict(True, "plan v1 accepted", 1, {"added": _norm(steps), "removed": [], "reordered": False})
        prev = self.versions[-1]
        if not triggered_by:
            return PlanVerdict(False, "rejected: a replan must cite triggered_by event numbers")
        unknown = [t for t in triggered_by if t not in tool_event_seqs]
        if unknown:
            return PlanVerdict(False, f"rejected: triggered_by cites unknown observation events {unknown}")
        if max(triggered_by) <= prev["seq"]:
            return PlanVerdict(False, f"rejected: at least one cited event must be newer than plan "
                                      f"v{prev['version']} (event {prev['seq']})")
        if _norm(steps) == _norm(prev["steps"]):
            return PlanVerdict(False, "rejected: steps unchanged from the current plan")
        return PlanVerdict(True, f"plan v{prev['version'] + 1} accepted", prev["version"] + 1,
                           step_diff(prev["steps"], steps))

    def commit(self, steps: list[str], seq: int) -> None:
        self.versions.append({"version": len(self.versions) + 1, "steps": list(steps), "seq": seq})
