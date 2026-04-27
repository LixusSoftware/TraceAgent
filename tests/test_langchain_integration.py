"""Integration tests for LangChain callback with the Visor backend.

These tests require langchain to be installed (via `uv pip install -e ".[langchain]"`).
They spin up the FastAPI app with an in-memory DB, create a run, invoke a LangChain
chain with the Visor callback, and verify that events are persisted.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from visor_agentico.config import Settings
from visor_agentico.main import create_app
from visor_agentico.models import Event, Run

# Skip entire module if langchain is not installed
langchain = pytest.importorskip("langchain")
langchain_core = pytest.importorskip("langchain_core")


@pytest.fixture
def test_client(tmp_path) -> TestClient:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        cors_origins=["http://localhost:5173"],
    )
    app = create_app(settings)
    return TestClient(app)


class TestLangChainCallbackIntegration:
    def test_chain_events_are_persisted(self, test_client) -> None:
        client = test_client

        # 1. Create a run via the API
        resp = client.post(
            "/api/runs",
            json={"agent_name": "test-agent", "goal": "test chain observability"},
        )
        assert resp.status_code == 200
        run_id = resp.json()["run_id"]

        # 2. Build a simple LangChain chain and attach the callback
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_core.runnables import RunnableLambda

        from visor_agentico.langchain_callback import VisorLangChainCallback
        from visor_agentico.sdk import RunSession, VisorClient

        visor_client = VisorClient(base_url="", http_client=client)
        # Manually construct a RunSession since we bypass start_run()
        run_session = RunSession(
            client=visor_client,
            run_id=run_id,
            agent_name="test-agent",
            goal="test",
        )
        callback = VisorLangChainCallback(run_session)

        # 3. Invoke a simple Runnable sequence
        chain = RunnableLambda(lambda x: x.upper())
        result = chain.invoke("hello", config={"callbacks": [callback]})
        assert result == "HELLO"

        # 4. Verify events were persisted
        with client.app.state.session_factory() as session:
            run = session.query(Run).filter_by(id=run_id).first()
            assert run is not None
            events = session.query(Event).filter_by(run_id=run_id).order_by(Event.seq).all()
            # Should have at least chain.started + chain.completed
            assert len(events) >= 2
            types = [e.type for e in events]
            assert "chain.started" in types
            assert "chain.completed" in types

    def test_llm_events_with_mocked_provider(self, test_client) -> None:
        """Test that LLM calls produce the correct event types.

        We mock the LLM so no real API key is needed.
        """
        client = test_client

        resp = client.post(
            "/api/runs",
            json={"agent_name": "test-llm-agent", "goal": "test llm events"},
        )
        run_id = resp.json()["run_id"]

        from unittest.mock import MagicMock, patch

        from langchain_core.outputs import Generation, LLMResult

        from visor_agentico.langchain_callback import VisorLangChainCallback
        from visor_agentico.sdk import RunSession, VisorClient

        visor_client = VisorClient(base_url="", http_client=client)
        run_session = RunSession(
            client=visor_client,
            run_id=run_id,
            agent_name="test-llm-agent",
            goal="test",
        )
        callback = VisorLangChainCallback(run_session)

        # Simulate an LLM call with token usage
        mock_result = LLMResult(
            generations=[[Generation(text="hello")]],
            llm_output={"token_usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7}},
        )

        callback.on_llm_start(
            serialized={"name": "FakeLLM"},
            prompts=["hi"],
            run_id="llm-1",
        )
        callback.on_llm_end(
            response=mock_result,
            run_id="llm-1",
        )

        with client.app.state.session_factory() as session:
            events = session.query(Event).filter_by(run_id=run_id).order_by(Event.seq).all()
            types = [e.type for e in events]
            assert "llm.started" in types
            assert "llm.completed" in types
            llm_completed = next(e for e in events if e.type == "llm.completed")
            assert llm_completed.event_metadata.get("prompt_tokens") == 5
            assert llm_completed.event_metadata.get("completion_tokens") == 2

    def test_tool_events_are_persisted(self, test_client) -> None:
        client = test_client

        resp = client.post(
            "/api/runs",
            json={"agent_name": "test-tool-agent", "goal": "test tool events"},
        )
        run_id = resp.json()["run_id"]

        from visor_agentico.langchain_callback import VisorLangChainCallback
        from visor_agentico.sdk import RunSession, VisorClient

        visor_client = VisorClient(base_url="", http_client=client)
        run_session = RunSession(
            client=visor_client,
            run_id=run_id,
            agent_name="test-tool-agent",
            goal="test",
        )
        callback = VisorLangChainCallback(run_session)

        callback.on_tool_start(
            serialized={"name": "search"},
            input_str='{"q": "hello"}',
            run_id="tool-1",
        )
        callback.on_tool_end(
            output="found it",
            run_id="tool-1",
            metadata={"name": "search"},
        )

        with client.app.state.session_factory() as session:
            events = session.query(Event).filter_by(run_id=run_id).order_by(Event.seq).all()
            types = [e.type for e in events]
            assert "tool.started" in types
            assert "tool.succeeded" in types
