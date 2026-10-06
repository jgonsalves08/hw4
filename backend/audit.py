"""Append-only audit trail of agent-loop activity: output/audit_trail.json.

Every chat message the agent handles adds one entry: when it ran, who it was
for (customer id or guest, never an email), every tool call with short
args/results, and why the loop stopped. Entries are only ever appended; the
file is never cleared between runs or server restarts.
"""

import fcntl
import json
import os
import threading
from datetime import UTC, datetime
from pathlib import Path

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    ToolCallPart,
    ToolReturnPart,
)

from safety import redact

AUDIT_PATH = Path(
    os.environ.get("AUDIT_TRAIL_PATH", Path(__file__).resolve().parent.parent / "output" / "audit_trail.json")
)
SHORT_LIMIT = 200  # characters kept from each arg/result
# The tool PydanticAI uses to return the structured ShopReply.
OUTPUT_TOOL = "final_result"

_lock = threading.Lock()


def short(value: object, limit: int = SHORT_LIMIT) -> str:
    """Compact, redacted, length-capped text for the log."""
    text = value if isinstance(value, str) else json.dumps(value, default=str, ensure_ascii=False)
    text = redact(" ".join(text.split()))
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _iso(dt: datetime | None) -> str | None:
    return dt.astimezone(UTC).isoformat(timespec="milliseconds") if dt else None


def loop_events(messages: list[ModelMessage]) -> list[dict]:
    """Turn one run's messages into a timeline of tool calls, results, and retries."""
    events: list[dict] = []
    for msg in messages:
        if isinstance(msg, ModelResponse):
            for part in msg.parts:
                if isinstance(part, ToolCallPart):
                    events.append(
                        {
                            "time": _iso(msg.timestamp),
                            "type": "final_output" if part.tool_name == OUTPUT_TOOL else "tool_call",
                            "tool": part.tool_name,
                            "args": short(part.args_as_dict()),
                        }
                    )
        elif isinstance(msg, ModelRequest):
            for part in msg.parts:
                if isinstance(part, ToolReturnPart) and part.tool_name != OUTPUT_TOOL:
                    events.append(
                        {
                            "time": _iso(part.timestamp),
                            "type": "tool_result",
                            "tool": part.tool_name,
                            "result": short(part.model_response_str()),
                        }
                    )
                elif isinstance(part, RetryPromptPart):
                    events.append(
                        {
                            "time": _iso(part.timestamp),
                            "type": "retry",
                            "tool": part.tool_name,
                            "result": short(part.model_response()),
                        }
                    )
    return events


def model_finish_reason(messages: list[ModelMessage]) -> str | None:
    for msg in reversed(messages):
        if isinstance(msg, ModelResponse):
            return msg.finish_reason
    return None


def append_entry(entry: dict) -> None:
    """Append one entry, keeping the file a valid JSON list. Never truncates history."""
    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _lock, open(AUDIT_PATH.with_name(".audit_trail.lock"), "w") as lock_file:
        # File lock as well, in case two server processes write at once.
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        entries: list = []
        if AUDIT_PATH.exists() and AUDIT_PATH.stat().st_size > 0:
            try:
                entries = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
                if not isinstance(entries, list):
                    raise ValueError("audit trail is not a list")
            except ValueError:
                # Never overwrite a damaged log: keep it under a new name and start fresh.
                stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
                AUDIT_PATH.rename(AUDIT_PATH.with_name(f"audit_trail.corrupt-{stamp}.json"))
                entries = []
        entries.append(entry)
        tmp = AUDIT_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(entries, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(tmp, AUDIT_PATH)  # atomic: readers never see a half-written file
