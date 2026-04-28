from __future__ import annotations

import hashlib
import json
from typing import Any


def stable_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def redact_payload(value: Any, redact_fields: list[str] | None = None) -> Any:
    redact_fields = set(redact_fields or [])
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, inner in value.items():
            if key in redact_fields:
                redacted[key] = "[redacted]"
            else:
                redacted[key] = redact_payload(inner, list(redact_fields))
        return redacted
    if isinstance(value, list):
        return [redact_payload(item, list(redact_fields)) for item in value]
    if isinstance(value, str):
        if len(value) <= 160:
            return value
        return f"{value[:157]}..."
    return value


def summarize_value(value: Any, redact_fields: list[str] | None = None, max_length: int = 220) -> str:
    redacted = redact_payload(value, redact_fields)
    if isinstance(redacted, str):
        return redacted
    rendered = json.dumps(redacted, ensure_ascii=True, sort_keys=True, default=str)
    if len(rendered) <= max_length:
        return rendered
    return f"{rendered[: max_length - 3]}..."
