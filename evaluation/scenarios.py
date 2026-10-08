"""The six development evaluation scenarios (SPEC §9: "Dev: 6 scenarios, prompt tuning only").

Plain data: name, seed, development fault combination. No descriptions, hints or recovery steps.
Seeds are fixed here and were not tuned for difficulty. Lives under evaluation/ so agent-accessible
code never imports it.

Design: three single-fault scenarios and three multi-fault scenarios covering every development
fault at least once; the hero (SPEC §7) is one of the six.
"""
from __future__ import annotations

from evaluation.harness import Scenario
from settlesim.generator import HERO_FAULTS, HERO_SEED

DEV_SCENARIOS: tuple[Scenario, ...] = (
    Scenario("hero", HERO_SEED, list(HERO_FAULTS)),  # F6 + F1 + F7, frozen hero seed (SPEC §7)
    Scenario("dev_f2", 11, ["F2"]),
    Scenario("dev_f4", 12, ["F4"]),
    Scenario("dev_f7", 13, ["F7"]),
    Scenario("dev_f1_f2", 14, ["F1", "F2"]),
    Scenario("dev_f4_f6", 15, ["F4", "F6"]),
)

# Evaluation protocol constants, quoted from SPEC.
# SPEC §9 gives runs-per-scenario for the HELD-OUT scenarios only: Nidaan x3 (x2 if quota short),
# runbook x1, one-shot x3. SPEC §7: hero is rehearsed >= 10 times and must succeed >= 9.
# SPEC does NOT state repeats for the development scenarios (see PROGRESS.md, open question).
HELD_OUT_RUNS_PER_SCENARIO = {"nidaan": 3, "runbook": 1, "oneshot": 3}
NIDAAN_RUNS_IF_QUOTA_SHORT = 2
HERO_REHEARSAL_RUNS = 10
HERO_MIN_SUCCESSES = 9
