from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from visor_agentico.config import Settings
from visor_agentico.main import create_app
from visor_agentico.sdk import VisorClient
from visor_agentico.services.provider import ProviderToolCall, ProviderTurnRequest, ProviderTurnResponse


class SimpleProvider:
    provider_name = "openai"

    def generate_turn(self, request: ProviderTurnRequest) -> ProviderTurnResponse:
        tool_msgs = [m for m in request.messages if m.get("role") == "tool"]
        if not tool_msgs:
            return ProviderTurnResponse(
                assistant_message={"role": "assistant", "content": "Hello"},
                summary="Hello",
                metadata={
                    "usage": {
                        "prompt_tokens": 10,
                        "completion_tokens": 5,
                        "total_tokens": 15,
                    }
                },
            )
        return ProviderTurnResponse(
            assistant_message={"role": "assistant", "content": "Done"},
            summary="Done",
            metadata={
                "usage": {
                    "prompt_tokens": 8,
                    "completion_tokens": 2,
                    "total_tokens": 10,
                }
            },
        )


@pytest.fixture
def test_client(tmp_path) -> TestClient:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        cors_origins=["http://localhost:5173"],
    )
    app = create_app(settings)
    app.state.provider_registry = {"openai": SimpleProvider()}
    return TestClient(app)


class TestTurnsApi:
    def test_create_turn_persists_messages_and_tokens(self, test_client) -> None:
        client = test_client
        sdk = VisorClient(base_url="http://testserver", http_client=client)

        run = sdk.start_run(agent_name="test-agent", goal="Test turn persistence")
        result = run.create_model_turn(
            messages=[{"role": "user", "content": "Hello"}],
            model="gpt-4",
        )
        run.finish(result.assistant_message)

        # Verify turns endpoint
        turns_resp = client.get(f"/api/runs/{run.run_id}/turns")
        assert turns_resp.status_code == 200
        turns = turns_resp.json()
        assert len(turns) == 1
        turn = turns[0]
        assert turn["seq"] > 0
        assert turn["prompt_tokens"] == 10
        assert turn["completion_tokens"] == 5
        assert turn["total_tokens"] == 15
        assert turn["assistant_message"]["content"] == "Hello"
        assert len(turn["messages"]) == 1
        assert turn["messages"][0]["role"] == "user"

    def test_create_turn_updates_run_counters(self, test_client) -> None:
        client = test_client
        sdk = VisorClient(base_url="http://testserver", http_client=client)

        run = sdk.start_run(agent_name="test-agent", goal="Test counters")
        result = run.create_model_turn(
            messages=[{"role": "user", "content": "Hello"}],
            model="gpt-4",
        )
        run.finish(result.assistant_message)

        run_resp = client.get(f"/api/runs/{run.run_id}")
        run_data = run_resp.json()
        assert run_data["total_prompt_tokens"] == 10
        assert run_data["total_completion_tokens"] == 5

    def test_multiple_turns_accumulate_tokens(self, test_client) -> None:
        client = test_client
        sdk = VisorClient(base_url="http://testserver", http_client=client)

        run = sdk.start_run(agent_name="test-agent", goal="Test multiple turns")
        # First turn
        result1 = run.create_model_turn(
            messages=[{"role": "user", "content": "Hello"}],
            model="gpt-4",
        )
        # Second turn (simulating tool result)
        result2 = run.create_model_turn(
            messages=[
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hello"},
                {"role": "tool", "content": "{\"result\": \"ok\"}"},
            ],
            model="gpt-4",
        )
        run.finish(result2.assistant_message)

        turns_resp = client.get(f"/api/runs/{run.run_id}/turns")
        turns = turns_resp.json()
        assert len(turns) == 2

        run_resp = client.get(f"/api/runs/{run.run_id}")
        run_data = run_resp.json()
        assert run_data["total_prompt_tokens"] == 18  # 10 + 8
        assert run_data["total_completion_tokens"] == 7  # 5 + 2

    def test_turn_links_events(self, test_client) -> None:
        client = test_client
        sdk = VisorClient(base_url="http://testserver", http_client=client)

        run = sdk.start_run(agent_name="test-agent", goal="Test event linking")
        result = run.create_model_turn(
            messages=[{"role": "user", "content": "Hello"}],
            model="gpt-4",
        )
        run.finish(result.assistant_message)

        events_resp = client.get(f"/api/runs/{run.run_id}/events")
        assert events_resp.status_code == 200
        events = events_resp.json()
        # model.responded and tool.requested should have turn_id
        linked_events = [e for e in events if e["type"] in ("model.responded", "tool.requested")]
        assert len(linked_events) >= 1
        for evt in linked_events:
            assert evt["turn_id"] is not None
