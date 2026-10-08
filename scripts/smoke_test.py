"""Phase 0 smoke test: 3 dependent toy-tool calls over multiple turns.

Usage: python scripts/smoke_test.py [model_name]   (defaults to config.MODEL_NAME)
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI

import config

load_dotenv()

ACCOUNTS = {"acme": " mrc-0042 "}
FEES = {"MRC-0042": 0.025}


@tool
def lookup_account(name: str) -> str:
    """Look up the raw merchant code for an account name."""
    return ACCOUNTS.get(name.lower(), "unknown")


@tool
def normalize_code(code: str) -> str:
    """Normalize a raw merchant code into canonical form."""
    return code.strip().upper()


@tool
def compute_fee(normalized_code: str, amount: float) -> float:
    """Compute the fee for a canonical merchant code and an amount."""
    return round(FEES[normalized_code] * amount, 2)


TOOLS = {t.name: t for t in (lookup_account, normalize_code, compute_fee)}
PROMPT = (
    "What is the fee for account 'acme' on an amount of 10000? Use the tools; "
    "call one tool at a time, and use each tool's output as input to the next. "
    "Give the final fee as a number."
)


def main(model_name: str) -> int:
    llm = ChatGoogleGenerativeAI(model=model_name, temperature=config.TEMPERATURE,
                                 max_retries=2).bind_tools(list(TOOLS.values()))
    messages = [HumanMessage(PROMPT)]
    calls, tool_calls_made, latencies, tokens = 0, [], [], []
    for _ in range(8):
        t0 = time.perf_counter()
        resp = llm.invoke(messages)
        latencies.append(time.perf_counter() - t0)
        calls += 1
        tokens.append(getattr(resp, "usage_metadata", None))
        messages.append(resp)
        if not resp.tool_calls:
            break
        for tc in resp.tool_calls:
            result = TOOLS[tc["name"]].invoke(tc["args"])
            tool_calls_made.append((tc["name"], tc["args"], result))
            messages.append(ToolMessage(content=str(result), tool_call_id=tc["id"], name=tc["name"]))

    text = resp.text  # content may be a list of blocks (with thought signatures)
    print(f"model: {model_name}")
    for i, (n, a, r) in enumerate(tool_calls_made, 1):
        print(f"  tool call {i}: {n}({a}) -> {r!r}")
    print(f"final answer: {text.strip()[:200]}")
    print(f"LLM calls: {calls}")
    for i, (lat, tk) in enumerate(zip(latencies, tokens), 1):
        tk_s = (f"in={tk.get('input_tokens')} out={tk.get('output_tokens')} total={tk.get('total_tokens')}"
                if tk else "unavailable")
        print(f"  call {i}: latency={lat:.2f}s tokens: {tk_s}")
    print(f"total latency: {sum(latencies):.2f}s")
    if all(tokens):
        print(f"total tokens: {sum(t.get('total_tokens', 0) for t in tokens)}")
    else:
        print("total tokens: unavailable")

    names = [n for n, _, _ in tool_calls_made]
    ok = names[:3] == ["lookup_account", "normalize_code", "compute_fee"] and "250" in text
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else config.MODEL_NAME))
