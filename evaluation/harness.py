"""Run one arm on one scenario and return a result record. Library only (no scenario set here).

    records = [run_arm("runbook", Scenario("hero", 323, ["F6", "F1", "F7"]))]
    save_results("results/dev_runbook.json", records)

The "nidaan" and "oneshot" arms call Gemini; the "runbook" arm makes no LLM calls.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from baselines.oneshot import run_oneshot
from baselines.runbook import run_runbook
from evaluation.metrics import compute_run_metrics
from nidaan.graph import NidaanAgent
from nidaan.logger import RunLogger, read_jsonl
from settlesim.generator import generate

ARMS = ("nidaan", "runbook", "oneshot")


@dataclass
class Scenario:
    name: str
    seed: int
    faults: list[str]


def run_arm(arm: str, scenario: Scenario, repeat: int = 1, runs_dir: str = "runs", llm=None) -> dict:
    if arm not in ARMS:
        raise ValueError(f"unknown arm {arm!r}; arms: {ARMS}")
    sim = generate(scenario.seed, scenario.faults)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    run_id = f"{arm}-{scenario.name}-s{scenario.seed}-r{repeat}-{stamp}"
    logger = RunLogger(run_id, runs_dir)
    info = {"scenario": scenario.name, "seed": scenario.seed, "faults": list(scenario.faults)}
    if arm == "runbook":
        run_runbook(sim, logger, info)
    elif arm == "oneshot":
        run_oneshot(sim, logger, info, llm=llm)
    else:
        NidaanAgent(sim, logger, llm=llm, scenario_info={**info, "arm": "nidaan"}).run()
    return {"arm": arm, "scenario": scenario.name, "seed": scenario.seed, "faults": list(scenario.faults),
            "repeat": repeat, "run_id": run_id, "log_path": logger.path,
            "metrics": compute_run_metrics(read_jsonl(logger.path))}
