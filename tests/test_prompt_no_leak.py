"""Prompt content, tool schema, plan validation, and the SPEC §4 no-leak test. Offline; no LLM.

No-leak design: the forbidden terms are derived at test time from SPEC.md's public fault table
(rows whose set column says held-out), so no held-out name or parameter is copied into this file.
Terms that also occur in development rows, and the four SPEC §3 run_task names (approved for the
tool enum), are excluded so legitimate generic wording and approved task names are not rejected.
Only agent-visible text is checked: system prompt, goal, nudge, tool and field descriptions.
"""
import hashlib
import os
import re

from langchain_core.utils.function_calling import convert_to_openai_tool

from nidaan.logger import RunLogger
from nidaan.prompt import GOAL, NUDGE, SYSTEM_PROMPT
from nidaan.tools import RUN_TASKS, ToolExecutor, build_langchain_tools
from settlesim.generator import generate
from settlesim.tools import SettleSimTools

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Recorded in PROGRESS.md. Any prompt edit must update this value deliberately (prompt-freeze guard).
PROMPT_SHA256 = "812cea1728f60b36b4ab1eb5451a4eca92e5c90688679d0f567a0adb1084165d"


# ---- prompt content -------------------------------------------------------
SPEC4_PRINCIPLES = (  # SPEC §4 prompt principles, as worded in the prompt
    "Assess the situation before acting",
    "Collect evidence that distinguishes between competing explanations before choosing a fix",
    "from observations; never guess them",
    "Inspect state before any operation that cannot be undone",
    "Prefer minimal, reversible changes",
    "call update_plan with a changed step list, citing in triggered_by",
    "Stop only when check_pipeline confirms the goal",
    "Report only actions you actually performed",
)
CHANGE_1 = ("Take configuration keys and values from observations; never guess them. Use only a key you have seen "
            "for that component, and when a result lists which keys, tasks or targets are valid, use that list "
            "instead of guessing.")
CHANGE_2 = ("If an action is rejected, does not produce the expected effect, or reveals a failure you did not "
            "anticipate, treat that result as the trigger for your next decision: reassess your hypothesis and call "
            "update_plan with a changed step list, citing in triggered_by the event numbers of the results that "
            "prompted it",
            "A rejected action changed nothing. Read its message, and do not try different guesses against the same "
            "component without relevant new evidence.")
CHANGE_3 = ("After an action that may have resolved a problem, obtain a fresh observation to check the current state. "
            "Before retrying an operation with side effects, inspect its status and determine whether retrying is "
            "safe. Then resume the required operation if appropriate and confirm the overall goal using "
            "check_pipeline. Historical logs alone do not prove that a recovery attempt succeeded.")


def test_prompt_hash_is_recorded():
    assert hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest() == PROMPT_SHA256


def test_all_spec4_principles_and_the_three_changes_are_present():
    for p in SPEC4_PRINCIPLES + (CHANGE_1, CHANGE_3) + CHANGE_2:
        assert p in SYSTEM_PROMPT, p


def test_replan_after_failure_is_unconditional():
    # SPEC §4: "reconsider the hypothesis and update the plan, citing the observation" - no condition attached.
    assert "When it changes your current hypothesis" not in SYSTEM_PROMPT
    assert "reassess your hypothesis and call update_plan" in SYSTEM_PROMPT


def test_prompt_hardcodes_no_mode_sequence_or_config_key():
    # Change 3 must stay generic: no settlement mode, tool sequence, or settable key named.
    for banned in ("get_batch_status", "'resume'", "'full'", "mode=", "run_settlement(", "key_in_use",
                   "max_concurrency", "credential"):
        assert banned not in SYSTEM_PROMPT, banned


# ---- tool schema ------------------------------------------------------------
def _tools():
    return {t["function"]["name"]: t["function"] for t in map(convert_to_openai_tool, build_langchain_tools())}


EXPECTED_PROPS = {
    "update_plan": ["reason", "steps", "triggered_by"], "check_pipeline": ["why"],
    "inspect": ["component", "why"], "read_logs": ["component", "grep", "n", "why"],
    "get_batch_status": ["why"], "restart": ["component", "why"],
    "set_config": ["component", "key", "value", "why"], "run_task": ["component", "task", "why"],
    "run_settlement": ["mode", "why"],
    "submit_incident_report": ["actions", "root_causes", "status_claimed", "summary"],
}


def test_tool_schema_unchanged():
    tools = _tools()
    assert set(tools) == set(EXPECTED_PROPS)
    for name, props in EXPECTED_PROPS.items():
        assert sorted(tools[name]["parameters"]["properties"]) == props, name
    p = tools["run_task"]["parameters"]["properties"]
    assert p["task"]["enum"] == list(RUN_TASKS) and len(RUN_TASKS) == 4
    assert p["component"]["enum"] == ["ledger", "worker", "bank", "settlement"]
    assert tools["run_settlement"]["parameters"]["properties"]["mode"]["enum"] == ["resume", "full"]


def test_set_config_description_matches_simulator_behaviour():
    desc = _tools()["set_config"]["description"]
    assert "rejecting an unknown key lists the keys that can be set" in desc
    res = SettleSimTools(generate(11, ["F2"])).set_config(component="bank", key="no_such_key", value="1", why="w")
    assert res.outcome == "rejected" and "settable:" in res.text


# ---- plan validation (rules unchanged; rejected ACT is a valid citation) ----
def test_replan_may_cite_a_rejected_action(tmp_path):
    lg = RunLogger("t", str(tmp_path))
    ex = ToolExecutor(SettleSimTools(generate(11, ["F2"])), lg)
    meta = {"llm_call": 1}
    assert "accepted" in ex.execute("update_plan", {"steps": ["a"], "reason": "r", "triggered_by": []}, meta)
    out = ex.execute("set_config", {"component": "settlement", "key": "no_such_key", "value": "1", "why": "w"}, meta)
    seq = int(out[1:out.index("]")])
    assert lg.events[-1]["type"] == "ACT" and lg.events[-1]["outcome"] == "rejected"
    ok = ex.execute("update_plan", {"steps": ["b"], "reason": "rejected", "triggered_by": [seq]}, meta)
    assert "accepted" in ok and lg.events[-1]["plan_version"] == 2
    noop = ex.execute("update_plan", {"steps": ["b"], "reason": "same", "triggered_by": [seq]}, meta)
    assert lg.events[-1]["outcome"] == "rejected", noop  # existing rules still apply (stale/no-op)


# ---- no-leak ------------------------------------------------------------------
IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
GENERIC = {"abs", "URL"}  # SPEC table notation, not fault-specific


def _fault_rows():
    rows = []
    for line in open(os.path.join(ROOT, "SPEC.md"), encoding="utf-8"):
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 7 and re.match(r"F\d ", cells[0]):
            rows.append(cells)
    return rows


def _terms(row):
    """Distinctive terms of one fault row: its name phrase, identifiers inside backticks of the condition and
    fix columns, and 3-digit status/threshold numbers anywhere in the row."""
    name = row[0].split(" ", 1)[1].lower()
    ticks = " ".join(re.findall(r"`([^`]*)`", row[2] + " " + row[5]))
    idents = {t for t in IDENT.findall(ticks)}
    nums = set(re.findall(r"\b\d{3}\b", " ".join(row)))
    return {("phrase", name)} | {("word", t) for t in idents | nums}


def held_out_terms():
    rows = _fault_rows()
    held = [r for r in rows if "held-out" in r[1]]
    dev_words = {t for r in rows if "held-out" not in r[1] for k, t in _terms(r) if k == "word"}
    allowed = dev_words | set(RUN_TASKS) | GENERIC
    per_row = [{(k, t) for k, t in _terms(r) if k == "phrase" or t not in allowed} for r in held]
    return held, per_row


def agent_visible_texts():
    texts = {"system_prompt": SYSTEM_PROMPT, "goal": GOAL, "nudge": NUDGE}

    def walk(node, path):
        if isinstance(node, dict):
            for k, v in node.items():
                if k == "description" and isinstance(v, str):
                    texts[path] = v
                elif k != "enum":  # enum values are the approved schema, checked in test_tool_schema_unchanged
                    walk(v, f"{path}.{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]")

    for name, fn in _tools().items():
        texts[f"tool:{name}"] = fn["description"]
        walk(fn["parameters"], f"tool:{name}.parameters")
    return texts


def leaks(text: str, terms) -> list[str]:
    found = []
    for kind, t in terms:
        pat = re.escape(t) if kind == "phrase" else rf"(?<![A-Za-z0-9_]){re.escape(t)}(?![A-Za-z0-9_])"
        if re.search(pat, text, re.I if kind == "phrase" else 0):
            found.append(t)
    return found


def test_held_out_terms_parse_from_spec():
    held, per_row = held_out_terms()
    assert len(held) == 3  # SPEC §2: three held-out fault types
    assert all(any(k == "word" for k, _ in row) for row in per_row)  # each row yields distinctive identifiers


def test_detector_flags_injected_terms_and_spares_generic_text():
    _, per_row = held_out_terms()
    terms = set().union(*per_row)
    for kind, t in terms:  # every derived term is caught when present (terms come from SPEC, not this file)
        assert leaks(f"Please check the {t} value.", terms)
    generic = ("Inspect the component, read its logs, and run the maintenance task the result lists as valid. "
               "Use rotate_credential or rotate_logs only when evidence supports it. Every why is <= 25 words.")
    assert leaks(generic + " " + " ".join(RUN_TASKS), terms) == []


def test_no_held_out_terms_in_agent_visible_text():
    _, per_row = held_out_terms()
    terms = set().union(*per_row)
    hits = {where: leaks(text, terms) for where, text in agent_visible_texts().items()}
    assert {w: h for w, h in hits.items() if h} == {}


def test_no_scenario_values_or_fault_ids_in_agent_visible_text():
    patterns = (r"\bF[1-8]\b", r"key-[a-z0-9]{6}", r"cred-[a-z0-9]{4}", r"https?://", r"\bPO-\d+",
                r"(?<![\w.])\d{3,}(?![\w.])")
    for where, text in agent_visible_texts().items():
        for p in patterns:
            assert not re.search(p, text), (where, p)


# ---- report schema guidance (root-cause attribution) --------------------------------------------
def test_report_schema_tells_the_model_what_a_root_cause_component_is():
    # Regression for the revision-2 hero report (runs/nidaan-hero-s323-r1-20261010T171521075447.jsonl, VERIFY #37):
    # the credential cause was attributed to the component where the symptom appeared, and a corrected problem was
    # omitted. The schema fields are unchanged (SPEC §5); only their descriptions are added.
    params = _tools()["submit_incident_report"]["parameters"]
    root_causes = params["properties"]["root_causes"]
    assert "including problems already corrected" in root_causes["description"]
    item = root_causes["items"]
    rc = item if "properties" in item else params["$defs"][item["$ref"].split("/")[-1]]
    assert sorted(rc["properties"]) == ["component", "description", "evidence"]
    assert "not the component where the symptom was observed" in rc["properties"]["component"]["description"]
    assert rc["properties"]["component"]["enum"] == ["ledger", "worker", "bank", "settlement"]
    assert "only as far as your observations support it" in rc["properties"]["description"]["description"]
