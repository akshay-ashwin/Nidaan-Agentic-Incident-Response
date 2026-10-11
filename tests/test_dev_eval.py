"""Development-evaluation driver (scripts/run_dev_eval.py). Offline: runbook arm only, no LLM."""
import importlib.util
import json
import os

import pytest

from evaluation.harness import run_arm as real_run_arm
from evaluation.scenarios import DEV_SCENARIOS
from nidaan.logger import RunLogger

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("run_dev_eval", os.path.join(ROOT, "scripts", "run_dev_eval.py"))
drv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(drv)


def _run(tmp_path, *extra):
    out = tmp_path / "res" / "dev.json"
    code = drv.main(["--arm", "runbook", "--repeats", "1", "--out", str(out),
                     "--runs-dir", str(tmp_path / "runs"), *extra])
    return code, out


def test_runbook_all_six_saved_with_existing_aggregation(tmp_path):
    code, out = _run(tmp_path)
    data = json.loads(out.read_text())
    assert code == 0
    assert [r["scenario"] for r in data["records"]] == [s.name for s in DEV_SCENARIOS]
    assert data["failed_runs"] == [] and data["driver"]["model"] is None
    assert data["summary"]["by_arm"]["runbook"]["spec"]["goal_success"]["n"] == 6
    assert len(set(r["log_path"] for r in data["records"])) == 6
    assert not os.path.exists(str(out) + ".tmp")


def test_existing_results_file_is_never_overwritten(tmp_path):
    out = tmp_path / "dev.json"
    out.write_text("evidence")
    with pytest.raises(SystemExit):
        drv.main(["--arm", "runbook", "--repeats", "1", "--out", str(out), "--runs-dir", str(tmp_path)])
    assert out.read_text() == "evidence"


def test_repeats_has_no_default_and_scenarios_are_dev_only(tmp_path):
    with pytest.raises(SystemExit):
        drv.main(["--arm", "runbook", "--out", str(tmp_path / "a.json")])
    with pytest.raises(SystemExit):
        drv.main(["--arm", "runbook", "--repeats", "1", "--out", str(tmp_path / "b.json"), "--scenarios", "nope"])


def test_exception_in_one_run_does_not_stop_others_and_is_kept(tmp_path, monkeypatch):
    def flaky(arm, scenario, repeat=1, runs_dir="runs"):
        if scenario.name == "dev_f2":
            raise RuntimeError("boom gsk_SHOULDNOTAPPEAR")
        if scenario.name == "dev_f4":  # partial log: GOAL written, then a crash
            lg = RunLogger(f"{arm}-{scenario.name}-s{scenario.seed}-r{repeat}-x", runs_dir)
            lg.log("GOAL", goal="g", eval={"scenario": scenario.name, "faults": scenario.faults, "arm": arm})
            lg.close()
            raise RuntimeError("crash mid-run")
        return real_run_arm(arm, scenario, repeat=repeat, runs_dir=runs_dir)

    monkeypatch.setattr(drv, "run_arm", flaky)
    code, out = _run(tmp_path, "--scenarios", "hero,dev_f2,dev_f4,dev_f7")
    data = json.loads(out.read_text())
    assert code == 1
    assert [r["scenario"] for r in data["records"]] == ["hero", "dev_f4", "dev_f7"]
    partial = data["records"][1]
    assert partial["driver_status"]["incomplete"] is True
    assert partial["metrics"]["spec"]["goal_success"] is False
    assert [f["scenario"] for f in data["failed_runs"]] == ["dev_f2"]
    assert "gsk_SHOULDNOTAPPEAR" not in out.read_text()
    assert data["summary"]["by_arm"]["runbook"]["n_runs"] == 3
