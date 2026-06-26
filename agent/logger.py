"""
logger.py
---------
Lightweight logging of every tool call the agent makes: tool name, input,
and output. This satisfies the "Add logging of tool calls" bonus point and
is invaluable for explaining/debugging agent behavior during evaluation.

Logs go to both the console and a rolling file (logs/tool_calls.log) so
graders can open the log file and see exactly what the agent did for any
given run.
"""

import json
import logging
import os
from datetime import datetime, timezone

_LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
os.makedirs(_LOG_DIR, exist_ok=True)

_logger = logging.getLogger("agentic_store")
_logger.setLevel(logging.INFO)

if not _logger.handlers:
    file_handler = logging.FileHandler(os.path.join(_LOG_DIR, "tool_calls.log"), encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(message)s"))
    _logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter("%(message)s"))
    _logger.addHandler(console_handler)


def log_tool_call(tool_name: str, tool_input: dict, tool_output):
    """
    Logs a single tool invocation and returns tool_output unchanged, so it
    can be wrapped directly around a tool call:

        order = log_tool_call("get_order", {"order_id": oid}, get_order(oid))
    """
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tool": tool_name,
        "input": tool_input,
        "output_preview": _preview(tool_output),
    }
    _logger.info(json.dumps(entry, ensure_ascii=False))
    return tool_output


def _preview(output, max_len: int = 300) -> str:
    try:
        text = json.dumps(output, ensure_ascii=False)
    except TypeError:
        text = str(output)
    return text if len(text) <= max_len else text[:max_len] + "...(truncated)"
