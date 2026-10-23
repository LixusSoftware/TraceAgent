from __future__ import annotations

import gzip
import json
import zlib
from datetime import datetime, timezone

import pytest
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
from opentelemetry.proto.common.v1.common_pb2 import AnyValue, ArrayValue, KeyValue, KeyValueList
from opentelemetry.proto.trace.v1.trace_pb2 import Status

from trace_agent_server.services.otlp_decode import (
    BodyTooLarge,
    OtlpDecodeError,
    decode_json,
    decode_protobuf,
    decode_traces,
    decompress,
)

TRACE_ID = bytes.fromhex("0af7651916cd43dd8448eb211c80319c")
SPAN_ID = bytes.fromhex("b7ad6b7169203331")
PARENT_ID = bytes.fromhex("00f067aa0ba902b7")
START_NS = 1_760_000_000_123_456_789
END_NS = START_NS + 2_500_000_000


def kv(key: str, **value) -> KeyValue:
    return KeyValue(key=key, value=AnyValue(**value))


def build_request() -> ExportTraceServiceRequest:
    request = ExportTraceServiceRequest()
    resource_spans = request.resource_spans.add()
    resource_spans.resource.attributes.append(kv("service.name", string_value="weather-agent"))
    scope_spans = resource_spans.scope_spans.add()
    scope_spans.scope.name = "pydantic-ai"
    span = scope_spans.spans.add()
    span.trace_id, span.span_id, span.parent_span_id = TRACE_ID, SPAN_ID, PARENT_ID
    span.name = "execute_tool get_weather"
    span.start_time_unix_nano, span.end_time_unix_nano = START_NS, END_NS
    span.status.code = Status.STATUS_CODE_ERROR
    span.status.message = "boom"
    span.attributes.extend(
        [
            kv("gen_ai.tool.name", string_value="get_weather"),
            kv("flag", bool_value=True),
            kv("count", int_value=7),
            kv("ratio", double_value=0.5),
            kv("names", array_value=ArrayValue(values=[AnyValue(string_value="a"), AnyValue(int_value=2)])),
            kv("nested", kvlist_value=KeyValueList(values=[kv("inner", string_value="x")])),
        ]
    )
    event = span.events.add()
    event.name = "exception"
    event.time_unix_nano = END_NS
    event.attributes.append(kv("exception.type", string_value="ValueError"))
    # A root span: no parent id at all.
    root = scope_spans.spans.add()
    root.trace_id, root.span_id = TRACE_ID, PARENT_ID
    root.name = "invoke_agent weather"
    root.start_time_unix_nano, root.end_time_unix_nano = START_NS, END_NS
    return request


class TestDecodeProtobuf:
    def test_decodes_a_span_with_every_attribute_type(self) -> None:
        spans = decode_protobuf(build_request().SerializeToString())

        span = spans[0]
        assert span.trace_id == "0af7651916cd43dd8448eb211c80319c"
        assert (span.span_id, span.parent_span_id) == ("b7ad6b7169203331", "00f067aa0ba902b7")
        assert span.name == "execute_tool get_weather"
        assert span.attributes == {
            "gen_ai.tool.name": "get_weather",
            "flag": True,
            "count": 7,
            "ratio": 0.5,
            "names": ["a", 2],
            "nested": {"inner": "x"},
        }
        assert (span.status_code, span.status_message) == ("ERROR", "boom")
        assert span.resource == {"service.name": "weather-agent"}
        assert span.scope == "pydantic-ai"

    def test_times_keep_their_precision_and_give_the_duration(self) -> None:
        span = decode_protobuf(build_request().SerializeToString())[0]

        assert span.start == datetime(2025, 10, 9, 8, 53, 20, 123456, tzinfo=timezone.utc)
        assert span.duration_ms == 2500

    def test_span_events_are_decoded(self) -> None:
        span = decode_protobuf(build_request().SerializeToString())[0]

        assert [(e.name, e.attributes) for e in span.events] == [("exception", {"exception.type": "ValueError"})]

    def test_a_missing_parent_is_none(self) -> None:
        assert decode_protobuf(build_request().SerializeToString())[1].parent_span_id is None

    def test_an_empty_export_decodes_to_no_spans(self) -> None:
        assert decode_protobuf(ExportTraceServiceRequest().SerializeToString()) == []

    def test_junk_is_rejected(self) -> None:
        with pytest.raises(OtlpDecodeError):
            decode_protobuf(b"\xff\xfe not protobuf")


def json_request() -> dict:
    return {
        "resourceSpans": [
            {
                "resource": {"attributes": [{"key": "service.name", "value": {"stringValue": "weather-agent"}}]},
                "scopeSpans": [
                    {
                        "scope": {"name": "pydantic-ai"},
                        "spans": [
                            {
                                "traceId": "0AF7651916CD43DD8448EB211C80319C",
                                "spanId": "b7ad6b7169203331",
                                "parentSpanId": "",
                                "name": "chat m",
                                "startTimeUnixNano": str(START_NS),
                                "endTimeUnixNano": str(END_NS),
                                "status": {"code": "STATUS_CODE_OK"},
                                "attributes": [
                                    {"key": "tokens", "value": {"intValue": "42"}},
                                    {"key": "ratio", "value": {"doubleValue": 0.25}},
                                    {"key": "ok", "value": {"boolValue": False}},
                                    {"key": "list", "value": {"arrayValue": {"values": [{"stringValue": "a"}]}}},
                                ],
                                "events": [{"name": "e", "timeUnixNano": str(END_NS), "attributes": []}],
                            }
                        ],
                    }
                ],
            }
        ]
    }


class TestDecodeJson:
    def test_decodes_hex_ids_string_integers_and_named_status(self) -> None:
        span = decode_json(json.dumps(json_request()).encode())[0]

        assert span.trace_id == "0af7651916cd43dd8448eb211c80319c"
        assert span.parent_span_id is None
        assert span.status_code == "OK"
        assert span.attributes == {"tokens": 42, "ratio": 0.25, "ok": False, "list": ["a"]}
        assert span.duration_ms == 2500
        assert span.resource == {"service.name": "weather-agent"}
        assert [e.name for e in span.events] == ["e"]

    def test_numeric_status_codes_are_understood(self) -> None:
        request = json_request()
        request["resourceSpans"][0]["scopeSpans"][0]["spans"][0]["status"] = {"code": 2, "message": "bad"}

        span = decode_json(json.dumps(request).encode())[0]

        assert (span.status_code, span.status_message) == ("ERROR", "bad")

    @pytest.mark.parametrize("body", [b"not json", b'{"resourceSpans": [{"scopeSpans": [{"spans": [{}]}]}]}', b'{"resourceSpans": 3}'])
    def test_malformed_bodies_are_rejected(self, body) -> None:
        with pytest.raises(OtlpDecodeError):
            decode_json(body)


class TestDecompress:
    def test_identity_passes_through(self) -> None:
        assert decompress(b"abc", None, 100) == b"abc"
        assert decompress(b"abc", "identity", 100) == b"abc"

    def test_gzip_and_deflate_are_undone(self) -> None:
        assert decompress(gzip.compress(b"hello"), "gzip", 100) == b"hello"
        assert decompress(zlib.compress(b"hello"), "deflate", 100) == b"hello"

    def test_a_decompression_bomb_is_stopped_at_the_limit(self) -> None:
        bomb = gzip.compress(b"\0" * 1_000_000)

        with pytest.raises(BodyTooLarge):
            decompress(bomb, "gzip", 1000)

    def test_an_oversized_plain_body_is_rejected(self) -> None:
        with pytest.raises(BodyTooLarge):
            decompress(b"x" * 11, None, 10)

    def test_corrupt_and_unsupported_encodings_are_rejected(self) -> None:
        with pytest.raises(OtlpDecodeError, match="Invalid gzip"):
            decompress(b"not gzip", "gzip", 100)
        with pytest.raises(OtlpDecodeError, match="Unsupported"):
            decompress(b"x", "br", 100)


class TestDecodeTraces:
    def test_dispatches_on_the_media_type(self) -> None:
        proto = build_request().SerializeToString()

        assert len(decode_traces(proto, "application/x-protobuf")) == 2
        assert len(decode_traces(proto, "application/x-protobuf; charset=utf-8")) == 2
        assert len(decode_traces(proto, None)) == 2
        assert len(decode_traces(json.dumps(json_request()).encode(), "application/json")) == 1

    def test_other_media_types_are_rejected(self) -> None:
        with pytest.raises(OtlpDecodeError, match="Unsupported Content-Type"):
            decode_traces(b"{}", "text/plain")
