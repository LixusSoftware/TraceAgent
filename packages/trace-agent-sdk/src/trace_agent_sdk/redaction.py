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


def redact_keys(value: Any, redact_fields: list[str] | None = None) -> Any:
    """Mask the value of every listed key, at any depth, and leave the rest exactly as it is.

    Unlike redact_payload it does not shorten long strings, so it is safe for copies that are
    stored in full.
    """
    fields = set(redact_fields or [])
    if not fields:
        return value
    if isinstance(value, dict):
        return {key: "[redacted]" if key in fields else redact_keys(inner, list(fields)) for key, inner in value.items()}
    if isinstance(value, list):
        return [redact_keys(item, list(fields)) for item in value]
    return value


def summarize_value(
    value: Any, redact_fields: list[str] | None = None, max_length: int = 220, *, sort_keys: bool = True
) -> str:
    """A short text for a value. Keys are sorted so equal values give equal summaries (arguments are compared);
    ``sort_keys=False`` keeps the order the data came in, for results people read (the decisive key may be last)."""
    redacted = redact_payload(value, redact_fields)
    if isinstance(redacted, str):
        return redacted
    # Keep accents and other non-ASCII text readable: the summary is shown to people as it is.
    rendered = json.dumps(redacted, ensure_ascii=False, sort_keys=sort_keys, default=str)
    if len(rendered) <= max_length:
        return rendered
    return f"{rendered[: max_length - 3]}..."
