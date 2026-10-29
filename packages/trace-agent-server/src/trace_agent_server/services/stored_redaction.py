"""Copies of a model turn with the sensitive keys of each tool masked, for what the server stores.

The provider and the agent still get the real data; only what is saved (events, turns) is masked.
A tool names its sensitive keys with ``redact_fields``; they apply to that tool's arguments and result.
"""

from __future__ import annotations

import json
from typing import Any

from trace_agent_sdk.redaction import redact_keys


def _redact_json_text(text: Any, fields: list[str]) -> Any:
    if not fields or not isinstance(text, str):
        return text
    try:
        parsed = json.loads(text)
    except ValueError:
        return text
    return json.dumps(redact_keys(parsed, fields), ensure_ascii=False)


def redact_messages(messages: list[dict[str, Any]], tool_redaction: dict[str, list[str]]) -> list[dict[str, Any]]:
    """The conversation with the arguments and results of each tool masked."""
    if not any(tool_redaction.values()):
        return messages

    tool_names: dict[str, str] = {}
    for message in messages:
        for call in message.get("tool_calls") or []:
            tool_names[str(call.get("id"))] = str((call.get("function") or {}).get("name"))

    redacted: list[dict[str, Any]] = []
    for message in messages:
        message = dict(message)
        if message.get("role") == "tool":
            fields = tool_redaction.get(tool_names.get(str(message.get("tool_call_id")), ""), [])
            message["content"] = _redact_json_text(message.get("content"), fields)
        if message.get("tool_calls"):
            calls = []
            for call in message["tool_calls"]:
                function = dict(call.get("function") or {})
                function["arguments"] = _redact_json_text(function.get("arguments"), tool_redaction.get(str(function.get("name")), []))
                calls.append({**call, "function": function})
            message["tool_calls"] = calls
        redacted.append(message)
    return redacted


def redact_tool_calls(tool_calls: list[dict[str, Any]], tool_redaction: dict[str, list[str]]) -> list[dict[str, Any]]:
    """Tool calls ({"name", "arguments", ...}) with the arguments of each tool masked."""
    return [
        {**call, "arguments": redact_keys(call.get("arguments"), tool_redaction.get(str(call.get("name")), []))}
        for call in tool_calls
    ]
