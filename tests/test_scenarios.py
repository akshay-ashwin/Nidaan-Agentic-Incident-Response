import pathlib
import re

from evaluation.harness import run_arm
from evaluation.scenarios import (DEV_SCENARIOS, HELD_OUT_RUNS_PER_SCENARIO, HERO_MIN_SUCCESSES,
                                  HERO_REHEARSAL_RUNS, NIDAAN_RUNS_IF_QUOTA_SHORT)
from settlesim.generator import DEV_FAULTS, HERO_FAULTS, HERO_SEED, generate

SRC = pathlib.Path(__file__).resolve().parent.parent / "evaluation" / "scenarios.py"


def test_exactly_six_unique_dev_scenarios():
    assert len(DEV_SCENARIOS) == 6
    assert len({s.name for s in DEV_SCENARIOS}) == 6
    assert len({s.seed for s in DEV_SCENARIOS}) == 6


def test_every_fault_is_a_development_fault_with_no_repeats():
    for s in DEV_SCENARIOS:
        assert s.faults and set(s.faults) <= set(DEV_FAULTS), s
        assert len(set(s.faults)) == len(s.faults), s


def test_hero_is_the_frozen_hero_seed_and_combination():
    hero = next(s for s in DEV_SCENARIOS if s.name == "hero")
    assert hero.seed == HERO_SEED == 323
    assert hero.faults == list(HERO_FAULTS) == ["F6", "F1", "F7"]


def test_coverage_singles_and_multi_fault_interactions():
    assert set().union(*(s.faults for s in DEV_SCENARIOS)) == set(DEV_FAULTS)  # every dev fault appears
    singles = [s for s in DEV_SCENARIOS if len(s.faults) == 1]
    multi = [s for s in DEV_SCENARIOS if len(s.faults) > 1]
    assert len(singles) == 3 and len(multi) == 3


def test_scenarios_generate_exactly_the_stated_faults():
    for s in DEV_SCENARIOS:
        assert sorted(generate(s.seed, s.faults).active_faults()) == sorted(s.faults), s.name


def test_each_scenario_is_solvable_by_the_runbook(tmp_path):  # local deterministic sanity, no LLM
    for s in DEV_SCENARIOS:
        m = run_arm("runbook", s, runs_dir=str(tmp_path))["metrics"]["spec"]
        assert m["goal_success"] and m["duplicate_payouts"] == 0, s.name


def test_definitions_contain_only_development_fault_ids_and_no_hints():
    text = SRC.read_text()
    assert set(re.findall(r"\bF\d+\b", text)) <= set(DEV_FAULTS)  # no other fault identifiers anywhere
    block = re.search(r"DEV_SCENARIOS.*?\n\)\n", text, re.S).group(0)
    block = "\n".join(ln.split("#")[0] for ln in block.splitlines())  # drop trailing comments
    for word in ("rotate", "restart", "set_config", "run_task", "resume", "retry", "fix", "hint"):
        assert word not in block.lower(), f"recovery wording in scenario definitions: {word}"
    assert len(re.findall(r"Scenario\(", block)) == 6


def test_protocol_constants_match_spec():
    assert HELD_OUT_RUNS_PER_SCENARIO == {"nidaan": 3, "runbook": 1, "oneshot": 3}
    assert NIDAAN_RUNS_IF_QUOTA_SHORT == 2
    assert (HERO_REHEARSAL_RUNS, HERO_MIN_SUCCESSES) == (10, 9)
