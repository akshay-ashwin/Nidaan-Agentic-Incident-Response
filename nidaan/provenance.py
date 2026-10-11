"""Run provenance: which prompt and code produced a run log. Recorded once per run on the GOAL event.

Fields: prompt_sha256 (Nidaan SYSTEM_PROMPT), oneshot_prompt_sha256 (one-shot baseline SYSTEM_PROMPT),
git_commit, git_dirty, git_dirty_count (tracked + untracked changes; paths are not recorded),
code_sha256, provider, model.

code_sha256 covers exactly CODE_DIRS/**/*.py plus CODE_FILES (see below), hashed in sorted relative-path
order. Git is queried read-only (no optional index locks), with a timeout; any failure yields None.
Nothing here reads environment variables, .env, or API keys.
"""
from __future__ import annotations

import hashlib
import os
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CODE_DIRS = ("nidaan", "settlesim", "baselines", "evaluation")  # all *.py below these, recursively
CODE_FILES = ("config.py", "run.py")
GIT_TIMEOUT_S = 5


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def code_files(root: str = ROOT) -> list[str]:
    """Relative paths (with '/') of the hashed source files, sorted."""
    found = [f for f in CODE_FILES if os.path.isfile(os.path.join(root, f))]
    for d in CODE_DIRS:
        for dirpath, dirnames, filenames in os.walk(os.path.join(root, d)):
            dirnames[:] = sorted(x for x in dirnames if x != "__pycache__")
            found += [os.path.relpath(os.path.join(dirpath, f), root).replace(os.sep, "/")
                      for f in filenames if f.endswith(".py")]
    return sorted(found)


def code_sha256(root: str = ROOT) -> str:
    h = hashlib.sha256()
    for rel in code_files(root):
        with open(os.path.join(root, rel), "rb") as f:
            h.update(rel.encode("utf-8") + b"\0" + hashlib.sha256(f.read()).digest() + b"\n")
    return h.hexdigest()


def _git(root: str, *args: str) -> str | None:
    try:
        out = subprocess.run(["git", "-C", root, *args], capture_output=True, text=True, timeout=GIT_TIMEOUT_S,
                             env={"GIT_OPTIONAL_LOCKS": "0", "PATH": os.environ.get("PATH", "")})
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout if out.returncode == 0 else None


def prompt_hashes() -> dict:
    # Imported here, not at module level: baselines.oneshot imports nidaan.logger, which uses this module.
    from baselines.oneshot import SYSTEM_PROMPT as ONESHOT_PROMPT
    from nidaan.prompt import SYSTEM_PROMPT
    return {"prompt_sha256": _sha256(SYSTEM_PROMPT), "oneshot_prompt_sha256": _sha256(ONESHOT_PROMPT)}


def collect_base(root: str = ROOT) -> dict:
    """Everything except provider/model; computed once per run."""
    commit = _git(root, "rev-parse", "HEAD")
    status = _git(root, "status", "--porcelain=v1")
    n = None if status is None else sum(1 for line in status.splitlines() if line.strip())
    return {**prompt_hashes(),
            "git_commit": commit.strip() if commit else None,
            "git_dirty": None if n is None else n > 0,
            "git_dirty_count": n,
            "code_sha256": code_sha256(root)}


def model_fields(model_id: str | None) -> dict:
    """'groq:openai/gpt-oss-120b' -> provider 'groq'. None (no LLM, e.g. runbook) -> both None."""
    provider = model_id.split(":", 1)[0] if model_id and ":" in model_id else None
    return {"provider": provider, "model": model_id}


def collect(model_id: str | None, root: str = ROOT) -> dict:
    return {**collect_base(root), **model_fields(model_id)}
