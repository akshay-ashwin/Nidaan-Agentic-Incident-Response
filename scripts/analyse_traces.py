"""Offline execution-trace analyser (no LLM calls, no network).

Usage:
  python scripts/analyse_traces.py --results results/*.json --log runs/<cli-run>.jsonl --out reports/trace_analysis.md
  python scripts/analyse_traces.py --log runs/<run>.jsonl --print-timeline

Inputs are existing results files (their records' log_path) and/or individual run logs. Writes a Markdown
report and a JSON file with the same content (<out>.json). Refuses to overwrite unless --force.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from evaluation.aggregate import load_results  # noqa: E402
from evaluation.trace_analysis import DEFINITIONS, analyse_run, render_markdown, timeline  # noqa: E402
from nidaan.logger import read_jsonl  # noqa: E402


def collect_paths(results: list[str], logs: list[str]) -> list[str]:
    paths = []
    for f in results:
        for r in load_results(f)["records"]:
            paths.append(r["log_path"])
    paths += logs
    seen, out = set(), []
    for p in paths:  # keep order, drop duplicates
        k = os.path.abspath(p)
        if k not in seen:
            seen.add(k)
            out.append(p)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--results", nargs="*", default=[], help="results JSON files from scripts/run_dev_eval.py")
    ap.add_argument("--log", nargs="*", default=[], help="individual run logs (e.g. a CLI hero run)")
    ap.add_argument("--out", help="Markdown report path; JSON is written next to it")
    ap.add_argument("--force", action="store_true", help="overwrite an existing report")
    ap.add_argument("--print-timeline", action="store_true", help="print each run's timeline to the terminal")
    a = ap.parse_args(argv)

    paths = collect_paths(a.results, a.log)
    if not paths:
        ap.error("no runs given: pass --results and/or --log")
    analyses, timelines, unreadable = [], {}, []
    for p in paths:
        try:
            events = read_jsonl(p)
        except (OSError, json.JSONDecodeError) as e:
            unreadable.append({"path": p, "error": f"{type(e).__name__}: {e}"})
            continue
        if not events:
            unreadable.append({"path": p, "error": "empty log"})
            continue
        an = analyse_run(events, source=os.path.relpath(p, ROOT) if os.path.isabs(p) else p)
        analyses.append(an)
        timelines[an["run_id"]] = timeline(events)

    for u in unreadable:
        print(f"UNREADABLE {u['path']}: {u['error']}")
    for an in analyses:
        m = an["measured"]
        print(f"{an['arm']:8} {str(an['scenario']):10} final={m['final_outcome'] or 'INCOMPLETE':13} "
              f"goal_met={m['goal_met']} dup={m['duplicates']} actions={m['actions']} {m['actions_by_outcome']} "
              f"{an['run_id']}")
        if a.print_timeline:
            for r in timelines[an["run_id"]]:
                err = f" [{', '.join(f'{k}={v}' for k, v in r['errors_before'].items())}]" if r["errors_before"] else ""
                print(f"   #{r['seq']}{err} {r['stage']}: {r['event']} -> {r['environment_response']}"
                      + (f"  {{{', '.join(r['eval_flags'])}}}" if r["eval_flags"] else ""))

    if a.out:
        js = os.path.splitext(a.out)[0] + ".json"
        for p in (a.out, js):
            if os.path.exists(p) and not a.force:
                ap.error(f"{p} exists; use --force to overwrite or choose another --out")
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(render_markdown(analyses, timelines, inputs=a.results + a.log))
        with open(js, "w", encoding="utf-8") as f:
            json.dump({"inputs": a.results + a.log, "analyses": analyses, "timelines": timelines, "unreadable": unreadable,
                       "definitions": DEFINITIONS}, f, indent=2, ensure_ascii=False)
        print(f"wrote {a.out} and {js}")
    return 1 if unreadable else 0


if __name__ == "__main__":
    sys.exit(main())
