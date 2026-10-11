"""Structured JSONL run log (SPEC §6).

Two channels live in one record:
  - agent-visible fields (plans, why, tool results, ...), and
  - an `eval` object holding evaluation-only annotations, never shown to the agent.
Only structured data is stored: no free-form model text or reasoning.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

EVENT_TYPES = ("GOAL", "PLAN", "OBSERVE", "ACT", "VERIFY", "FINAL", "ERROR")
TOOL_EVENT_TYPES = ("OBSERVE", "ACT")  # events whose result the agent saw (citable)


class RunLogger:
    def __init__(self, run_id: str, runs_dir: str = "runs"):
        self.run_id = run_id
        self.events: list[dict] = []
        os.makedirs(runs_dir, exist_ok=True)
        self.path = os.path.join(runs_dir, f"{run_id}.jsonl")
        self._f = open(self.path, "w", encoding="utf-8")
        from nidaan.provenance import collect_base  # local import: provenance hashes prompts that import this module
        self._provenance = collect_base()  # once per run; attached to the initial GOAL event (run metadata, additive)

    def log(self, type: str, **fields) -> dict:
        if type not in EVENT_TYPES:
            raise ValueError(f"unknown event type {type!r}")
        ev = {"seq": len(self.events) + 1,
              "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
              "run_id": self.run_id, "type": type}
        ev.update({k: v for k, v in fields.items() if v is not None})
        if type == "GOAL" and self._provenance is not None and "provenance" not in ev:
            from nidaan.provenance import model_fields
            ev["provenance"] = {**self._provenance, **model_fields(fields.get("model"))}
            self._provenance = None  # initial GOAL only
        self.events.append(ev)
        self._f.write(json.dumps(ev, ensure_ascii=False) + "\n")
        self._f.flush()
        return ev

    def close(self) -> None:
        self._f.close()

    def tool_event_seqs(self) -> set[int]:
        return {e["seq"] for e in self.events if e["type"] in TOOL_EVENT_TYPES}


def agent_visible(event: dict) -> dict:
    """The event without evaluation-only annotations (what a UI trace may show live)."""
    return {k: v for k, v in event.items() if k != "eval"}


def read_jsonl(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]
