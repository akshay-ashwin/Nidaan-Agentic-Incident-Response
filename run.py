"""CLI runner: python run.py [--scenario hero | --seed N --faults F1,F6] [--runs-dir runs]"""
import argparse
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv

from nidaan.graph import NidaanAgent
from nidaan.logger import RunLogger, agent_visible
from settlesim.generator import HERO_FAULTS, HERO_SEED, generate


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default="hero", choices=["hero", "custom"])
    ap.add_argument("--seed", type=int)
    ap.add_argument("--faults", help="comma-separated development fault ids, with --seed")
    ap.add_argument("--runs-dir", default="runs")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    load_dotenv()

    if a.seed is not None or a.faults:
        if a.seed is None or not a.faults:
            ap.error("--seed and --faults must be given together")
        seed, faults = a.seed, [f.strip() for f in a.faults.split(",")]
        name = "custom"
    else:
        seed, faults, name = HERO_SEED, list(HERO_FAULTS), "hero"

    sim = generate(seed, faults)
    run_id = f"{name}-s{seed}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}"
    logger = RunLogger(run_id, a.runs_dir)
    if not a.quiet:  # live trace: agent-visible channel only
        orig = logger.log

        def traced(type, **fields):
            ev = orig(type, **fields)
            v = agent_visible(ev)
            line = v.get("result") or v.get("error") or v.get("reason") or v.get("goal", "")
            tool = f" {v['tool']}" if "tool" in v else ""
            print(f"[{v['seq']:>3}] {type:<7}{tool} {str(line).splitlines()[0][:110] if line else ''}")
            return ev
        logger.log = traced

    out = NidaanAgent(sim, logger, scenario_info={"scenario": name, "seed": seed, "faults": faults}).run()
    m = out["metrics"]
    print(f"\nstatus: {out['status']}" + (f" ({out['reason']})" if out["reason"] else ""))
    tok = m["total_tokens"] if m["tokens_available"] else "unavailable"
    print(f"LLM calls: {m['llm_calls']}  tokens: {tok}  latency: {m['latency_s']:.1f}s  errors: {m['llm_errors']}")
    print(f"log: {out['log_path']}")
    return 0 if out["status"] == "VERIFIED" else 1


if __name__ == "__main__":
    sys.exit(main())
