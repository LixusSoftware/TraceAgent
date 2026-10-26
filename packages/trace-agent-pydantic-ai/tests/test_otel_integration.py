"""A real Pydantic AI agent, traced through OpenTelemetry and the server's OTLP receiver.

The agent's own spans are encoded exactly as an OTLP exporter would and posted to the
receiver, so what is checked is what a user gets by pointing their exporter at TraceAgent.
"""

from __future__ import annotations

from collections import Counter
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

pytest.importorskip("opentelemetry.sdk")
pytest.importorskip("pydantic_ai")

from opentelemetry.exporter.otlp.proto.common.trace_encoder import encode_spans
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor, SpanExporter, SpanExportResult
from pydantic_ai import Agent, ModelRetry
from pydantic_ai.capabilities import Instrumentation
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.instrumented import InstrumentationSettings
from pydantic_ai.models.test import TestModel
from trace_agent_sdk import TraceAgentClient
from trace_agent_server.config import Settings
from trace_agent_server.main import create_app
from trace_agent_server.models import Event, Run


class ReceiverExporter(SpanExporter):
    """Sends spans to the server like an OTLP/HTTP exporter, without a network."""

    def __init__(self, client: TestClient) -> None:
        self.client = client
        self.requests = 0

    def export(self, spans) -> SpanExportResult:
        response = self.client.post(
            "/v1/traces", content=encode_spans(spans).SerializeToString(), headers={"content-type": "application/x-protobuf"}
        )
        self.requests += 1
        return SpanExportResult.SUCCESS if response.status_code == 200 else SpanExportResult.FAILURE

    def shutdown(self) -> None:
        pass


@pytest.fixture
def client(tmp_path) -> TestClient:
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'test.db'}", cors_origins=["http://localhost:5173"])
    return TestClient(create_app(settings))


def traced_agent(client: TestClient, model, *, name: str, include_content: bool = True, batch: bool = False):
    exporter = ReceiverExporter(client)
    provider = TracerProvider(resource=Resource.create({"service.name": "otel-test"}))
    provider.add_span_processor(BatchSpanProcessor(exporter) if batch else SimpleSpanProcessor(exporter))
    instrumentation = Instrumentation(settings=InstrumentationSettings(tracer_provider=provider, include_content=include_content))
    return Agent(model, name=name, capabilities=[instrumentation]), provider, exporter


def runs_and_events(client: TestClient):
    with client.app.state.session_factory() as session:
        runs = session.query(Run).all()
        events = {run.id: session.query(Event).filter_by(run_id=run.id).order_by(Event.seq).all() for run in runs}
        for run in runs:
            session.expunge(run)
        for run_events in events.values():
            for event in run_events:
                session.expunge(event)
    return runs, events


class TestOpenTelemetryIntegration:
    async def test_a_run_with_a_tool_is_traced_span_by_span(self, client) -> None:
        agent, _, exporter = traced_agent(client, TestModel(), name="weather")

        @agent.tool_plain
        def get_weather(city: str) -> str:
            return f"Sunny in {city}"

        result = await agent.run("What is the weather?")

        # Simple processors export each span as it ends: children arrive before the agent span.
        assert exporter.requests >= 4
        (run,), events = runs_and_events(client)
        run_events = [e.type for e in events[run.id]]
        assert run.status == "completed"
        assert (run.agent_name, run.goal) == ("weather", "What is the weather?")
        assert run.final_output_summary == result.output
        assert (run.tool_count, run.error_count) == (1, 0)
        assert run.total_prompt_tokens > 0 and run.total_completion_tokens > 0
        assert run.provider == "test"
        assert run_events[0] == "run.started" and run_events[-1] == "run.completed"
        assert run_events.count("tool.succeeded") == 1
        assert run_events.count("llm.completed") == 2

    async def test_a_batched_export_gives_the_same_run(self, client) -> None:
        agent, provider, _ = traced_agent(client, TestModel(), name="weather", batch=True)

        @agent.tool_plain
        def get_weather(city: str) -> str:
            return f"Sunny in {city}"

        await agent.run("weather?")
        provider.force_flush()

        (run,), events = runs_and_events(client)
        assert run.status == "completed"
        assert [e.type for e in events[run.id]].count("tool.succeeded") == 1

    async def test_a_failing_tool_fails_the_run(self, client) -> None:
        agent, _, _ = traced_agent(client, TestModel(), name="failing")

        @agent.tool_plain
        def fetch(url: str) -> str:
            raise ConnectionError("network unreachable")

        with pytest.raises(ConnectionError):
            await agent.run("go")

        (run,), events = runs_and_events(client)
        failed = next(e for e in events[run.id] if e.type == "tool.failed")
        assert (failed.error_code, failed.tool_name) == ("ConnectionError", "fetch")
        assert (run.status, run.final_output_summary) == ("failed", "network unreachable")

    async def test_a_retried_tool_shows_retry_and_recovery(self, client) -> None:
        agent, _, _ = traced_agent(client, TestModel(), name="retrying")
        attempts = {"n": 0}

        @agent.tool_plain
        def lookup(item: str) -> str:
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise ModelRetry("busy")
            return "in stock"

        await agent.run("stock?")

        (run,), events = runs_and_events(client)
        assert [e.error_code for e in events[run.id] if e.type == "tool.failed"] == ["ToolRetryError"]
        kinds = [d["kind"] for d in client.get(f"/api/runs/{run.id}/explanation").json()["decisions"]]
        assert "retry" in kinds and "recovery" in kinds
        assert run.status == "completed"

    async def test_a_nested_agent_does_not_end_the_run_early(self, client) -> None:
        inner, _, _ = traced_agent(client, FunctionModel(lambda m, i: ModelResponse(parts=[TextPart("inner answer")])), name="inner")
        outer, _, _ = traced_agent(client, TestModel(call_tools=["delegate"]), name="outer")

        @outer.tool_plain
        async def delegate(topic: str) -> str:
            return (await inner.run(topic)).output

        result = await outer.run("go")

        # The inner agent runs inside the outer one's tool, so both are one trace and one run,
        # even with separate tracer providers: the inner agent ends first and must not close it.
        (run,), events = runs_and_events(client)
        run_events = events[run.id]
        assert (run.agent_name, run.status) == ("outer", "completed")
        assert run.final_output_summary == result.output  # the outer agent's answer, not "inner answer"
        chains = [e for e in run_events if e.type == "chain.started"]
        assert [e.metadata_["agent_name"] if hasattr(e, "metadata_") else e.event_metadata["agent_name"] for e in chains] == ["outer", "inner"]
        tool_step = next(e for e in run_events if e.type == "tool.started").step_id
        assert chains[1].parent_step_id == tool_step  # the inner agent hangs from the tool that called it
        assert [e.type for e in run_events].count("run.completed") == 1

    async def test_a_run_without_captured_content_is_still_traced(self, client) -> None:
        agent, _, _ = traced_agent(client, TestModel(), name="private", include_content=False)

        @agent.tool_plain
        def get_weather(city: str) -> str:
            return "secret"

        await agent.run("a private prompt")

        (run,), events = runs_and_events(client)
        assert run.goal == "OpenTelemetry trace"  # the prompt was not exported
        assert run.status == "completed"
        assert "a private prompt" not in str([e.summary for e in events[run.id]])

    async def test_the_run_feeds_every_view_of_the_ui(self, client) -> None:
        agent, _, _ = traced_agent(client, TestModel(), name="weather")

        @agent.tool_plain
        def get_weather(city: str) -> str:
            return "Sunny"

        await agent.run("weather?")

        (run,), _ = runs_and_events(client)
        for path in ("", "/timeline", "/graph?view=execution", "/graph?view=decisions", "/analytics", "/explanation"):
            assert client.get(f"/api/runs/{run.id}{path}").status_code == 200, path
        overview = client.get(f"/api/runs/{run.id}").json()
        assert overview["execution"]["model_turn_count"] == 2
        assert client.get("/api/dashboard?period=24h").json()["stats"]["total_runs"] == 1

    async def test_it_matches_what_the_hooks_capability_records(self, client) -> None:
        """The same agent traced both ways produces the same events, tools and tokens."""
        otel_agent, _, _ = traced_agent(client, TestModel(), name="same")
        hooks_run = TraceAgentClient(base_url="", http_client=client).start_run("same", "weather?")
        hooks_agent = Agent(TestModel(), name="same", capabilities=[hooks_run.as_pydantic_ai_capability()])
        for agent in (otel_agent, hooks_agent):

            @agent.tool_plain
            def get_weather(city: str) -> str:
                return f"Sunny in {city}"

        await otel_agent.run("weather?")
        result = await hooks_agent.run("weather?")
        hooks_run.finish(result.output)

        runs, events = runs_and_events(client)
        by_source = {("otlp" if r.run_metadata.get("source") == "otlp" else "hooks"): r for r in runs}
        otel, hooks = by_source["otlp"], by_source["hooks"]
        assert Counter(e.type for e in events[otel.id]) == Counter(e.type for e in events[hooks.id])
        assert (otel.tool_count, otel.error_count) == (hooks.tool_count, hooks.error_count)
        assert (otel.total_prompt_tokens, otel.total_completion_tokens) == (hooks.total_prompt_tokens, hooks.total_completion_tokens)
        assert (otel.provider, otel.model) == (hooks.provider, hooks.model)
        assert UUID(otel.id)  # a real UUID, derived from the trace id
