"""Example: a Pydantic AI agent traced by TraceAgent through OpenTelemetry alone.

Nothing from TraceAgent is imported by the agent: it is instrumented with Pydantic AI's own
``Instrumentation`` capability and exports its spans over OTLP to the server's ``/v1/traces``.
TraceAgent turns the spans into a run (one per trace) with the model calls, tools, tokens and
decisions. A scripted model stands in for a live LLM, so no API key is needed.

Requirements:
    uv sync --extra dev --extra pydantic-ai     # includes the OpenTelemetry SDK and OTLP exporter

Environment:
    TRACE_AGENT_PROXY_URL=http://127.0.0.1:8000
"""

from __future__ import annotations

import os
import sys

import httpx
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from pydantic_ai import Agent
from pydantic_ai.capabilities import Instrumentation
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.instrumented import InstrumentationSettings


def scripted_model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    """Ask for both tools first, then answer once their results are in."""
    if len(messages) == 1:
        return ModelResponse(
            parts=[
                ToolCallPart("get_weather", {"city": "Madrid"}),
                ToolCallPart("get_news", {"topic": "AI agents"}),
            ]
        )
    return ModelResponse(parts=[TextPart("Madrid is sunny at 23C and AI agents are all over the news.")])


def main() -> int:
    base_url = os.getenv("TRACE_AGENT_PROXY_URL", "http://127.0.0.1:8000")

    # 1. Export spans over OTLP to TraceAgent.
    provider = TracerProvider(resource=Resource.create({"service.name": "otel-news-weather-agent"}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{base_url}/v1/traces")))

    # 2. A plain Pydantic AI agent with Pydantic AI's own instrumentation.
    agent = Agent(
        FunctionModel(scripted_model),
        name="otel-news-weather-agent",
        capabilities=[Instrumentation(settings=InstrumentationSettings(tracer_provider=provider))],
    )

    @agent.tool_plain
    def get_weather(city: str) -> str:
        """Get the current weather for a city."""
        return f"Sunny, 23°C in {city}."

    @agent.tool_plain
    def get_news(topic: str) -> str:
        """Get the latest news on a topic."""
        return f"Latest news on {topic}: AI agents are becoming mainstream."

    # 3. Run it. The surrounding span stands for a request handler: the agent runs under a parent.
    with provider.get_tracer("example").start_as_current_span("ask") as span:
        trace_id = format(span.get_span_context().trace_id, "032x")
        result = agent.run_sync("What's the weather in Madrid and any news about AI agents?")
    print(f"Assistant response: {result.output}")

    # A short script must flush before exiting, or the batch of spans is lost.
    provider.shutdown()

    # 4. The trace id is the run id (as a UUID): check what TraceAgent recorded.
    run_id = f"{trace_id[:8]}-{trace_id[8:12]}-{trace_id[12:16]}-{trace_id[16:20]}-{trace_id[20:]}"
    response = httpx.get(f"{base_url}/api/runs/{run_id}")
    if response.status_code != 200:
        print(f"TraceAgent has no run {run_id}: is the server reachable at {base_url}?", file=sys.stderr)
        return 1
    run = response.json()
    print(f"Run {run_id}: {run['status']}, {run['tool_count']} tools, provider={run['provider']}")
    print(f"View at: {base_url}/runs/{run_id}")
    return 0 if run["status"] == "completed" else 1


if __name__ == "__main__":
    sys.exit(main())
