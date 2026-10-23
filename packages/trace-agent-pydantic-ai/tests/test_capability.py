"""Tests for TraceAgentCapability.

The HTTP layer is mocked; a real Pydantic AI ``Agent`` backed by ``TestModel`` /
``FunctionModel`` drives the hooks so no live model is needed.
"""

from __future__ import annotations

import threading
import time
from typing import Any
from unittest.mock import MagicMock

import pytest

pytest.importorskip("pydantic_ai")

from pydantic_ai import Agent, ModelRetry
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel
from trace_agent_pydantic_ai import TraceAgentCapability


@pytest.fixture
def posts() -> list[tuple[str, dict[str, Any]]]:
    return []


@pytest.fixture
def run_session(posts) -> MagicMock:
    session = MagicMock()
    session.run_id = "run-123"

    def _request(method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        posts.append((path, payload or {}))
        return {"status": "ok"}

    session.client._request = MagicMock(side_effect=_request)
    return session


def observations(posts, kind: str | None = None) -> list[dict[str, Any]]:
    found = [
        obs
        for path, payload in posts
        if path.endswith("/observations")
        for obs in payload["observations"]
    ]
    return [obs for obs in found if kind is None or obs["kind"] == kind]


def tool_results(posts) -> list[dict[str, Any]]:
    return [
        result
        for path, payload in posts
        if path.endswith("/tool-results")
        for result in payload["results"]
    ]


def make_agent(capability: TraceAgentCapability, model: Any | None = None) -> Agent:
    agent = Agent(model or TestModel(), name="weather-agent", capabilities=[capability])

    @agent.tool_plain
    def get_weather(city: str) -> str:
        """Get the weather for a city."""
        return f"Sunny in {city}"

    return agent


class TestRunLifecycle:
    async def test_run_posts_running_then_succeeded(self, run_session, posts) -> None:
        agent = make_agent(TraceAgentCapability(run_session))
        await agent.run("What is the weather?")

        runs = observations(posts, "chain_step")
        assert [obs["status"] for obs in runs] == ["running", "succeeded"]
        assert runs[0]["step_id"] == runs[1]["step_id"]
        assert runs[0]["metadata"]["agent_name"] == "weather-agent"
        assert runs[1]["duration_ms"] >= 0
        assert runs[1]["metadata"]["total_tokens"] >= 0
        assert "output_hash" in runs[1]["metadata"]

    async def test_run_failure_posts_failed_and_reraises(self, run_session, posts) -> None:
        def boom(messages: Any, info: AgentInfo) -> ModelResponse:
            raise RuntimeError("model exploded")

        agent = make_agent(TraceAgentCapability(run_session), FunctionModel(boom))
        with pytest.raises(RuntimeError, match="model exploded"):
            await agent.run("hi")

        runs = observations(posts, "chain_step")
        assert runs[-1]["status"] == "failed"
        assert runs[-1]["error_code"] == "RuntimeError"
        assert "model exploded" in runs[-1]["error_summary"]
        llm = observations(posts, "llm_call")
        assert llm[-1]["status"] == "failed"


class TestModelRequests:
    async def test_llm_calls_are_children_of_the_run(self, run_session, posts) -> None:
        agent = make_agent(TraceAgentCapability(run_session))
        await agent.run("weather please")

        run_step = observations(posts, "chain_step")[0]["step_id"]
        llm = observations(posts, "llm_call")
        # TestModel: one request that calls the tool, one that answers.
        assert [obs["status"] for obs in llm] == ["running", "succeeded", "running", "succeeded"]
        assert {obs["parent_step_id"] for obs in llm} == {run_step}
        assert llm[1]["metadata"]["requested_tools"] == ["get_weather"]
        assert llm[1]["model"]

    async def test_model_events_can_be_disabled(self, run_session, posts) -> None:
        agent = make_agent(TraceAgentCapability(run_session, record_model_events=False))
        await agent.run("weather please")
        assert observations(posts, "llm_call") == []


class TestToolExecution:
    async def test_tool_posts_only_tool_results(self, run_session, posts) -> None:
        agent = make_agent(TraceAgentCapability(run_session))
        await agent.run("weather please")

        results = tool_results(posts)
        assert len(results) == 1
        assert results[0]["name"] == "get_weather"
        assert results[0]["status"] == "succeeded"
        assert results[0]["call_id"]
        assert results[0]["args"] == {"city": "a"}
        assert "Sunny" in results[0]["output_summary"]
        assert results[0]["duration_ms"] >= 0
        assert results[0]["parent_step_id"] == observations(posts, "chain_step")[0]["step_id"]
        # /tool-results already records tool.started/tool.succeeded events.
        assert observations(posts, "tool_call") == []

    async def test_tool_failure_is_reported_and_reraised(self, run_session, posts) -> None:
        agent = Agent(TestModel(), capabilities=[TraceAgentCapability(run_session)])

        @agent.tool_plain
        def explode(city: str) -> str:
            raise ValueError("no network")

        with pytest.raises(ValueError, match="no network"):
            await agent.run("go")

        failed = tool_results(posts)[0]
        assert failed["status"] == "failed"
        assert failed["error_code"] == "ValueError"
        assert failed["error_summary"] == "no network"

    async def test_model_retry_is_recorded_then_succeeds(self, run_session, posts) -> None:
        attempts = {"count": 0}
        agent = Agent(TestModel(), capabilities=[TraceAgentCapability(run_session)])

        @agent.tool_plain
        def flaky(city: str) -> str:
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise ModelRetry("try again")
            return "ok"

        await agent.run("go")

        statuses = [(r["status"], r.get("error_code")) for r in tool_results(posts)]
        # Pydantic AI wraps ModelRetry in ToolRetryError before it reaches the hook.
        assert statuses == [("failed", "ToolRetryError"), ("succeeded", None)]

    async def test_redact_fields_hide_arguments(self, run_session, posts) -> None:
        agent = Agent(
            TestModel(),
            capabilities=[TraceAgentCapability(run_session, redact_fields=["secret"])],
        )

        @agent.tool_plain
        def login(secret: str) -> str:
            return "ok"

        await agent.run("go")
        assert tool_results(posts)[0]["args"] == {"secret": "[redacted]"}

    async def test_tool_events_can_be_disabled(self, run_session, posts) -> None:
        agent = make_agent(TraceAgentCapability(run_session, record_tool_events=False))
        await agent.run("weather please")
        assert tool_results(posts) == []

    async def test_parallel_tools_get_distinct_steps(self, run_session, posts) -> None:
        agent = Agent(TestModel(), capabilities=[TraceAgentCapability(run_session)])

        @agent.tool_plain
        def first(x: str) -> str:
            return "1"

        @agent.tool_plain
        def second(x: str) -> str:
            return "2"

        await agent.run("go")

        results = tool_results(posts)
        assert {r["name"] for r in results} == {"first", "second"}
        assert len({r["step_id"] for r in results}) == 2


class TestConcurrency:
    async def test_posts_are_never_sent_concurrently(self, run_session) -> None:
        """The backend numbers events per run without locking: overlap means a 500."""
        in_flight = {"now": 0, "max": 0}
        guard = threading.Lock()

        def slow_request(method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
            with guard:
                in_flight["now"] += 1
                in_flight["max"] = max(in_flight["max"], in_flight["now"])
            time.sleep(0.02)
            with guard:
                in_flight["now"] -= 1
            return {"status": "ok"}

        run_session.client._request = MagicMock(side_effect=slow_request)
        agent = Agent(TestModel(), capabilities=[TraceAgentCapability(run_session)])

        @agent.tool_plain
        async def first(x: str) -> str:
            return "1"

        @agent.tool_plain
        async def second(x: str) -> str:
            return "2"

        await agent.run("go")

        assert in_flight["max"] == 1


class TestNodeEvents:
    async def test_nodes_are_off_by_default(self, run_session, posts) -> None:
        agent = make_agent(TraceAgentCapability(run_session))
        await agent.run("hi")
        assert observations(posts, "agent_action") == []

    async def test_nodes_can_be_enabled(self, run_session, posts) -> None:
        agent = make_agent(TraceAgentCapability(run_session, record_node_events=True))
        await agent.run("hi")

        nodes = observations(posts, "agent_action")
        assert nodes
        assert {obs["metadata"]["node"] for obs in nodes} >= {"ModelRequestNode", "CallToolsNode"}


class TestBackendFailures:
    async def test_unreachable_backend_never_breaks_the_agent(self, run_session) -> None:
        run_session.client._request = MagicMock(side_effect=ConnectionError("backend down"))
        agent = make_agent(TraceAgentCapability(run_session))

        result = await agent.run("weather please")

        assert result.output
        assert run_session.client._request.called

    async def test_nested_run_is_child_of_outer_step(self, run_session, posts) -> None:
        capability = TraceAgentCapability(run_session)
        inner = Agent(FunctionModel(lambda m, i: ModelResponse(parts=[TextPart("inner")])), name="inner", capabilities=[capability])
        outer = Agent(TestModel(call_tools=[]), name="outer", capabilities=[capability])

        @outer.tool_plain
        async def delegate(topic: str) -> str:
            return (await inner.run(topic)).output

        outer.model = FunctionModel(_call_delegate_then_answer)
        await outer.run("go")

        runs = [o for o in observations(posts, "chain_step") if o["status"] == "running"]
        by_agent = {o["metadata"]["agent_name"]: o for o in runs}
        assert by_agent["outer"]["parent_step_id"] is None
        assert by_agent["inner"]["parent_step_id"] == by_agent["outer"]["step_id"]


def _call_delegate_then_answer(messages: Any, info: AgentInfo) -> ModelResponse:
    if len(messages) == 1:
        return ModelResponse(parts=[ToolCallPart("delegate", {"topic": "x"})])
    return ModelResponse(parts=[TextPart("done")])


class TestSdkIntegration:
    def test_run_session_builds_capability(self) -> None:
        from trace_agent_sdk.client import RunSession

        session = RunSession(MagicMock(), "run-1", "agent", "goal")
        capability = session.as_pydantic_ai_capability(record_node_events=True, redact_fields=["token"])

        assert isinstance(capability, TraceAgentCapability)
        assert capability.run_session is session
        assert capability.record_node_events is True
        assert capability.redact_fields == ["token"]
