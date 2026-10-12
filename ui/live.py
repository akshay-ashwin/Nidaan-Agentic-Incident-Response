"""Interactive (live) runs for the dashboard. No Streamlit import; unit-tested offline.

A LiveRun executes ONE development scenario in a background thread, with either:
  - mode "runbook": the deterministic baseline (baselines.runbook.run_runbook) - no LLM calls, or
  - mode "nidaan":  the LangGraph agent (nidaan.graph.NidaanAgent) - uses the configured provider's quota.

Events are the existing RunLogger events, unchanged in schema. A thin RunLogger subclass also pushes a
copy of every event onto a thread-safe queue so the UI can render the trace while the run is in progress.

Guarantees:
  - Importing this module makes no LLM request and reads no API key. A model client is only built
    inside NidaanAgent when a "nidaan" run is explicitly started.
  - Only scenarios from evaluation.scenarios.DEV_SCENARIOS can be run, and their faults must all be
    development faults (settlesim.generator.generate also enforces this).
  - One live run at a time per process (a second start raises LiveRunBusy).
  - Logs go to runs_live/ (gitignored), never to runs/ or results/, so interactive runs cannot mix with
    the recorded evaluation evidence.
  - The agent's submitted report (its claim) is exposed separately from the verifier's result and from
    the simulator's own goal check. A run is called VERIFIED only when the verifier passed.
  - No free-form model text or reasoning is collected: only the structured events RunLogger already writes.
"""
from __future__ import annotations

import os
import pathlib
import queue
import re
import threading
from datetime import datetime, timezone

from nidaan import llm_errors
from nidaan.logger import RunLogger, agent_visible  # noqa: F401  (agent_visible re-exported for the UI)
from settlesim.generator import DEV_FAULTS, generate

ROOT = pathlib.Path(__file__).resolve().parent.parent
LIVE_RUNS_DIR = ROOT / "runs_live"  # separate from runs/ (evaluation evidence)
MODES = ("runbook", "nidaan")
KEY_ENV = {"groq": "GROQ_API_KEY", "gemini": "GOOGLE_API_KEY"}

# Anything that looks like a provider key is masked in error text shown to the UI.
_KEY_RE = re.compile(r"(gsk_|AIza|AQ\.)[A-Za-z0-9_\-.]+")
_ORG_RE = re.compile(r"org_[A-Za-z0-9]+")

_lock = threading.Lock()  # process-wide: at most one live run
_current: "LiveRun | None" = None


class LiveRunBusy(RuntimeError):
    """Another live run is still in progress."""


def redact(msg: str) -> str:
    return llm_errors.redact(_ORG_RE.sub("org_<redacted>", _KEY_RE.sub("<redacted>", msg)))


# ---- scenarios ------------------------------------------------------------
def dev_scenarios() -> dict:
    """name -> Scenario, development scenarios only."""
    from evaluation.scenarios import DEV_SCENARIOS  # local: keeps import of this module light
    return {s.name: s for s in DEV_SCENARIOS}


def resolve_scenario(name: str):
    scenarios = dev_scenarios()
    if name not in scenarios:
        raise ValueError(f"unknown scenario {name!r}; development scenarios: {', '.join(scenarios)}")
    s = scenarios[name]
    bad = [f for f in s.faults if f not in DEV_FAULTS]
    if bad:
        raise ValueError(f"scenario {name!r} contains non-development fault(s); refusing to run")
    return s


# ---- provider key (presence only; the value is never read into the UI) -------
def provider_key_present() -> bool:
    import config
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")  # loads the file into the environment; nothing is printed
    return bool(os.environ.get(KEY_ENV.get(config.PROVIDER, ""), ""))


# ---- simulator state (read from the real SettleSim object) -------------------
def sim_state(sim) -> dict:
    goals = sim.goals()
    return {"goals": goals, "goal_met": all(goals.values()), "payouts_sent": sim.sent_count(),
            "payouts_total": len(sim.payouts), "settled_amount": sim.settled_amount(),
            "duplicates": len(sim.duplicates()), "faults_active": sim.active_faults(),
            "worker_running": sim.worker.running, "queue_depth": sim.worker.queue_depth,
            "ledger_up": sim.ledger.up, "disk_pct": sim.ledger.disk_pct, "checkpoint": sim.checkpoint,
            # Per-payout send counts for the live ledger view (live runs only; recorded logs do not store this).
            "payouts": [{"id": p.id, "amount": p.amount, "send_count": p.send_count} for p in sim.payouts]}


class StreamingRunLogger(RunLogger):
    """RunLogger that also publishes each event (as written to JSONL) to a queue."""

    def __init__(self, run_id: str, runs_dir: str, sink: "queue.Queue[dict]"):
        super().__init__(run_id, runs_dir)
        self._sink = sink

    def log(self, type: str, **fields) -> dict:
        ev = super().log(type, **fields)
        self._sink.put(dict(ev))
        return ev


class LiveRun:
    """One interactive run. Create with start(); poll with snapshot()."""

    def __init__(self, mode: str, scenario_name: str, runs_dir: str | os.PathLike = LIVE_RUNS_DIR, llm=None):
        if mode not in MODES:
            raise ValueError(f"unknown mode {mode!r}; modes: {MODES}")
        self.mode = mode
        self.scenario = resolve_scenario(scenario_name)
        self.runs_dir = str(runs_dir)
        self._llm = llm  # tests only; None -> NidaanAgent builds the configured model on start
        self.sim = generate(self.scenario.seed, self.scenario.faults)
        self.initial_state = sim_state(self.sim)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
        self.run_id = f"live-{mode}-{self.scenario.name}-s{self.scenario.seed}-{stamp}"
        self.log_path: str | None = None
        self.started_at: str | None = None
        self.finished_at: str | None = None
        self._q: "queue.Queue[dict]" = queue.Queue()
        self._events: list[dict] = []
        self._ev_lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._done = threading.Event()
        self.result: dict | None = None
        self.error: str | None = None

    # ---- lifecycle -----------------------------------------------------
    def start(self) -> "LiveRun":
        global _current
        if not _lock.acquire(blocking=False):
            raise LiveRunBusy("a live run is already in progress; wait for it to finish")
        try:
            if self.mode == "nidaan" and self._llm is None and not provider_key_present():
                raise RuntimeError("no API key for the configured provider in .env; Nidaan cannot run live")
            logger = StreamingRunLogger(self.run_id, self.runs_dir, self._q)
            self.log_path = logger.path
            self.started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            self._thread = threading.Thread(target=self._worker, args=(logger,), daemon=True,
                                            name=f"nidaan-live-{self.run_id}")
            _current = self
            self._thread.start()
        except BaseException:
            _lock.release()
            raise
        return self

    def _worker(self, logger: StreamingRunLogger) -> None:
        info = {"scenario": self.scenario.name, "seed": self.scenario.seed, "faults": list(self.scenario.faults)}
        try:
            if self.mode == "runbook":
                from baselines.runbook import run_runbook
                self.result = run_runbook(self.sim, logger, info)
            else:
                from nidaan.graph import NidaanAgent
                out = NidaanAgent(self.sim, logger, llm=self._llm, scenario_info={**info, "arm": "nidaan"}).run()
                self.result = {"status": out["status"], "reason": out["reason"], "metrics": dict(out["metrics"])}
        except Exception as e:  # noqa: BLE001 - surfaced to the UI, redacted
            self.error = redact(f"{type(e).__name__}: {str(e)[:1000]}")
        finally:
            logger.close()  # idempotent; the arms close it on normal completion
            self.finished_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            self._done.set()
            _lock.release()

    def wait(self, timeout: float | None = None) -> bool:
        return self._done.wait(timeout)

    @property
    def running(self) -> bool:
        return self._thread is not None and not self._done.is_set()

    # ---- reading -------------------------------------------------------
    def events(self) -> list[dict]:
        with self._ev_lock:
            while True:
                try:
                    self._events.append(self._q.get_nowait())
                except queue.Empty:
                    break
            return list(self._events)

    def snapshot(self) -> dict:
        evs = self.events()
        done = self._done.is_set()
        if self._thread is None:
            status = "not_started"
        elif not done:
            status = "running"
        elif self.error:
            status = "error"
        else:
            status = "completed"
        verifies = [e for e in evs if e["type"] == "VERIFY"]
        last_verify = verifies[-1] if verifies else None
        final = next((e for e in reversed(evs) if e["type"] == "FINAL"), None)
        final_state = sim_state(self.sim) if done else None
        return {
            "run_id": self.run_id, "mode": self.mode, "scenario": self.scenario.name,
            "seed": self.scenario.seed, "faults": list(self.scenario.faults), "status": status,
            "started_at": self.started_at, "finished_at": self.finished_at, "log_path": self.log_path,
            "events": evs, "error": self.error, "result": self.result,
            "progress": {"payouts_sent": self.sim.sent_count(), "payouts_total": len(self.sim.payouts)},
            "initial_state": self.initial_state, "final_state": final_state,
            # The agent's claim (its submitted report) - NOT evidence of anything by itself.
            "agent_claim": last_verify.get("args") if last_verify else None,
            # What the deterministic verifier established (Nidaan only; the runbook submits no report).
            "verification": ({"outcome": last_verify.get("outcome"), "checks": last_verify.get("checks"),
                              "message": last_verify.get("result")} if last_verify else None),
            # Every verifier attempt in order (the agent may resubmit after a failed check).
            "verify_history": [{"seq": e["seq"], "outcome": e.get("outcome"), "checks": e.get("checks"),
                                "message": e.get("result")} for e in verifies],
            "final_outcome": final.get("outcome") if final else None,
            "verdict": verdict(self.mode, done, self.error, last_verify, final_state, final),
            # Why the run stopped, if the model provider stopped it (redacted; plain-language explanation).
            "llm_failure": llm_failure(final),
            # Provider rate-limit rejections that were retried automatically during this run.
            "rate_limit_retries": sum(1 for e in evs if e["type"] == "ERROR" and _error_kind(e) == llm_errors.RATE_LIMIT
                                      and e.get("retry_in_s") is not None),
            # While running: the agent is waiting before a retry (last event is a retried LLM error).
            "waiting": _waiting(evs) if not done else None,
        }


def _error_kind(e: dict) -> str | None:
    if e.get("error_kind"):
        return e["error_kind"]
    msg = str(e.get("error", ""))
    return llm_errors.classify(msg).kind if msg.startswith("LLM call failed") else None


def _waiting(evs: list[dict]) -> dict | None:
    last = evs[-1] if evs else None
    if last and last["type"] == "ERROR" and last.get("retry_in_s") is not None:
        return {"kind": _error_kind(last), "retry_in_s": last["retry_in_s"], "attempt": last.get("attempt"),
                "since": last.get("ts")}
    return None


def llm_failure(final: dict | None) -> dict | None:
    """Classification and explanation of a run stopped by an LLM error (None otherwise). Redacted throughout."""
    reason = str((final or {}).get("result", ""))
    if not reason.startswith("LLM error"):
        return None
    err = llm_errors.classify(redact(reason[len("LLM error: "):]))
    return {**err.to_dict(), **llm_errors.explain(err)}


def verdict(mode: str, done: bool, error: str | None, last_verify: dict | None, final_state: dict | None,
            final_event: dict | None = None) -> str | None:
    """Headline outcome. Never claims success without independent evidence.
    nidaan:  VERIFIED only if the verifier passed AND the simulator goal check holds.
             ERROR if the run stopped on a model-provider error (rate limit, outage, ...): the run is incomplete,
             which says nothing about the simulator itself (its real state is still reported).
    runbook: GOAL_MET from the simulator goal check (the runbook submits no report to verify)."""
    if not done:
        return None
    if error:
        return "ERROR"
    if mode == "nidaan" and str((final_event or {}).get("result", "")).startswith("LLM error"):
        return "ERROR"
    goal = bool(final_state and final_state["goal_met"])
    if mode == "nidaan":
        return "VERIFIED" if (last_verify and last_verify.get("outcome") == "pass" and goal) else "FAILED"
    return "GOAL_MET" if goal else "GOAL_NOT_MET"


# ---- process-wide helpers for the UI ---------------------------------------
def current_run() -> "LiveRun | None":
    """The most recently started live run in this process (running or finished)."""
    return _current


def is_busy() -> bool:
    return _lock.locked()


def start_live_run(mode: str, scenario_name: str, runs_dir: str | os.PathLike = LIVE_RUNS_DIR) -> LiveRun:
    """Explicit entry point for the UI. Raises LiveRunBusy / ValueError / RuntimeError."""
    return LiveRun(mode, scenario_name, runs_dir).start()
