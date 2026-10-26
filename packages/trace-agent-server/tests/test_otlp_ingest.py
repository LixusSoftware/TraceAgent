"""The OTLP receiver end to end: protobuf in over HTTP, runs and events out."""

from __future__ import annotations

import gzip
import json
import time
from datetime import datetime, timezone
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest, ExportTraceServiceResponse
from opentelemetry.proto.common.v1.common_pb2 import AnyValue, KeyValue
from opentelemetry.proto.trace.v1.trace_pb2 import Status

from trace_agent_server.config import Settings
from trace_agent_server.main import create_app
from trace_agent_server.models import Event, Run

TRACE = "0af7651916cd43dd8448eb211c80319c"
MS = 1_000_000
# Recent, like a real exporter's: the dashboard only looks at the last day.
T0 = (int(time.time()) - 300) * 1_000_000_000  # ns


def make_client(tmp_path, **settings) -> TestClient:
    config = Settings(database_url=f"sqlite:///{tmp_path / 'test.db'}", cors_origins=["http://localhost:5173"], **settings)
    return TestClient(create_app(config))


@pytest.fixture
def client(tmp_path) -> TestClient:
    return make_client(tmp_path)


def attr(key: str, value) -> KeyValue:
    if isinstance(value, bool):
        return KeyValue(key=key, value=AnyValue(bool_value=value))
    if isinstance(value, int):
        return KeyValue(key=key, value=AnyValue(int_value=value))
    return KeyValue(key=key, value=AnyValue(string_value=str(value)))


class Span:
    """A span to export; times are milliseconds after T0."""

    def __init__(self, name, span_id, start, end, *, parent=None, error=None, trace=TRACE, **attributes) -> None:
        self.name, self.span_id, self.start, self.end = name, span_id, start, end
        self.parent, self.error, self.trace = parent, error, trace
        self.attributes = attributes


def export(*spans: Span, resource: dict | None = None) -> bytes:
    request = ExportTraceServiceRequest()
    resource_spans = request.resource_spans.add()
    for key, value in {"service.name": "weather-service", **(resource or {})}.items():
        resource_spans.resource.attributes.append(attr(key, value))
    scope = resource_spans.scope_spans.add()
    for item in spans:
        span = scope.spans.add()
        span.trace_id = bytes.fromhex(item.trace)
        span.span_id = bytes.fromhex(item.span_id)
        if item.parent:
            span.parent_span_id = bytes.fromhex(item.parent)
        span.name = item.name
        span.start_time_unix_nano = T0 + item.start * MS
        span.end_time_unix_nano = T0 + item.end * MS
        span.attributes.extend(attr(k.replace("__", "."), v) for k, v in item.attributes.items())
        if item.error:
            span.status.code = Status.STATUS_CODE_ERROR
            span.status.message = item.error[1]
            event = span.events.add()
            event.name = "exception"
            event.time_unix_nano = span.end_time_unix_nano
            event.attributes.append(attr("exception.type", item.error[0]))
            event.attributes.append(attr("exception.message", item.error[1]))
    return request.SerializeToString()


def post(client: TestClient, body: bytes, **headers):
    headers.setdefault("content-type", "application/x-protobuf")
    return client.post("/v1/traces", content=body, headers=headers)


AGENT = "1111111111111111"
CHAT1, TOOL, CHAT2 = "2222222222222222", "3333333333333333", "4444444444444444"
CALL = "call-1"


def agent_spans(*, tool_error=None, agent_error=None, final="It is sunny.") -> list[Span]:
    gen = "gen_ai__"
    return [
        Span("invoke_agent weather", AGENT, 0, 100, error=agent_error, **{
            gen + "operation__name": "invoke_agent", gen + "agent__name": "weather", gen + "agent__call__id": CALL,
            gen + "aggregated_usage__input_tokens": 110, gen + "aggregated_usage__output_tokens": 16,
            **({"final_result": final} if final else {}),
        }),
        Span("chat m", CHAT1, 5, 30, parent=AGENT, **{
            gen + "operation__name": "chat", gen + "provider__name": "openai", gen + "request__model": "gpt-x",
            gen + "response__model": "gpt-x-2025", gen + "agent__call__id": CALL, gen + "agent__name": "weather",
            gen + "usage__input_tokens": 60, gen + "usage__output_tokens": 6,
            gen + "input__messages": json.dumps([{"role": "user", "parts": [{"type": "text", "content": "Weather in Madrid?"}]}]),
            gen + "output__messages": json.dumps([{"role": "assistant", "parts": [{"type": "tool_call", "id": "t1", "name": "get_weather", "arguments": {"city": "Madrid"}}]}]),
        }),
        Span("execute_tool get_weather", TOOL, 30, 40, parent=AGENT, error=tool_error, **{
            gen + "operation__name": "execute_tool", gen + "tool__name": "get_weather", gen + "tool__call__id": "t1",
            gen + "tool__call__arguments": json.dumps({"city": "Madrid"}), gen + "agent__call__id": CALL,
            **({} if tool_error else {gen + "tool__call__result": "Sunny, 23C"}),
        }),
        Span("chat m", CHAT2, 45, 90, parent=AGENT, **{
            gen + "operation__name": "chat", gen + "provider__name": "openai", gen + "request__model": "gpt-x",
            gen + "response__model": "gpt-x-2025", gen + "agent__call__id": CALL,
            gen + "usage__input_tokens": 50, gen + "usage__output_tokens": 10,
            gen + "output__messages": json.dumps([{"role": "assistant", "parts": [{"type": "text", "content": "It is sunny."}]}]),
        }),
    ]


def as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc)


def load(client: TestClient, run_id: str | None = None):
    run_id = run_id or str(UUID(hex=TRACE))
    with client.app.state.session_factory() as session:
        run = session.get(Run, run_id)
        events = session.query(Event).filter_by(run_id=run_id).order_by(Event.seq).all() if run else []
        if run:
            session.expunge(run)
        for event in events:
            session.expunge(event)
    return run, events


def types(events) -> list[str]:
    return [e.type for e in events]


class TestRunCreationAndMapping:
    def test_a_full_trace_becomes_a_completed_run(self, client) -> None:
        assert post(client, export(*agent_spans())).status_code == 200

        run, events = load(client)
        assert run.id == str(UUID(hex=TRACE))
        assert (run.agent_name, run.goal, run.status) == ("weather", "Weather in Madrid?", "completed")
        assert run.run_metadata["source"] == "otlp"
        assert run.run_metadata["service_name"] == "weather-service"
        assert run.final_output_summary == "It is sunny."
        assert types(events) == [
            "run.started", "chain.started", "llm.started", "llm.completed", "tool.started", "tool.succeeded",
            "llm.started", "llm.completed", "chain.completed", "run.completed",
        ]

    def test_usage_provider_model_and_tool_counters_land_on_the_run(self, client) -> None:
        post(client, export(*agent_spans()))

        run, _ = load(client)
        assert (run.provider, run.model) == ("openai", "gpt-x-2025")
        assert (run.total_prompt_tokens, run.total_completion_tokens) == (110, 16)
        assert (run.tool_count, run.error_count) == (1, 0)

    def test_events_carry_the_real_times_and_durations_of_the_spans(self, client) -> None:
        post(client, export(*agent_spans()))

        run, events = load(client)
        by_type = {}
        for event in events:
            by_type.setdefault(event.type, []).append(event)
        assert as_utc(run.started_at) == datetime.fromtimestamp(T0 / 1e9, tz=timezone.utc)
        assert as_utc(by_type["tool.started"][0].timestamp) == datetime.fromtimestamp((T0 + 30 * MS) / 1e9, tz=timezone.utc)
        assert by_type["tool.succeeded"][0].duration_ms == 10
        assert by_type["llm.completed"][0].duration_ms == 25
        assert by_type["chain.completed"][0].duration_ms == 100

    def test_children_hang_from_the_agent_span(self, client) -> None:
        post(client, export(*agent_spans()))

        _, events = load(client)
        children = [e for e in events if e.type.startswith(("llm.", "tool."))]
        assert {e.parent_step_id for e in children} == {AGENT}
        assert {e.step_id for e in events if e.type.startswith("tool.")} == {TOOL}

    def test_model_call_details_are_kept(self, client) -> None:
        post(client, export(*agent_spans()))

        _, events = load(client)
        completed = next(e for e in events if e.type == "llm.completed")
        assert (completed.provider, completed.model) == ("openai", "gpt-x-2025")
        assert completed.event_metadata["prompt_tokens"] == 60
        assert completed.event_metadata["requested_tools"] == ["get_weather"]

    def test_tool_arguments_and_result_are_recorded(self, client) -> None:
        post(client, export(*agent_spans()))

        _, events = load(client)
        started = next(e for e in events if e.type == "tool.started")
        succeeded = next(e for e in events if e.type == "tool.succeeded")
        assert started.tool_name == "get_weather"
        assert started.payload_full == {"args": {"city": "Madrid"}}
        assert succeeded.summary == "Sunny, 23C"

    def test_spans_delivered_in_any_order_are_replayed_chronologically(self, client) -> None:
        post(client, export(*reversed(agent_spans())))

        run, events = load(client)
        assert types(events)[:4] == ["run.started", "chain.started", "llm.started", "llm.completed"]
        assert run.status == "completed"

    def test_decisions_are_derived_when_the_run_ends(self, client) -> None:
        post(client, export(*agent_spans()))

        explanation = client.get(f"/api/runs/{UUID(hex=TRACE)}/explanation").json()
        assert [d["label"] for d in explanation["decisions"] if d["kind"] == "tool_choice"] == ["Selected get_weather"]

    def test_other_spans_are_ignored(self, client) -> None:
        body = export(Span("GET /ask", "5555555555555555", 0, 10, **{"http__method": "GET"}))

        assert post(client, body).status_code == 200
        assert load(client)[0] is None


class TestFailures:
    def test_a_failed_tool_and_run_are_recorded_with_their_error(self, client) -> None:
        spans = agent_spans(tool_error=("builtins.ConnectionError", "network unreachable"), agent_error=("builtins.ConnectionError", "network unreachable"), final=None)
        post(client, export(*spans))

        run, events = load(client)
        failed_tool = next(e for e in events if e.type == "tool.failed")
        assert (failed_tool.error_code, failed_tool.summary) == ("ConnectionError", "network unreachable")
        assert next(e for e in events if e.type == "chain.failed").error_code == "ConnectionError"
        assert (run.status, run.final_output_summary) == ("failed", "network unreachable")
        assert run.tool_count == 1
        assert run.error_count == 2  # the tool, and the run itself

    def test_a_failed_model_call_is_recorded_and_not_counted_as_usage(self, client) -> None:
        spans = agent_spans()
        spans[3] = Span("chat m", CHAT2, 45, 90, parent=AGENT, error=("openai.APIError", "rate limited"), **{
            "gen_ai__operation__name": "chat", "gen_ai__agent__call__id": CALL, "gen_ai__usage__input_tokens": 999,
        })
        post(client, export(*spans))

        run, events = load(client)
        failed = next(e for e in events if e.type == "llm.failed")
        assert (failed.error_code, failed.summary) == ("APIError", "rate limited")
        assert run.total_prompt_tokens == 60

    def test_a_retried_tool_yields_retry_and_recovery_decisions(self, client) -> None:
        spans = agent_spans()
        retry = Span("execute_tool get_weather", "6666666666666666", 12, 20, parent=AGENT, error=("pydantic_ai.exceptions.ToolRetryError", "busy"), **{
            "gen_ai__operation__name": "execute_tool", "gen_ai__tool__name": "get_weather", "gen_ai__tool__call__id": "t0",
            "gen_ai__tool__call__arguments": json.dumps({"city": "Madrid"}), "gen_ai__agent__call__id": CALL,
            "pydantic_ai__tool__retry__cause": "model_retry",
        })
        post(client, export(*spans, retry))

        explanation = client.get(f"/api/runs/{UUID(hex=TRACE)}/explanation").json()
        kinds = [d["kind"] for d in explanation["decisions"]]
        assert "retry" in kinds and "recovery" in kinds
        _, events = load(client)
        assert next(e for e in events if e.type == "tool.failed").error_code == "ToolRetryError"


class TestRunEnd:
    def test_the_run_stays_open_until_the_agent_span_arrives(self, client) -> None:
        spans = agent_spans()
        post(client, export(*spans[1:]))  # only the children, the agent span is still running

        run, _ = load(client)
        assert (run.status, run.agent_name) == ("running", "weather")

        post(client, export(spans[0]))
        run, events = load(client)
        assert run.status == "completed"
        assert types(events).count("run.completed") == 1

    def test_a_nested_agent_ending_first_does_not_close_the_run(self, client) -> None:
        outer = agent_spans()
        inner = [
            Span("invoke_agent helper", "7777777777777777", 32, 38, parent=TOOL, **{
                "gen_ai__operation__name": "invoke_agent", "gen_ai__agent__name": "helper", "gen_ai__agent__call__id": "call-2", "final_result": "done"}),
            Span("chat m", "8888888888888888", 33, 36, parent="7777777777777777", **{
                "gen_ai__operation__name": "chat", "gen_ai__agent__call__id": "call-2", "gen_ai__usage__input_tokens": 5, "gen_ai__usage__output_tokens": 1}),
        ]
        # The helper and the outer agent's own model call go first; the outer agent span is last.
        post(client, export(*inner, outer[1]))
        assert load(client)[0].status == "running"

        post(client, export(*outer[2:], outer[0]))
        run, _ = load(client)
        assert run.status == "completed"
        assert run.final_output_summary == "It is sunny."  # the outer agent's answer, not the helper's

    def test_an_agent_under_a_non_genai_parent_still_ends_the_run(self, client) -> None:
        spans = agent_spans()
        spans[0].parent = "9999999999999999"  # e.g. an HTTP server span that is not exported here

        post(client, export(*spans))

        run, events = load(client)
        assert run.status == "completed"
        assert next(e for e in events if e.type == "chain.started").parent_step_id == "9999999999999999"

    def test_late_spans_of_a_finished_run_are_appended_and_decisions_refreshed(self, client) -> None:
        spans = agent_spans()
        post(client, export(spans[0], spans[1], spans[3]))  # the run ends without the tool span
        assert load(client)[0].tool_count == 0

        post(client, export(spans[2]))  # ... which arrives afterwards

        run, events = load(client)
        assert run.status == "completed"
        assert run.tool_count == 1
        assert "tool.succeeded" in types(events)
        explanation = client.get(f"/api/runs/{UUID(hex=TRACE)}/explanation").json()
        assert [d["label"] for d in explanation["decisions"] if d["kind"] == "tool_choice"] == ["Selected get_weather"]


class TestChronologicalOrder:
    """Spans are exported when they end, so the agent span, which began first, arrives last."""

    EXPECTED = [
        "run.started", "chain.started", "llm.started", "llm.completed", "tool.started", "tool.succeeded",
        "llm.started", "llm.completed", "chain.completed", "run.completed",
    ]

    def test_spans_delivered_one_at_a_time_children_first_are_renumbered_in_order(self, client) -> None:
        spans = agent_spans()
        for span in sorted(spans, key=lambda s: s.end):  # the order a SimpleSpanProcessor exports them
            post(client, export(span))

        run, events = load(client)
        assert types(events) == self.EXPECTED
        assert [e.seq for e in events] == list(range(1, len(events) + 1))
        assert run.last_event_seq == len(events)
        assert as_utc(run.started_at) == datetime.fromtimestamp(T0 / 1e9, tz=timezone.utc)
        assert as_utc(events[0].timestamp) == as_utc(run.started_at)

    def test_decisions_follow_the_real_order(self, client) -> None:
        spans = agent_spans()
        retry = Span("execute_tool get_weather", "6666666666666666", 12, 20, parent=AGENT, error=("builtins.ValueError", "busy"), **{
            "gen_ai__operation__name": "execute_tool", "gen_ai__tool__name": "get_weather", "gen_ai__tool__call__id": "t0",
            "gen_ai__tool__call__arguments": json.dumps({"city": "Madrid"}), "gen_ai__agent__call__id": CALL,
        })
        for span in sorted([*spans, retry], key=lambda s: s.end):
            post(client, export(span))

        explanation = client.get(f"/api/runs/{UUID(hex=TRACE)}/explanation").json()
        kinds = [d["kind"] for d in explanation["decisions"]]
        assert kinds.index("retry") < kinds.index("recovery")

    def test_a_late_batch_with_earlier_spans_is_slotted_in_by_time(self, client) -> None:
        spans = agent_spans()
        post(client, export(spans[3], spans[0]))  # the second model call and the agent span first
        post(client, export(spans[1], spans[2]))  # the earlier work arrives afterwards

        _, events = load(client)
        assert types(events) == self.EXPECTED

    def test_a_run_that_was_only_attached_to_is_not_reordered(self, client) -> None:
        run_id = client.post("/api/runs", json={"agent_name": "mine", "goal": "g"}).json()["run_id"]
        post(client, export(*agent_spans(), resource={"trace_agent.run_id": run_id}))

        _, events = load(client, run_id)
        assert events[0].type == "run.started" and events[0].actor == "proxy"
        assert [e.seq for e in events] == list(range(1, len(events) + 1))


class TestIdempotency:
    def test_redelivering_a_batch_changes_nothing(self, client) -> None:
        body = export(*agent_spans())
        post(client, body)
        before = types(load(client)[1])

        assert post(client, body).status_code == 200

        run, events = load(client)
        assert types(events) == before
        assert (run.tool_count, run.total_prompt_tokens) == (1, 110)

    def test_a_partially_known_batch_only_adds_the_new_spans(self, client) -> None:
        spans = agent_spans()
        post(client, export(*spans[1:3]))
        post(client, export(*spans[1:]))  # a retry that also carries newer spans

        _, events = load(client)
        assert types(events).count("tool.started") == 1
        assert types(events).count("llm.completed") == 2


class TestAttachingToARun:
    def test_spans_naming_an_existing_run_are_added_to_it(self, client) -> None:
        run_id = client.post("/api/runs", json={"agent_name": "mine", "goal": "g"}).json()["run_id"]

        post(client, export(*agent_spans(), resource={"trace_agent.run_id": run_id}))

        run, events = load(client, run_id)
        assert run.agent_name == "mine"
        assert "tool.succeeded" in types(events)
        assert load(client)[0] is None  # no second run for the trace

    def test_an_unknown_run_id_falls_back_to_one_run_per_trace(self, client) -> None:
        post(client, export(*agent_spans(), resource={"trace_agent.run_id": "does-not-exist"}))

        assert load(client)[0].status == "completed"


class TestPrivacy:
    def test_full_payloads_are_stored_when_enabled(self, tmp_path) -> None:
        client = make_client(tmp_path, capture_full_payloads=True)
        post(client, export(*agent_spans()))

        _, events = load(client)
        llm = next(e for e in events if e.type == "llm.completed")
        assert llm.payload_full["output_messages"][0]["parts"][0]["type"] == "tool_call"
        assert next(e for e in events if e.type == "chain.completed").payload_full == {"final_result": "It is sunny."}

    def test_only_summaries_are_stored_when_disabled(self, tmp_path) -> None:
        client = make_client(tmp_path, capture_full_payloads=False)
        post(client, export(*agent_spans()))

        _, events = load(client)
        assert all(e.payload_full is None for e in events)
        assert next(e for e in events if e.type == "tool.succeeded").summary == "Sunny, 23C"

    def test_long_values_are_summarized(self, client) -> None:
        spans = agent_spans()
        spans[2].attributes["gen_ai__tool__call__result"] = "x" * 5000

        post(client, export(*spans))

        _, events = load(client)
        assert len(next(e for e in events if e.type == "tool.succeeded").summary) <= 220


class TestNonAsciiText:
    def test_accents_in_a_tool_result_are_shown_as_typed(self, client) -> None:
        spans = agent_spans()
        spans[2].attributes["gen_ai__tool__call__result"] = json.dumps({"mensaje": "El OEE bajó"}, ensure_ascii=False)

        post(client, export(*spans))

        _, events = load(client)
        summary = next(e for e in events if e.type == "tool.succeeded").summary
        assert "El OEE bajó" in summary
        assert "\\u" not in summary

    def test_a_result_escaped_by_the_producer_is_decoded(self, client) -> None:
        spans = agent_spans()
        spans[2].attributes["gen_ai__tool__call__result"] = json.dumps({"mensaje": "El OEE bajó"})
        assert "\\u00f3" in spans[2].attributes["gen_ai__tool__call__result"]

        post(client, export(*spans))

        _, events = load(client)
        summary = next(e for e in events if e.type == "tool.succeeded").summary
        assert "El OEE bajó" in summary
        assert "\\u" not in summary

    def test_a_plain_text_result_with_a_backslash_is_left_alone(self, client) -> None:
        spans = agent_spans()
        spans[2].attributes["gen_ai__tool__call__result"] = r"path C:\users\ana"

        post(client, export(*spans))

        _, events = load(client)
        assert next(e for e in events if e.type == "tool.succeeded").summary == r"path C:\users\ana"


class TestEndpoint:
    def test_the_response_is_a_valid_protobuf_export_response(self, client) -> None:
        response = post(client, export(*agent_spans()))

        assert response.headers["content-type"] == "application/x-protobuf"
        ExportTraceServiceResponse.FromString(response.content)

    def test_json_bodies_are_accepted(self, client) -> None:
        payload = {"resourceSpans": [{"scopeSpans": [{"spans": [
            {"traceId": TRACE, "spanId": AGENT, "name": "invoke_agent a", "startTimeUnixNano": str(T0), "endTimeUnixNano": str(T0 + 5 * MS),
             "attributes": [{"key": "gen_ai.operation.name", "value": {"stringValue": "invoke_agent"}},
                            {"key": "gen_ai.agent.name", "value": {"stringValue": "a"}},
                            {"key": "gen_ai.agent.call.id", "value": {"stringValue": "c"}}]},
        ]}]}]}

        response = client.post("/v1/traces", content=json.dumps(payload), headers={"content-type": "application/json"})

        assert response.status_code == 200
        assert response.json() == {}
        assert load(client)[0].agent_name == "a"

    def test_gzip_bodies_are_accepted(self, client) -> None:
        response = post(client, gzip.compress(export(*agent_spans())), **{"content-encoding": "gzip"})

        assert response.status_code == 200
        assert load(client)[0].status == "completed"

    @pytest.mark.parametrize("headers, body, status", [
        ({}, b"\xff junk", 400),
        ({"content-type": "text/plain"}, b"x", 400),
        ({"content-encoding": "gzip"}, b"not gzip", 400),
        ({"content-encoding": "br"}, b"x", 400),
    ])
    def test_invalid_requests_are_rejected(self, client, headers, body, status) -> None:
        assert post(client, body, **headers).status_code == status

    def test_oversized_bodies_are_rejected(self, tmp_path) -> None:
        client = make_client(tmp_path, otlp_max_body_bytes=100)

        assert post(client, export(*agent_spans())).status_code == 413

    def test_the_receiver_can_be_turned_off(self, tmp_path) -> None:
        client = make_client(tmp_path, otlp_enabled=False)

        assert post(client, export(*agent_spans())).status_code == 404
        assert load(client)[0] is None

    def test_an_empty_export_is_fine(self, client) -> None:
        assert post(client, ExportTraceServiceRequest().SerializeToString()).status_code == 200

    def test_the_run_shows_up_in_the_run_apis(self, client) -> None:
        post(client, export(*agent_spans()))
        run_id = str(UUID(hex=TRACE))

        for path in ("", "/timeline", "/graph?view=execution", "/graph?view=decisions", "/analytics", "/explanation"):
            assert client.get(f"/api/runs/{run_id}{path}").status_code == 200, path
        overview = client.get(f"/api/runs/{run_id}").json()
        assert (overview["provider"], overview["model"]) == ("openai", "gpt-x-2025")
        assert overview["execution"]["model_turn_count"] == 2
        stats = client.get("/api/dashboard?period=24h").json()["stats"]
        assert (stats["total_runs"], stats["completed_runs"], stats["total_tools"]) == (1, 1, 1)
        assert stats["total_tokens"] == 126
