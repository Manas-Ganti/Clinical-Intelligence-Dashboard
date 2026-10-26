"""Measure the tokens one list_alerts tool result costs, before and after the row cap.

    python scripts/measure_tool_tokens.py

Runs the tool call behind "Show me all the critical alerts" (list_alerts,
severity=critical) against the DB that DATABASE_URL points at, serializes each
result exactly as both providers send it to the model
(json.dumps(result, default=str), backend/llm/providers.py), and counts tokens.
No LLM call is made.

Four variants:
  pre-cap      the tool as it was before the cap (commit aaaf578): every matching
               row, as {"alerts": [...]}, no count fields
  cap off      today's code with MAX_TOOL_ROWS patched out in-process, the model
               asking for every row; isolates the cap from the added count fields
  cap, default today's code, model passes no limit (list_alerts default = 50)
  cap, max     today's code, model asks for more than the cap (clamped to 100)

The patch in "cap off" lives only in this process; application code is untouched.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import structlog
import tiktoken

from backend.config import DATABASE_URL
from backend.db import SessionLocal
from backend.llm import tools
from backend.services import alert_service

# o200k_harmony is gpt-oss's own tokenizer (the default LLM_MODEL here);
# cl100k_base is the common reference point. Claude's tokenizer is not public.
ENCODINGS = ("o200k_harmony", "cl100k_base")
TOOL_INPUT = {"severity": "critical"}


def serialize(result: dict) -> str:
    """Byte-for-byte what providers.py puts in the tool-result message."""
    return json.dumps(result, default=str)


def pre_cap(db) -> dict:
    """list_alerts as implemented at commit aaaf578, before the cap existed."""
    rows = [
        a
        for a in alert_service.list_alerts(db)
        if a.severity.value == TOOL_INPUT["severity"]
    ]
    return {"alerts": [tools._alert_brief(a) for a in rows]}


def cap_off(db) -> dict:
    saved = tools.MAX_TOOL_ROWS
    tools.MAX_TOOL_ROWS = 10**9
    try:
        return tools.execute_tool(db, "list_alerts", {**TOOL_INPUT, "limit": 10**9})
    finally:
        tools.MAX_TOOL_ROWS = saved


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(40))
    encs = {name: tiktoken.get_encoding(name) for name in ENCODINGS}

    db = SessionLocal()
    try:
        variants = [
            ("pre-cap (aaaf578)", pre_cap(db)),
            ("cap off (patched)", cap_off(db)),
            ("cap, default limit", tools.execute_tool(db, "list_alerts", TOOL_INPUT)),
            (
                "cap, max limit",
                tools.execute_tool(db, "list_alerts", {**TOOL_INPUT, "limit": 10**9}),
            ),
        ]
    finally:
        db.close()

    print(f"\n  DATABASE_URL:  {DATABASE_URL}")
    print(f"  tool call:     list_alerts {json.dumps(TOOL_INPUT)}")
    print(f"  MAX_TOOL_ROWS: {tools.MAX_TOOL_ROWS}  tiktoken {tiktoken.__version__}\n")
    header = f"  {'variant':<20} {'rows':>5} {'total_matching':>14} {'chars':>8}"
    header += "".join(f" {name:>14}" for name in ENCODINGS)
    print(header)
    print("  " + "-" * (len(header) - 2))
    for label, result in variants:
        text = serialize(result)
        rows = len(result["alerts"])
        total = result.get("total_matching", "n/a")
        line = f"  {label:<20} {rows:>5} {total!s:>14} {len(text):>8}"
        line += "".join(f" {len(enc.encode(text)):>14,}" for enc in encs.values())
        print(line)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
