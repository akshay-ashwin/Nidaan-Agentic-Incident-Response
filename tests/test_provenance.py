"""Run provenance (nidaan/provenance.py + RunLogger GOAL hook). Offline; no LLM."""
import hashlib
import importlib.util
import json
import os
import subprocess

import pytest

import nidaan.provenance as P
from baselines.oneshot import SYSTEM_PROMPT as ONESHOT_PROMPT
from evaluation.harness import Scenario, run_arm
from evaluation.metrics import compute_run_metrics
from evaluation.trace_analysis import analyse_run
from nidaan.logger import RunLogger, read_jsonl
from nidaan.prompt import SYSTEM_PROMPT

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIELDS = {"prompt_sha256", "oneshot_prompt_sha256", "git_commit", "git_dirty", "git_dirty_count", "code_sha256",
          "provider", "model"}


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


# ---- prompt hashes ---------------------------------------------------------------
def test_prompt_hashes_match_the_exact_prompts_and_the_guard():
    spec = importlib.util.spec_from_file_location("guard", os.path.join(ROOT, "tests", "test_prompt_no_leak.py"))
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    h = P.prompt_hashes()
    assert h["prompt_sha256"] == _sha(SYSTEM_PROMPT) == guard.PROMPT_SHA256
    assert h["oneshot_prompt_sha256"] == _sha(ONESHOT_PROMPT) != h["prompt_sha256"]


# ---- provider / model parsing ------------------------------------------------------
@pytest.mark.parametrize("model_id,provider", [("groq:openai/gpt-oss-120b", "groq"),
                                               ("gemini:gemini-3.8-flash", "gemini"),
                                               ("no-provider-prefix", None), (None, None)])
def test_model_fields(model_id, provider):
    assert P.model_fields(model_id) == {"provider": provider, "model": model_id}


# ---- deterministic code hashing ----------------------------------------------------
def _tree(root):
    for rel, text in {"config.py": "A = 1\n", "run.py": "x\n", "nidaan/a.py": "a\n", "nidaan/sub/b.py": "b\n",
                      "settlesim/s.py": "s\n", "nidaan/notes.txt": "ignored\n", ".env": "GROQ_API_KEY=gsk_FAKE\n",
                      "nidaan/__pycache__/a.cpython-313.py": "cache\n", "scripts/other.py": "not hashed\n"}.items():
        os.makedirs(os.path.dirname(os.path.join(root, rel)) or root, exist_ok=True)
        with open(os.path.join(root, rel), "w") as f:
            f.write(text)


def test_code_files_are_exactly_the_documented_set(tmp_path):
    _tree(tmp_path)
    assert P.code_files(str(tmp_path)) == ["config.py", "nidaan/a.py", "nidaan/sub/b.py", "run.py", "settlesim/s.py"]
    real = P.code_files()
    assert {"config.py", "run.py", "nidaan/prompt.py", "nidaan/provenance.py", "baselines/oneshot.py",
            "evaluation/metrics.py", "settlesim/sim.py"} <= set(real)
    assert not any("__pycache__" in f or f.startswith(("tests/", "scripts/", "ui/")) for f in real)


def test_code_hash_is_deterministic_and_content_sensitive(tmp_path):
    _tree(tmp_path)
    h1, h2 = P.code_sha256(str(tmp_path)), P.code_sha256(str(tmp_path))
    assert h1 == h2 and P.code_sha256() == P.code_sha256()
    (tmp_path / "nidaan" / "notes.txt").write_text("changed\n")  # not a hashed file
    (tmp_path / ".env").write_text("GROQ_API_KEY=gsk_OTHER\n")
    assert P.code_sha256(str(tmp_path)) == h1
    (tmp_path / "nidaan" / "a.py").write_text("a2\n")
    assert P.code_sha256(str(tmp_path)) != h1


# ---- git handling --------------------------------------------------------------------
def test_git_fields_in_this_repository():
    b = P.collect_base()
    assert set(b) == FIELDS - {"provider", "model"}
    assert b["git_commit"] is None or (len(b["git_commit"]) == 40 and int(b["git_commit"], 16) >= 0)
    if b["git_commit"] is not None:
        assert isinstance(b["git_dirty"], bool) and isinstance(b["git_dirty_count"], int)
        assert b["git_dirty"] == (b["git_dirty_count"] > 0)


@pytest.mark.parametrize("exc", [FileNotFoundError("git"), subprocess.TimeoutExpired("git", 5)])
def test_git_unavailable_or_hanging_fails_safely(monkeypatch, exc):
    def boom(*a, **k):
        raise exc
    monkeypatch.setattr(P.subprocess, "run", boom)
    b = P.collect_base()
    assert (b["git_commit"], b["git_dirty"], b["git_dirty_count"]) == (None, None, None)
    assert len(b["code_sha256"]) == 64 and b["prompt_sha256"] == _sha(SYSTEM_PROMPT)


def test_outside_a_repository_git_fields_are_none(tmp_path):
    _tree(tmp_path)
    b = P.collect_base(str(tmp_path))
    assert (b["git_commit"], b["git_dirty"], b["git_dirty_count"]) == (None, None, None)


def test_git_is_called_read_only_with_timeout_and_minimal_env(monkeypatch):
    calls = []

    def fake(cmd, **kw):
        calls.append((cmd, kw))
        return subprocess.CompletedProcess(cmd, 0, stdout="abc\n" if "rev-parse" in cmd else " M x\n?? y\n")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_SHOULD_NOT_PROPAGATE")
    monkeypatch.setattr(P.subprocess, "run", fake)
    b = P.collect_base()
    assert (b["git_commit"], b["git_dirty"], b["git_dirty_count"]) == ("abc", True, 2)
    assert {c[0][3] for c in calls} == {"rev-parse", "status"}  # read-only subcommands only
    for _, kw in calls:
        assert kw["timeout"] == P.GIT_TIMEOUT_S and kw["env"]["GIT_OPTIONAL_LOCKS"] == "0"
        assert set(kw["env"]) == {"GIT_OPTIONAL_LOCKS", "PATH"}


# ---- secret exclusion ------------------------------------------------------------------
def test_no_secrets_or_paths_in_provenance(monkeypatch, tmp_path):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_TEST_SECRET_VALUE_123")
    monkeypatch.setenv("GOOGLE_API_KEY", "AIza_TEST_SECRET_VALUE_456")
    _tree(tmp_path)
    for prov in (P.collect("groq:openai/gpt-oss-120b"), P.collect(None, str(tmp_path))):
        text = json.dumps(prov)
        assert set(prov) == FIELDS
        assert "gsk_" not in text and "AIza" not in text and ".env" not in text and "/" not in text.replace(
            "openai/gpt-oss-120b", "")  # no file paths recorded


# ---- logger integration --------------------------------------------------------------------
def test_goal_event_gets_provenance_once_and_computed_once(tmp_path, monkeypatch):
    n = {"calls": 0}
    real = P.collect_base

    def counting(*a, **k):
        n["calls"] += 1
        return real(*a, **k)
    monkeypatch.setattr(P, "collect_base", counting)
    lg = RunLogger("r", str(tmp_path))
    g = lg.log("GOAL", goal="g", model="groq:openai/gpt-oss-120b", eval={"scenario": "s"})
    o = lg.log("OBSERVE", tool="check_pipeline", result="x", outcome="ok")
    g2 = lg.log("GOAL", goal="again")
    lg.close()
    assert n["calls"] == 1
    assert set(g["provenance"]) == FIELDS and g["provenance"]["provider"] == "groq"
    assert "provenance" not in o and "provenance" not in g2
    assert [e["seq"] for e in lg.events] == [1, 2, 3]
    assert read_jsonl(lg.path)[0]["provenance"] == g["provenance"]


def test_runbook_goal_records_no_provider_and_explicit_value_is_kept(tmp_path):
    lg = RunLogger("rb", str(tmp_path))
    g = lg.log("GOAL", goal="g", eval={"arm": "runbook"})
    assert (g["provenance"]["provider"], g["provenance"]["model"]) == (None, None)
    lg2 = RunLogger("x", str(tmp_path))
    assert lg2.log("GOAL", goal="g", provenance={"given": 1})["provenance"] == {"given": 1}


# ---- backward compatibility ----------------------------------------------------------------
def _strip(events):
    return [{k: v for k, v in e.items() if k != "provenance"} for e in events]


def test_metrics_and_trace_analysis_unchanged_by_provenance(tmp_path):
    rec = run_arm("runbook", Scenario("hero", 323, ["F6", "F1", "F7"]), runs_dir=str(tmp_path))
    events = read_jsonl(rec["log_path"])
    assert "provenance" in events[0] and events[0]["provenance"]["model"] is None
    assert rec["metrics"]["spec"]["goal_success"] is True
    assert compute_run_metrics(events) == compute_run_metrics(_strip(events))
    with_p, without_p = analyse_run(events), analyse_run(_strip(events))
    for k in ("measured", "derived", "spec_metrics", "unavailable", "integrity"):
        assert with_p[k] == without_p[k], k


def test_historical_logs_without_provenance_still_load(tmp_path):
    hist = os.path.join(ROOT, "runs", "hero-s323-20261010T122852.jsonl")
    if not os.path.exists(hist):
        pytest.skip("historical log not present (runs/ is gitignored)")
    events = read_jsonl(hist)
    assert "provenance" not in events[0]
    assert compute_run_metrics(events)["spec"]["goal_success"] is True


def test_driver_results_record_provenance(tmp_path):
    spec = importlib.util.spec_from_file_location("drv", os.path.join(ROOT, "scripts", "run_dev_eval.py"))
    drv = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(drv)
    out = tmp_path / "r.json"
    assert drv.main(["--arm", "runbook", "--repeats", "1", "--scenarios", "dev_f2", "--out", str(out),
                     "--runs-dir", str(tmp_path / "runs")]) == 0
    prov = json.loads(out.read_text())["driver"]["provenance"]
    assert set(prov) == FIELDS and prov["model"] is None and prov["prompt_sha256"] == _sha(SYSTEM_PROMPT)
