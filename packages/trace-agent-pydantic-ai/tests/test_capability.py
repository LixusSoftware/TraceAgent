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
from trace_agent_pydantic_ai import TraceAgentCapability, current_step_id


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

    async def test_both_rows_of_a_call_know_the_provider_and_say_it_once_each(self, run_session, posts) -> None:
        agent = Agent(FunctionModel(lambda m, i: ModelResponse(parts=[TextPart("hi")])), name="a", capabilities=[TraceAgentCapability(run_session)])
        await agent.run("hello")

        started, completed = observations(posts, "llm_call")
        assert started["provider"] == completed["provider"] == "function"
        assert started["input_summary"].startswith("Model request to ")
        assert completed["input_summary"] == "Model responded via function"

    async def test_a_call_carries_what_was_asked_and_what_was_answered(self, run_session, posts) -> None:
        agent = Agent(FunctionModel(lambda m, i: ModelResponse(parts=[TextPart("El OEE bajó")])), name="a", instructions="Be brief.", capabilities=[TraceAgentCapability(run_session)])
        await agent.run("¿Por qué bajó el OEE?")

        content = observations(posts, "llm_call")[-1]["content"]
        asked = [(m["role"], m["parts"][0]["content"]) for m in content["input_messages"]]
        assert ("system", "Be brief.") in asked
        assert ("user", "¿Por qué bajó el OEE?") in asked
        assert content["output_messages"] == [{"role": "assistant", "parts": [{"type": "text", "content": "El OEE bajó"}]}]

    async def test_content_can_be_turned_off(self, run_session, posts) -> None:
        agent = make_agent(TraceAgentCapability(run_session, capture_content=False))
        await agent.run("weather please")

        assert all(obs.get("content") is None for obs in observations(posts, "llm_call"))

    async def test_tool_calls_and_results_in_the_content_follow_redact_fields(self, run_session, posts) -> None:
        def model(messages: Any, info: AgentInfo) -> ModelResponse:
            if len(messages) == 1:
                return ModelResponse(parts=[ToolCallPart("charge", {"customer": "ana", "api_key": "SECRET-KEY"})])
            return ModelResponse(parts=[TextPart("charged")])

        agent = Agent(FunctionModel(model), name="a", capabilities=[TraceAgentCapability(run_session, redact_fields=["api_key", "card"])])

        @agent.tool_plain
        def charge(customer: str, api_key: str) -> dict:
            return {"ok": True, "card": "4111111111111111"}

        await agent.run("charge ana")

        sent = str([obs.get("content") for obs in observations(posts, "llm_call")])
        assert "SECRET-KEY" not in sent
        assert "4111111111111111" not in sent
        assert "[redacted]" in sent
        assert "ana" in sent

    async def test_the_whole_tool_output_is_sent_masked_and_can_be_turned_off(self, run_session, posts) -> None:
        def build(**options: Any) -> Agent:
            agent = Agent(
                FunctionModel(lambda m, i: ModelResponse(parts=[ToolCallPart("lookup", {})]) if len(m) == 1 else ModelResponse(parts=[TextPart("ok")])),
                name="a", capabilities=[TraceAgentCapability(run_session, **options)],
            )

            @agent.tool_plain
            def lookup() -> dict:
                return {"veredicto": "descartado", "api_key": "SECRET"}

            return agent

        await build(redact_fields=["api_key"]).run("go")
        assert tool_results(posts)[-1]["output"] == {"veredicto": "descartado", "api_key": "[redacted]"}

        posts.clear()
        await build(capture_content=False).run("go")
        assert tool_results(posts)[-1]["output"] is None

    async def test_very_long_texts_in_the_content_are_cut(self, run_session, posts) -> None:
        agent = Agent(FunctionModel(lambda m, i: ModelResponse(parts=[TextPart("ok")])), name="a", capabilities=[TraceAgentCapability(run_session)])
        await agent.run("x" * 50_000)

        text = observations(posts, "llm_call")[-1]["content"]["input_messages"][-1]["parts"][0]["content"]
        assert len(text) < 21_000
        assert "more characters" in text


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

    async def test_a_slow_backend_does_not_stall_the_agent(self, run_session) -> None:
        def slow_request(method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
            time.sleep(0.3)
            return {"status": "ok"}

        run_session.client._request = MagicMock(side_effect=slow_request)
        agent = make_agent(TraceAgentCapability(run_session, flush_timeout=0.1))

        started = time.perf_counter()
        await agent.run("weather please")
        elapsed = time.perf_counter() - started

        # Delivering every event serially would take at least 7 * 0.3s.
        assert elapsed < 1.2

    async def test_failed_delivery_pauses_sending_and_warns_once(self, run_session, capsys) -> None:
        run_session.client._request = MagicMock(side_effect=ConnectionError("backend down"))
        agent = make_agent(TraceAgentCapability(run_session, failure_cooldown=60))

        await agent.run("weather please")
        await agent.run("weather again")

        assert run_session.client._request.call_count == 1
        err = capsys.readouterr().err
        assert err.count("pausing delivery") == 1
        assert "ConnectionError" in err
        assert "Traceback" not in err

    async def test_zero_cooldown_retries_every_event(self, run_session) -> None:
        run_session.client._request = MagicMock(side_effect=ConnectionError("backend down"))
        agent = make_agent(TraceAgentCapability(run_session, failure_cooldown=0))

        await agent.run("weather please")

        assert run_session.client._request.call_count > 1

    async def test_everything_is_delivered_when_the_run_returns(self, run_session, posts) -> None:
        agent = make_agent(TraceAgentCapability(run_session))
        await agent.run("weather please")

        # The caller may call run.finish() right away: nothing can still be queued.
        assert observations(posts, "chain_step")[-1]["status"] == "succeeded"
        assert len(tool_results(posts)) == 1

    async def test_what_a_tool_records_by_hand_hangs_from_the_tool(self, run_session, posts) -> None:
        seen: dict[str, Any] = {}
        agent = make_agent(TraceAgentCapability(run_session))

        @agent.tool_plain
        def inspect_step() -> str:
            seen["inside"] = current_step_id()
            return "ok"

        agent.model = FunctionModel(lambda m, i: ModelResponse(parts=[ToolCallPart("inspect_step", {})]) if len(m) == 1 else ModelResponse(parts=[TextPart("done")]))
        await agent.run("go")

        tool_step = next(r for r in tool_results(posts) if r["name"] == "inspect_step")["step_id"]
        assert seen["inside"] == tool_step
        assert current_step_id() is None  # outside any run there is no current step

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
        # The agent is called from inside a tool, so it hangs from that tool (as it does over OpenTelemetry).
        assert by_agent["inner"]["parent_step_id"] == tool_results(posts)[-1]["step_id"]


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
