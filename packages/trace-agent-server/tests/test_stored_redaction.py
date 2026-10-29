from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from trace_agent_sdk import TraceAgentClient
from trace_agent_server.config import Settings
from trace_agent_server.main import create_app
from trace_agent_server.models import Event, Turn
from trace_agent_server.services.provider import ProviderToolCall, ProviderTurnRequest, ProviderTurnResponse
from trace_agent_server.services.stored_redaction import redact_messages, redact_tool_calls

SECRET = "SECRET-KEY-123"
CARD = "4111111111111111"


class ChargingProvider:
    """Asks for the `charge` tool once, then answers. Keeps what it was sent."""

    provider_name = "openai"

    def __init__(self) -> None:
        self.seen: list[list[dict]] = []

    def generate_turn(self, request: ProviderTurnRequest) -> ProviderTurnResponse:
        self.seen.append(request.messages)
        if not any(m.get("role") == "tool" for m in request.messages):
            return ProviderTurnResponse(
                assistant_message={
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {"id": "call_1", "type": "function", "function": {"name": "charge", "arguments": json.dumps({"customer": "ana", "api_key": SECRET})}}
                    ],
                },
                tool_calls=[ProviderToolCall(id="call_1", name="charge", arguments={"customer": "ana", "api_key": SECRET}, step_id="step-1")],
                summary="calls charge",
            )
        return ProviderTurnResponse(assistant_message={"role": "assistant", "content": "Charged."}, summary="Charged.")


@pytest.fixture
def provider() -> ChargingProvider:
    return ChargingProvider()


@pytest.fixture
def client(tmp_path, provider) -> TestClient:
    app = create_app(Settings(database_url=f"sqlite:///{tmp_path / 'test.db'}", cors_origins=["http://localhost:5173"]))
    app.state.provider_registry = {"openai": provider}
    return TestClient(app)


def everything_stored(client: TestClient) -> str:
    with client.app.state.session_factory() as session:
        events = [(e.summary, e.payload_full, e.event_metadata) for e in session.query(Event).all()]
        turns = [(t.messages, t.assistant_message, t.tool_calls) for t in session.query(Turn).all()]
    return json.dumps([events, turns], default=str)


class TestToolRedactionOnStoredData:
    def run_agent(self, client: TestClient, redact_fields: list[str]):
        run = TraceAgentClient("http://testserver", http_client=client).start_run("billing", "Charge ana")
        received: dict = {}

        @run.tool(name="charge", description="Charge a customer.", redact_fields=redact_fields)
        def charge(customer: str, api_key: str) -> dict:
            received["args"] = {"customer": customer, "api_key": api_key}
            return {"ok": True, "customer": customer, "card": CARD}

        result = run.create_model_turn([{"role": "user", "content": "Charge ana"}], model="m")
        run.finish(result.assistant_message["content"])
        return received, result

    def test_nothing_sensitive_is_stored_anywhere(self, client, provider) -> None:
        self.run_agent(client, ["api_key", "card"])

        stored = everything_stored(client)
        assert SECRET not in stored
        assert CARD not in stored
        assert "[redacted]" in stored

    def test_the_tool_and_the_model_still_get_the_real_data(self, client, provider) -> None:
        received, _ = self.run_agent(client, ["api_key", "card"])

        assert received["args"] == {"customer": "ana", "api_key": SECRET}
        tool_message = next(m for m in provider.seen[-1] if m.get("role") == "tool")
        assert CARD in tool_message["content"]

    def test_the_agent_is_handed_the_real_tool_call_arguments(self, client, provider) -> None:
        _, result = self.run_agent(client, ["api_key", "card"])

        assert result.executed_tools[0]["status"] == "succeeded"

    def test_without_redact_fields_the_data_is_stored_as_before(self, client, provider) -> None:
        self.run_agent(client, [])

        assert SECRET in everything_stored(client)

    def test_other_values_are_kept_in_full(self, client, provider) -> None:
        self.run_agent(client, ["api_key"])

        stored = everything_stored(client)
        assert "ana" in stored
        assert CARD in stored  # `card` was not listed, so it is not masked


class TestRedactMessages:
    def test_masks_the_arguments_of_a_call_and_the_result_of_its_tool(self) -> None:
        messages = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": None, "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "charge", "arguments": json.dumps({"api_key": "k", "n": 1})}}]},
            {"role": "tool", "tool_call_id": "c1", "content": json.dumps({"card": "4111", "ok": True})},
        ]

        masked = redact_messages(messages, {"charge": ["api_key", "card"]})

        assert json.loads(masked[1]["tool_calls"][0]["function"]["arguments"]) == {"api_key": "[redacted]", "n": 1}
        assert json.loads(masked[2]["content"]) == {"card": "[redacted]", "ok": True}
        assert messages[2]["content"] == json.dumps({"card": "4111", "ok": True})  # the original is untouched

    def test_a_tool_without_redact_fields_and_plain_text_are_left_alone(self) -> None:
        messages = [
            {"role": "assistant", "tool_calls": [{"id": "c1", "function": {"name": "other", "arguments": '{"a": 1}'}}]},
            {"role": "tool", "tool_call_id": "c1", "content": "plain text"},
        ]

        assert redact_messages(messages, {"charge": ["api_key"]}) == messages
        assert redact_messages(messages, {}) is messages

    def test_accents_survive_the_masking(self) -> None:
        messages = [
            {"role": "assistant", "tool_calls": [{"id": "c1", "function": {"name": "t", "arguments": json.dumps({"pw": "x", "msg": "bajó"}, ensure_ascii=False)}}]},
        ]

        masked = redact_messages(messages, {"t": ["pw"]})

        assert "bajó" in masked[0]["tool_calls"][0]["function"]["arguments"]


class TestRedactToolCalls:
    def test_masks_the_arguments_of_the_listed_tools(self) -> None:
        calls = [{"id": "c1", "name": "charge", "arguments": {"api_key": "k", "n": 1}, "step_id": "s"}]

        assert redact_tool_calls(calls, {"charge": ["api_key"]})[0]["arguments"] == {"api_key": "[redacted]", "n": 1}
        assert calls[0]["arguments"]["api_key"] == "k"
