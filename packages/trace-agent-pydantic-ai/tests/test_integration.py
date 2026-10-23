"""Integration tests for the Pydantic AI capability with the TraceAgent backend.

They spin up the FastAPI app with a temporary SQLite DB, run a real Pydantic AI
agent (``TestModel``, no live model) with the capability attached and verify
what the backend persisted and exposes.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

pytest.importorskip("pydantic_ai")

from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel
from trace_agent_sdk import TraceAgentClient
from trace_agent_server.config import Settings
from trace_agent_server.main import create_app
from trace_agent_server.models import Event, Run


@pytest.fixture
def test_client(tmp_path) -> TestClient:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        cors_origins=["http://localhost:5173"],
    )
    return TestClient(create_app(settings))


def start_run(test_client: TestClient, name: str):
    client = TraceAgentClient(base_url="", http_client=test_client)
    return client.start_run(name, "answer weather questions")


class TestPydanticAiIntegration:
    async def test_run_llm_and_tool_events_are_persisted(self, test_client) -> None:
        run = start_run(test_client, "pydantic-weather")
        agent = Agent(TestModel(), name="pydantic-weather", capabilities=[run.as_pydantic_ai_capability()])

        @agent.tool_plain
        def get_weather(city: str) -> str:
            """Get the weather for a city."""
            return f"Sunny in {city}"

        result = await agent.run("weather in Madrid?")
        run.finish(result.output)

        with test_client.app.state.session_factory() as session:
            stored = session.query(Run).filter_by(id=run.run_id).one()
            events = session.query(Event).filter_by(run_id=run.run_id).order_by(Event.seq).all()
            types = [event.type for event in events]

            assert stored.status == "completed"
            assert stored.tool_count == 1
            assert stored.error_count == 0
            assert types.count("chain.started") == 1
            assert types.count("chain.completed") == 1
            assert types.count("llm.completed") == 2
            # One tool.started/tool.succeeded pair: no duplicates from observations.
            assert types.count("tool.started") == 1
            assert types.count("tool.succeeded") == 1
            llm = next(event for event in events if event.type == "llm.completed")
            assert llm.event_metadata["prompt_tokens"] > 0
            run_step = next(e for e in events if e.type == "chain.started").step_id
            assert llm.parent_step_id == run_step
            # Tools hang from the run too, and model usage lands on the run totals.
            assert {e.parent_step_id for e in events if e.type.startswith("tool.")} == {run_step}
            assert stored.model
            assert stored.total_prompt_tokens > 0
            assert stored.total_completion_tokens > 0

    async def test_failed_tool_is_recorded_once_and_run_fails(self, test_client) -> None:
        run = start_run(test_client, "pydantic-failing")
        agent = Agent(TestModel(), capabilities=[run.as_pydantic_ai_capability()])

        @agent.tool_plain
        def explode(city: str) -> str:
            raise ValueError("no network")

        with pytest.raises(ValueError):
            await agent.run("go")
        run.fail("ValueError", "no network")

        with test_client.app.state.session_factory() as session:
            stored = session.query(Run).filter_by(id=run.run_id).one()
            types = [e.type for e in session.query(Event).filter_by(run_id=run.run_id).all()]
            assert stored.status == "failed"
            # One error from the failed tool and one from run.fail() itself.
            assert stored.error_count == 2
            assert types.count("tool.failed") == 1
            assert "chain.failed" in types

    async def test_timeline_graph_and_analytics_render_the_run(self, test_client) -> None:
        run = start_run(test_client, "pydantic-views")
        agent = Agent(TestModel(), capabilities=[run.as_pydantic_ai_capability()])

        @agent.tool_plain
        def get_weather(city: str) -> str:
            return "Sunny"

        result = await agent.run("weather?")
        run.finish(result.output)

        for path in ("timeline", "graph?view=execution", "analytics", "explanation"):
            response = test_client.get(f"/api/runs/{run.run_id}/{path}")
            assert response.status_code == 200, f"{path}: {response.text}"

        assert test_client.get(f"/api/runs/{run.run_id}").json()["agent_name"] == "pydantic-views"
