from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from trace_agent_server.config import Settings
from trace_agent_server.main import create_app
from trace_agent_server.models import Event, Run


@pytest.fixture
def client(tmp_path) -> TestClient:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        cors_origins=["http://localhost:5173"],
    )
    return TestClient(create_app(settings))


def start_run(client: TestClient) -> str:
    response = client.post("/api/runs", json={"agent_name": "framework-agent", "goal": "test"})
    assert response.status_code == 200
    return response.json()["run_id"]


def observe(client: TestClient, run_id: str, **observation) -> None:
    response = client.post(f"/api/runs/{run_id}/observations", json={"observations": [observation]})
    assert response.status_code == 200, response.text


def load_run(client: TestClient, run_id: str) -> Run:
    with client.app.state.session_factory() as session:
        run = session.get(Run, run_id)
        session.expunge(run)
        return run


class TestLlmCallUsage:
    def test_succeeded_call_fills_provider_model_and_tokens(self, client) -> None:
        run_id = start_run(client)
        observe(client, run_id, kind="llm_call", step_id="llm-1", status="running", model="m-1")
        observe(
            client,
            run_id,
            kind="llm_call",
            step_id="llm-1",
            status="succeeded",
            provider="anthropic",
            model="m-1",
            metadata={"prompt_tokens": 100, "completion_tokens": 20},
        )
        observe(
            client,
            run_id,
            kind="llm_call",
            step_id="llm-2",
            status="succeeded",
            provider="anthropic",
            model="m-1",
            metadata={"prompt_tokens": 50, "completion_tokens": 5},
        )

        run = load_run(client, run_id)
        assert run.provider == "anthropic"
        assert run.model == "m-1"
        assert run.total_prompt_tokens == 150
        assert run.total_completion_tokens == 25

    def test_first_provider_and_model_are_kept(self, client) -> None:
        run_id = start_run(client)
        for provider, model in (("openai", "first"), ("anthropic", "second")):
            observe(client, run_id, kind="llm_call", status="succeeded", provider=provider, model=model)

        run = load_run(client, run_id)
        assert (run.provider, run.model) == ("openai", "first")

    def test_running_and_failed_calls_do_not_count(self, client) -> None:
        run_id = start_run(client)
        for status in ("running", "failed"):
            observe(
                client,
                run_id,
                kind="llm_call",
                status=status,
                provider="openai",
                model="m",
                metadata={"prompt_tokens": 99, "completion_tokens": 99},
            )

        run = load_run(client, run_id)
        assert run.provider is None
        assert run.model is None
        assert run.total_prompt_tokens == 0
        assert run.total_completion_tokens == 0

    def test_unknown_provider_and_invalid_tokens_are_ignored(self, client) -> None:
        run_id = start_run(client)
        observe(
            client,
            run_id,
            kind="llm_call",
            status="succeeded",
            provider="unknown",
            metadata={"prompt_tokens": True, "completion_tokens": "12", "total_tokens": -3},
        )

        run = load_run(client, run_id)
        assert run.provider is None
        assert run.total_prompt_tokens == 0
        assert run.total_completion_tokens == 0

    def test_overview_counts_llm_calls_as_model_turns(self, client) -> None:
        run_id = start_run(client)
        for step in ("llm-1", "llm-2"):
            observe(client, run_id, kind="llm_call", step_id=step, status="running")
            observe(client, run_id, kind="llm_call", step_id=step, status="succeeded", provider="openai", model="m")

        execution = client.get(f"/api/runs/{run_id}").json()["execution"]
        assert execution["model_turn_count"] == 2
        assert execution["assistant_turn_count"] == 2


class TestLlmCallContent:
    content = {
        "input_messages": [{"role": "user", "parts": [{"type": "text", "content": "¿Por qué bajó el OEE?"}]}],
        "output_messages": [{"role": "assistant", "parts": [{"type": "text", "content": "Por las paradas."}]}],
    }

    def completed_event(self, client, run_id: str) -> Event:
        with client.app.state.session_factory() as session:
            event = session.query(Event).filter_by(run_id=run_id, type="llm.completed").one()
            session.expunge(event)
            return event

    def test_what_the_model_was_asked_and_answered_is_stored_with_the_event(self, client) -> None:
        run_id = start_run(client)
        observe(client, run_id, kind="llm_call", step_id="l1", status="succeeded", provider="openai", model="m",
                content=self.content, metadata={"prompt_tokens": 3})

        event = self.completed_event(client, run_id)
        assert event.payload_full["input_messages"] == self.content["input_messages"]
        assert event.payload_full["output_messages"] == self.content["output_messages"]
        assert event.payload_full["prompt_tokens"] == 3
        # The content is not copied into the metadata that is always kept and listed.
        assert "input_messages" not in event.event_metadata

    def test_it_is_not_stored_when_full_payloads_are_off(self, tmp_path) -> None:
        app = create_app(Settings(database_url=f"sqlite:///{tmp_path / 'off.db'}", cors_origins=["http://localhost:5173"], capture_full_payloads=False))
        client = TestClient(app)
        run_id = start_run(client)
        observe(client, run_id, kind="llm_call", step_id="l1", status="succeeded", provider="openai", model="m", content=self.content)

        assert self.completed_event(client, run_id).payload_full is None

    def test_a_call_without_content_is_stored_as_before(self, client) -> None:
        run_id = start_run(client)
        observe(client, run_id, kind="llm_call", step_id="l1", status="succeeded", provider="openai", model="m", metadata={"prompt_tokens": 3})

        assert self.completed_event(client, run_id).payload_full == {"prompt_tokens": 3}


class TestTokenUsageOfFrameworkRuns:
    def model_call(self, client, run_id, step, **tokens) -> None:
        observe(client, run_id, kind="llm_call", step_id=step, status="succeeded", provider="openai", model="m", metadata=tokens)

    def test_the_run_overview_sums_model_calls(self, client) -> None:
        run_id = start_run(client)
        self.model_call(client, run_id, "llm-1", prompt_tokens=10, completion_tokens=2)
        self.model_call(client, run_id, "llm-2", prompt_tokens=5, completion_tokens=1)

        usage = client.get(f"/api/runs/{run_id}").json()["execution"]["token_usage"]
        assert usage == {"prompt_tokens": 15, "completion_tokens": 3, "total_tokens": 18, "reasoning_tokens": 0}

    def test_a_reported_total_wins_over_the_sum(self, client) -> None:
        run_id = start_run(client)
        self.model_call(client, run_id, "llm-1", prompt_tokens=10, completion_tokens=2, total_tokens=20)

        assert client.get(f"/api/runs/{run_id}").json()["execution"]["token_usage"]["total_tokens"] == 20

    def test_compare_reports_the_token_difference_between_two_runs(self, client) -> None:
        left, right = start_run(client), start_run(client)
        self.model_call(client, left, "llm-1", prompt_tokens=10, completion_tokens=2)
        self.model_call(client, right, "llm-1", prompt_tokens=30, completion_tokens=4)
        for run_id in (left, right):
            assert client.post(f"/api/runs/{run_id}/finish", json={"final_output": "done"}).status_code == 200

        response = client.get("/api/runs/compare", params={"left_run_id": left, "right_run_id": right})

        assert response.status_code == 200
        assert response.json()["overview_diff"]["token_total_delta"] == (30 + 4) - (10 + 2)


class TestToolResultParent:
    def tool_result(self, **extra) -> dict:
        return {
            "call_id": "call-1",
            "name": "get_weather",
            "step_id": "tool-1",
            "status": "succeeded",
            "args": {"city": "Madrid"},
            "output_summary": "Sunny",
            "duration_ms": 1234,
            **extra,
        }

    def test_parent_step_id_is_stored_on_both_events(self, client) -> None:
        run_id = start_run(client)
        response = client.post(
            f"/api/runs/{run_id}/tool-results",
            json={"results": [self.tool_result(parent_step_id="run-1")]},
        )
        assert response.status_code == 200

        with client.app.state.session_factory() as session:
            events = session.query(Event).filter_by(run_id=run_id, step_id="tool-1").all()
        assert {event.type for event in events} == {"tool.started", "tool.succeeded"}
        assert {event.parent_step_id for event in events} == {"run-1"}

    def test_parent_step_id_is_optional(self, client) -> None:
        run_id = start_run(client)
        response = client.post(f"/api/runs/{run_id}/tool-results", json={"results": [self.tool_result()]})
        assert response.status_code == 200

        with client.app.state.session_factory() as session:
            events = session.query(Event).filter_by(run_id=run_id, step_id="tool-1").all()
        assert {event.parent_step_id for event in events} == {None}


def post_tool(client: TestClient, run_id: str, step_id: str, name: str, *, status: str = "succeeded", args: dict | None = None) -> None:
    result = {"call_id": step_id, "name": name, "step_id": step_id, "status": status, "args": args or {}}
    response = client.post(f"/api/runs/{run_id}/tool-results", json={"results": [result]})
    assert response.status_code == 200, response.text


def explanation(client: TestClient, run_id: str) -> dict:
    # Decisions are derived when a run finishes, not while it is still running.
    assert client.post(f"/api/runs/{run_id}/finish", json={"final_output": "done"}).status_code == 200
    response = client.get(f"/api/runs/{run_id}/explanation")
    assert response.status_code == 200, response.text
    return response.json()


class TestDecisionsFromFrameworkTools:
    """Integrations never emit tool.requested, so the start of a tool is the choice."""

    def test_each_tool_start_becomes_a_tool_choice(self, client) -> None:
        run_id = start_run(client)
        post_tool(client, run_id, "t1", "get_weather", args={"city": "Madrid"})
        post_tool(client, run_id, "t2", "get_news", args={"topic": "ai"})

        labels = [d["label"] for d in explanation(client, run_id)["decisions"] if d["kind"] == "tool_choice"]
        assert labels == ["Selected get_weather", "Selected get_news"]

    def test_a_failure_followed_by_the_same_tool_is_a_retry_then_a_recovery(self, client) -> None:
        run_id = start_run(client)
        post_tool(client, run_id, "t1", "lookup", status="failed")
        post_tool(client, run_id, "t2", "lookup", status="succeeded")

        kinds = [d["kind"] for d in explanation(client, run_id)["decisions"]]
        assert "retry" in kinds
        assert "recovery" in kinds
        assert client.get(f"/api/runs/{run_id}").json()["retry_count"] == 1

    def test_repeating_the_same_call_is_flagged_as_a_loop(self, client) -> None:
        run_id = start_run(client)
        for step in ("t1", "t2", "t3"):
            post_tool(client, run_id, step, "search", args={"q": "same"})

        flags = explanation(client, run_id)["flags"]
        assert any(flag["type"] == "loop" for flag in flags)

    def test_a_repeated_call_is_one_flag_with_its_count_in_plain_words(self, client) -> None:
        run_id = start_run(client)
        for step in ("t1", "t2", "t3", "t4", "t5", "t6"):
            post_tool(client, run_id, step, "search", args={"q": "same"})

        loops = [flag for flag in explanation(client, run_id)["flags"] if flag["type"] == "loop"]

        assert len(loops) == 1
        assert loops[0]["label"] == "search was called 6 times with the same arguments."
        assert loops[0]["metadata"]["count"] == 6
        assert len(loops[0]["event_ids"]) == 6

    def test_different_programs_that_share_a_long_start_are_not_a_loop(self, client) -> None:
        # The arguments are cut at 160 characters before they are sent: what tells the calls apart is their hash.
        run_id = start_run(client)
        common = "# OEE de las lineas del 14 al 18 de septiembre " * 6
        for step, ending in (("t1", "kpis('L1')"), ("t2", "kpis('L2')"), ("t3", "kpis('L3')")):
            result = {"call_id": step, "name": "ejecutar_python", "step_id": step, "status": "succeeded",
                      "args": {"codigo": common[:157] + "..."}, "args_hash": f"hash-of-the-whole-{ending}"}
            assert client.post(f"/api/runs/{run_id}/tool-results", json={"results": [result]}).status_code == 200

        assert not any(flag["type"] == "loop" for flag in explanation(client, run_id)["flags"])

    def test_the_same_whole_arguments_are_a_loop_even_when_what_was_sent_was_cut(self, client) -> None:
        run_id = start_run(client)
        for step in ("t1", "t2", "t3"):
            result = {"call_id": step, "name": "ejecutar_python", "step_id": step, "status": "succeeded",
                      "args": {"codigo": "x" * 157 + "..."}, "args_hash": "the-same-program"}
            client.post(f"/api/runs/{run_id}/tool-results", json={"results": [result]})

        assert any(flag["type"] == "loop" for flag in explanation(client, run_id)["flags"])

    def test_the_same_tool_with_different_arguments_is_not_a_loop(self, client) -> None:
        run_id = start_run(client)
        for step, query in (("t1", "a"), ("t2", "b"), ("t3", "c")):
            post_tool(client, run_id, step, "search", args={"q": query})

        flags = explanation(client, run_id)["flags"]
        assert not any(flag["type"] == "loop" for flag in flags)

    def test_a_native_tool_request_is_not_counted_twice(self, client) -> None:
        run_id = start_run(client)
        # The native flow records tool.requested and then tool.started under the same step.
        with client.app.state.session_factory() as session:
            from trace_agent_server.services.events import record_event

            run = session.get(Run, run_id)
            record_event(session, run, actor="proxy", event_type="tool.requested", summary="Requested search.", status="requested", step_id="t1", tool_name="search")
            session.commit()
        post_tool(client, run_id, "t1", "search")

        labels = [d["label"] for d in explanation(client, run_id)["decisions"] if d["kind"] == "tool_choice"]
        assert labels == ["Selected search"]


class TestTimelineGroupDuration:
    def test_reported_duration_wins_over_recording_time(self, client) -> None:
        run_id = start_run(client)
        client.post(
            f"/api/runs/{run_id}/tool-results",
            json={
                "results": [
                    {
                        "call_id": "call-1",
                        "name": "slow_tool",
                        "step_id": "tool-1",
                        "status": "succeeded",
                        "duration_ms": 4321,
                    }
                ]
            },
        )

        groups = client.get(f"/api/runs/{run_id}/timeline").json()["groups"]
        tool_group = next(group for group in groups if group["step_id"] == "tool-1")
        assert tool_group["event_count"] == 2
        assert tool_group["duration_ms"] == 4321

    def test_falls_back_to_timestamps_without_a_reported_duration(self, client) -> None:
        run_id = start_run(client)
        observe(client, run_id, kind="chain_step", step_id="chain-1", status="running")
        observe(client, run_id, kind="chain_step", step_id="chain-1", status="succeeded")

        groups = client.get(f"/api/runs/{run_id}/timeline").json()["groups"]
        chain_group = next(group for group in groups if group["step_id"] == "chain-1")
        assert chain_group["duration_ms"] is not None
        assert chain_group["duration_ms"] >= 0
