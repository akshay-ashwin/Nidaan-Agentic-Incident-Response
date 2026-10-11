"""Development-evaluation driver: run one arm over the development scenarios via the existing harness.

Usage:
  python scripts/run_dev_eval.py --arm runbook --repeats 1 --out results/dev_runbook.json
  python scripts/run_dev_eval.py --arm nidaan --repeats N --scenarios hero,dev_f2 --out results/<new>.json

- SPEC does not define repeats for development scenarios, so --repeats has no default.
- The results file must not exist yet (evidence is never overwritten). It is rewritten atomically
  after every run, so completed runs survive if the process stops.
- Scoring and aggregation are the harness's own (compute_run_metrics, aggregate, Wilson CIs).
- No run is dropped: a run whose log can be scored stays in "records" (marked incomplete if it has no
  FINAL event); a run that raised before writing a scorable log is listed in "failed_runs".
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(ROOT, ".env"))  # before any model is built; values are never printed

import config  # noqa: E402
from evaluation.aggregate import aggregate  # noqa: E402
from evaluation.harness import ARMS, run_arm  # noqa: E402
from evaluation.metrics import compute_run_metrics  # noqa: E402
from evaluation.scenarios import DEV_SCENARIOS  # noqa: E402
from nidaan.graph import redact  # noqa: E402
from nidaan.logger import read_jsonl  # noqa: E402
from nidaan.provenance import collect as collect_provenance  # noqa: E402

LLM_ARMS = ("nidaan", "oneshot")
KEY_RE = re.compile(r"(gsk_|AIza)[A-Za-z0-9_\-]+")


def clean(msg: str) -> str:
    return KEY_RE.sub("<redacted>", redact(msg))


def run_status(events: list[dict]) -> dict:
    goal = next((e for e in events if e["type"] == "GOAL"), {})
    final = next((e for e in reversed(events) if e["type"] == "FINAL"), None)
    return {"model": goal.get("model"),
            "final_outcome": final.get("outcome") if final else None,
            "incomplete": final is None,
            "error_events": sum(1 for e in events if e["type"] == "ERROR"),
            "llm": (final or {}).get("metrics")}


def save(path: str, records: list[dict], failed: list[dict], meta: dict) -> None:
    out = {"records": records, "summary": aggregate(records), "failed_runs": failed,
           "driver": {**meta, "n_records": len(records), "n_failed_runs": len(failed),
                      "updated": datetime.now(timezone.utc).isoformat(timespec="seconds")}}
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)  # atomic: a stop mid-write never leaves a truncated file


def one_run(arm: str, scenario, repeat: int, runs_dir: str) -> tuple[dict | None, dict | None]:
    """(record, None) if a scorable log exists, else (None, failure)."""
    prefix = os.path.join(runs_dir, f"{arm}-{scenario.name}-s{scenario.seed}-r{repeat}-")
    before = set(glob.glob(prefix + "*.jsonl"))
    try:
        rec = run_arm(arm, scenario, repeat=repeat, runs_dir=runs_dir)
        rec["driver_status"] = run_status(read_jsonl(rec["log_path"]))
        return rec, None
    except Exception as e:  # noqa: BLE001 - one failed run must not stop the others
        err = clean(f"{type(e).__name__}: {str(e)[:500]}")
    new = sorted(set(glob.glob(prefix + "*.jsonl")) - before)
    base = {"arm": arm, "scenario": scenario.name, "seed": scenario.seed, "faults": list(scenario.faults),
            "repeat": repeat}
    if new:
        events = read_jsonl(new[-1])
        if any(e["type"] == "GOAL" for e in events):  # partial log: scored as-is, flagged incomplete
            return {**base, "run_id": os.path.basename(new[-1])[:-6], "log_path": new[-1],
                    "metrics": compute_run_metrics(events),
                    "driver_status": {**run_status(events), "exception": err}}, None
    return None, {**base, "log_path": new[-1] if new else None, "exception": err}


def main(argv: list[str] | None = None) -> int:
    names = [s.name for s in DEV_SCENARIOS]
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--arm", required=True, choices=ARMS)
    ap.add_argument("--repeats", required=True, type=int, help="runs per scenario (SPEC gives none for dev)")
    ap.add_argument("--out", required=True, help="new results file, e.g. results/dev_runbook.json")
    ap.add_argument("--scenarios", default=",".join(names), help=f"comma-separated subset of {names}")
    ap.add_argument("--runs-dir", default=os.path.join(ROOT, "runs"))
    a = ap.parse_args(argv)

    chosen = [s.strip() for s in a.scenarios.split(",") if s.strip()]
    unknown = [s for s in chosen if s not in names]
    if unknown or not chosen:
        ap.error(f"unknown development scenario(s) {unknown}; choose from {names}")
    if a.repeats < 1:
        ap.error("--repeats must be >= 1")
    if os.path.exists(a.out):
        ap.error(f"{a.out} already exists; choose a new --out (existing evidence is never overwritten)")
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)

    scenarios = [s for s in DEV_SCENARIOS if s.name in chosen]
    meta = {"arm": a.arm, "repeats": a.repeats, "scenarios": [s.name for s in scenarios],
            "model": config.MODEL_ID if a.arm in LLM_ARMS else None,
            "started": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    meta["provenance"] = collect_provenance(meta["model"])  # prompt/code/git state at evaluation start
    if a.arm in LLM_ARMS:
        key = {"groq": "GROQ_API_KEY", "gemini": "GOOGLE_API_KEY"}[config.PROVIDER]
        if not os.environ.get(key):
            ap.error(f"{key} is not set (put it in .env)")
    print(f"arm={a.arm} model={meta['model'] or 'none (no LLM)'} repeats={a.repeats} scenarios={meta['scenarios']}")

    records, failed = [], []
    for s in scenarios:
        for r in range(1, a.repeats + 1):
            rec, fail = one_run(a.arm, s, r, a.runs_dir)
            if rec:
                records.append(rec)
                st, sp = rec["driver_status"], rec["metrics"]["spec"]
                flag = " INCOMPLETE" if st["incomplete"] else ""
                exc = f" exception={st['exception']}" if "exception" in st else ""
                print(f"  {s.name} r{r}: goal_success={sp['goal_success']} duplicates={sp['duplicate_payouts']} "
                      f"final={st['final_outcome']}{flag} actions={sp['actions']} llm_calls={sp['llm_calls']} "
                      f"tokens={sp['total_tokens']} errors={st['error_events']}{exc} log={os.path.basename(rec['log_path'])}")
            else:
                failed.append(fail)
                print(f"  {s.name} r{r}: FAILED before a scorable log: {fail['exception']}")
            save(a.out, records, failed, meta)

    print(f"saved {a.out}: {len(records)} scored run(s), {len(failed)} failed run(s)")
    return 0 if not failed and all(not r["driver_status"]["incomplete"] for r in records) else 1


if __name__ == "__main__":
    sys.exit(main())
