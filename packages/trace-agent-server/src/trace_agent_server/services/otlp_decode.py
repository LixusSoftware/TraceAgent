"""Decode OTLP/HTTP trace exports (protobuf or JSON) into plain span records."""

from __future__ import annotations

import base64
import json
import zlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
from opentelemetry.proto.common.v1.common_pb2 import AnyValue, KeyValue
from opentelemetry.proto.trace.v1.trace_pb2 import Status

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
_STATUS_NAMES = {code: name.removeprefix("STATUS_CODE_") for name, code in Status.StatusCode.items()}


class OtlpDecodeError(ValueError):
    """The request body is not a valid OTLP trace export."""


class BodyTooLarge(OtlpDecodeError):
    """The (decompressed) request body is over the configured limit."""


@dataclass
class SpanEventRecord:
    name: str
    time: datetime
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class SpanRecord:
    trace_id: str
    span_id: str
    parent_span_id: str | None
    name: str
    start: datetime
    end: datetime
    status_code: str  # UNSET, OK or ERROR
    status_message: str | None
    attributes: dict[str, Any]
    events: list[SpanEventRecord]
    resource: dict[str, Any]
    scope: str | None

    @property
    def duration_ms(self) -> int:
        return max(0, int((self.end - self.start).total_seconds() * 1000))


def _from_unix_nano(value: int | str) -> datetime:
    # Integer arithmetic: float seconds cannot hold nanosecond timestamps exactly.
    return _EPOCH + timedelta(microseconds=int(value) // 1000)


def decompress(body: bytes, encoding: str | None, limit: int) -> bytes:
    """Undo ``Content-Encoding`` without ever producing more than ``limit`` bytes."""
    encoding = (encoding or "").strip().lower()
    if encoding in ("", "identity"):
        data = body
    elif encoding in ("gzip", "deflate"):
        # wbits 47 auto-detects the gzip and zlib headers.
        inflater = zlib.decompressobj(wbits=47)
        try:
            data = inflater.decompress(body, limit + 1)
        except zlib.error as exc:
            raise OtlpDecodeError(f"Invalid {encoding} body: {exc}") from exc
    else:
        raise OtlpDecodeError(f"Unsupported Content-Encoding '{encoding}'.")
    if len(data) > limit:
        raise BodyTooLarge(f"Request body is over {limit} bytes.")
    return data


# ── Protobuf ─────────────────────────────────────────────────────────────────


def _any_value(value: AnyValue) -> Any:
    kind = value.WhichOneof("value")
    if kind is None:
        return None
    if kind == "array_value":
        return [_any_value(item) for item in value.array_value.values]
    if kind == "kvlist_value":
        return _attributes(value.kvlist_value.values)
    return getattr(value, kind)


def _attributes(items: Any) -> dict[str, Any]:
    return {item.key: _any_value(item.value) for item in items}


def decode_protobuf(body: bytes) -> list[SpanRecord]:
    request = ExportTraceServiceRequest()
    try:
        request.ParseFromString(body)
    except Exception as exc:  # google.protobuf raises DecodeError, but also others on junk
        raise OtlpDecodeError(f"Invalid OTLP protobuf body: {exc}") from exc

    spans: list[SpanRecord] = []
    for resource_spans in request.resource_spans:
        resource = _attributes(resource_spans.resource.attributes)
        for scope_spans in resource_spans.scope_spans:
            scope = scope_spans.scope.name or None
            for span in scope_spans.spans:
                spans.append(
                    SpanRecord(
                        trace_id=span.trace_id.hex(),
                        span_id=span.span_id.hex(),
                        parent_span_id=span.parent_span_id.hex() or None,
                        name=span.name,
                        start=_from_unix_nano(span.start_time_unix_nano),
                        end=_from_unix_nano(span.end_time_unix_nano),
                        status_code=_STATUS_NAMES.get(span.status.code, "UNSET"),
                        status_message=span.status.message or None,
                        attributes=_attributes(span.attributes),
                        events=[
                            SpanEventRecord(event.name, _from_unix_nano(event.time_unix_nano), _attributes(event.attributes))
                            for event in span.events
                        ],
                        resource=resource,
                        scope=scope,
                    )
                )
    return spans


# ── JSON ─────────────────────────────────────────────────────────────────────


def _json_any_value(value: dict[str, Any]) -> Any:
    if "stringValue" in value:
        return value["stringValue"]
    if "boolValue" in value:
        return value["boolValue"]
    if "intValue" in value:
        return int(value["intValue"])  # 64-bit integers are strings in OTLP/JSON
    if "doubleValue" in value:
        return float(value["doubleValue"])
    if "arrayValue" in value:
        return [_json_any_value(item) for item in value["arrayValue"].get("values", [])]
    if "kvlistValue" in value:
        return _json_attributes(value["kvlistValue"].get("values", []))
    if "bytesValue" in value:
        return base64.b64decode(value["bytesValue"])
    return None


def _json_attributes(items: list[dict[str, Any]] | None) -> dict[str, Any]:
    return {item["key"]: _json_any_value(item.get("value", {})) for item in items or []}


def _json_status_code(value: Any) -> str:
    if isinstance(value, int):
        return _STATUS_NAMES.get(value, "UNSET")
    return str(value or "UNSET").removeprefix("STATUS_CODE_")


def _json_id(value: str | None) -> str | None:
    # OTLP/JSON carries trace and span ids as hex strings, unlike plain protobuf JSON.
    return value.lower() if value else None


def decode_json(body: bytes) -> list[SpanRecord]:
    try:
        payload = json.loads(body)
        spans: list[SpanRecord] = []
        for resource_spans in payload.get("resourceSpans", []):
            resource = _json_attributes(resource_spans.get("resource", {}).get("attributes"))
            for scope_spans in resource_spans.get("scopeSpans", []):
                scope = scope_spans.get("scope", {}).get("name") or None
                for span in scope_spans.get("spans", []):
                    status = span.get("status", {})
                    spans.append(
                        SpanRecord(
                            trace_id=_json_id(span["traceId"]) or "",
                            span_id=_json_id(span["spanId"]) or "",
                            parent_span_id=_json_id(span.get("parentSpanId")),
                            name=span.get("name", ""),
                            start=_from_unix_nano(span.get("startTimeUnixNano", 0)),
                            end=_from_unix_nano(span.get("endTimeUnixNano", 0)),
                            status_code=_json_status_code(status.get("code")),
                            status_message=status.get("message") or None,
                            attributes=_json_attributes(span.get("attributes")),
                            events=[
                                SpanEventRecord(
                                    event.get("name", ""),
                                    _from_unix_nano(event.get("timeUnixNano", 0)),
                                    _json_attributes(event.get("attributes")),
                                )
                                for event in span.get("events", [])
                            ],
                            resource=resource,
                            scope=scope,
                        )
                    )
        return spans
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise OtlpDecodeError(f"Invalid OTLP JSON body: {exc}") from exc


def decode_traces(body: bytes, content_type: str | None) -> list[SpanRecord]:
    """Decode a request body according to its media type (protobuf by default)."""
    media_type = (content_type or "").split(";")[0].strip().lower()
    if media_type == "application/json":
        return decode_json(body)
    if media_type in ("", "application/x-protobuf", "application/protobuf"):
        return decode_protobuf(body)
    raise OtlpDecodeError(f"Unsupported Content-Type '{media_type}'.")
