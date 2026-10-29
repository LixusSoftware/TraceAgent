from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from trace_agent_sdk import RunSession, TraceAgentClient


class Backend:
    """In-memory stand-in for the TraceAgent API that records every request."""

    def __init__(self) -> None:
        self.requests: list[tuple[str, str, dict[str, Any]]] = []
        self.responses: dict[str, list[httpx.Response]] = {}

    def queue(self, path_suffix: str, *responses: httpx.Response) -> None:
        self.responses.setdefault(path_suffix, []).extend(responses)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else {}
        self.requests.append((request.method, request.url.path, body))
        for suffix, queued in self.responses.items():
            if request.url.path.endswith(suffix) and queued:
                return queued.pop(0)
        if request.url.path == "/api/runs":
            return httpx.Response(200, json={"run_id": "run-1"})
        return httpx.Response(200, json={"status": "ok"})

    def observations(self, kind: str | None = None) -> list[dict[str, Any]]:
        found = [
            obs
            for _, path, body in self.requests
            if path.endswith("/observations")
            for obs in body["observations"]
        ]
        return [obs for obs in found if kind is None or obs["kind"] == kind]


@pytest.fixture
def backend() -> Backend:
    return Backend()


@pytest.fixture
def client(backend) -> TraceAgentClient:
    http = httpx.Client(transport=httpx.MockTransport(backend), base_url="http://trace.test")
    return TraceAgentClient(base_url="http://trace.test", http_client=http)


@pytest.fixture
def run(client) -> RunSession:
    return client.start_run("agent", "goal", metadata={"env": "test"})


class TestClient:
    def test_start_run_posts_and_returns_a_bound_session(self, client, backend) -> None:
        session = client.start_run("agent", "goal", metadata={"env": "test"})

        assert session.run_id == "run-1"
        assert (session.agent_name, session.goal, session.metadata) == ("agent", "goal", {"env": "test"})
        assert backend.requests[0] == ("POST", "/api/runs", {"agent_name": "agent", "goal": "goal", "metadata": {"env": "test"}})

    def test_error_responses_raise_with_the_server_detail(self, client, backend) -> None:
        backend.queue("/api/runs", httpx.Response(404, json={"detail": "Run not found."}))

        with pytest.raises(httpx.HTTPStatusError, match="404 for /api/runs: Run not found."):
            client.start_run("agent", "goal")

    def test_error_responses_without_json_fall_back_to_the_body_text(self, client, backend) -> None:
        backend.queue("/api/runs", httpx.Response(502, text="bad gateway"))

        with pytest.raises(httpx.HTTPStatusError, match="bad gateway"):
            client.start_run("agent", "goal")

    def test_api_key_and_base_url_configure_the_http_client(self) -> None:
        client = TraceAgentClient(base_url="http://trace.test/", api_key="secret")

        assert client.http.headers["Authorization"] == "Bearer secret"
        assert str(client.http.base_url).rstrip("/") == "http://trace.test"


class TestRecording:
    def test_command_renders_lists_and_summarizes_output(self, run, backend) -> None:
        run.record_command(["python", "-m", "pytest"], status="failed", output={"stdout": "x"}, exit_code=1, cwd=".")

        obs = backend.observations("command")[0]
        assert obs["command"] == "python -m pytest"
        assert obs["status"] == "failed"
        assert obs["exit_code"] == 1
        assert obs["step_id"].startswith("command-")
        assert json.loads(obs["output_summary"]) == {"stdout": "x"}

    def test_file_read_hashes_the_content(self, run, backend) -> None:
        run.record_file_read("src/app.py", content="print('x')")

        obs = backend.observations("file_read")[0]
        assert obs["path"] == "src/app.py"
        assert obs["extension"] == ".py"
        assert obs["size_bytes"] == len("print('x')")
        assert len(obs["content_hash"]) == 64

    def test_file_write_counts_added_and_removed_lines(self, run, backend) -> None:
        run.record_file_write("a.txt", change_type="update", before_content="one\ntwo\n", after_content="one\nthree\nfour\n")

        obs = backend.observations("file_write")[0]
        assert (obs["line_additions"], obs["line_deletions"]) == (2, 1)
        assert obs["before_hash"] != obs["after_hash"]
        assert obs["change_type"] == "update"

    def test_file_write_without_changes_reports_no_diff(self, run, backend) -> None:
        run.record_file_write("a.txt", before_content="same", after_content="same")

        obs = backend.observations("file_write")[0]
        assert obs["diff_summary"] == "No textual diff."
        assert (obs["line_additions"], obs["line_deletions"]) == (0, 0)

    def test_patch_prefers_the_given_diff_text(self, run, backend) -> None:
        run.record_patch("a.py", diff_text="--- custom diff", before_content="a", after_content="b")

        assert backend.observations("patch")[0]["diff_summary"] == "--- custom diff"

    def test_artifact_carries_a_content_hash(self, run, backend) -> None:
        run.record_artifact("report", "weekly", "summary", content={"k": 1}, metadata={"source": "test"})

        artifact = backend.observations("artifact")[0]["artifact"]
        assert (artifact["kind"], artifact["label"]) == ("report", "weekly")
        assert artifact["metadata"]["source"] == "test"
        assert len(artifact["metadata"]["content_hash"]) == 64

    def test_finish_and_fail_payloads(self, run, backend) -> None:
        run.finish("done", artifacts=[{"kind": "k"}])
        run.fail("ValueError", "boom")

        assert backend.requests[-2] == ("POST", "/api/runs/run-1/finish", {"final_output": "done", "artifacts": [{"kind": "k"}]})
        assert backend.requests[-1] == ("POST", "/api/runs/run-1/fail", {"error_code": "ValueError", "error_summary": "boom"})


class TestToolsAndTurns:
    def test_tool_decorator_builds_the_input_schema(self, run) -> None:
        @run.tool(description="Look things up", redact_fields=["api_key"])
        def search(query: str, limit: int = 5, exact: bool = False) -> str:
            return query

        binding = run.tools["search"]
        assert binding.description == "Look things up"
        assert binding.redact_fields == ["api_key"]
        assert binding.input_schema == {
            "type": "object",
            "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}, "exact": {"type": "boolean"}},
            "required": ["query"],
        }

    def test_tool_description_defaults_to_the_docstring(self, run) -> None:
        @run.tool()
        def lookup(item: str) -> str:
            """Find an item."""
            return item

        assert run.tools["lookup"].description == "Find an item."

    def test_model_turn_runs_requested_tools_and_returns_the_answer(self, run, backend) -> None:
        @run.tool()
        def get_weather(city: str) -> str:
            return f"Sunny in {city}"

        backend.queue(
            "/turns",
            httpx.Response(
                200,
                json={
                    "status": "requires_action",
                    "tool_calls": [{"id": "call-1", "name": "get_weather", "arguments": {"city": "Madrid"}, "step_id": "step-1"}],
                },
            ),
            httpx.Response(200, json={"status": "message", "assistant_message": {"role": "assistant", "content": "It is sunny."}}),
        )

        result = run.create_model_turn([{"role": "user", "content": "Weather?"}], model="m")

        assert result.assistant_message["content"] == "It is sunny."
        assert [t["name"] for t in result.executed_tools] == ["get_weather"]
        posted = next(body for _, path, body in backend.requests if path.endswith("/tool-results"))["results"][0]
        assert posted["status"] == "succeeded"
        assert posted["args"] == {"city": "Madrid"}
        assert posted["step_id"] == "step-1"
        roles = [m["role"] for m in run.messages]
        assert roles == ["user", "assistant", "tool", "assistant"]

    def test_a_failing_tool_is_reported_and_the_error_goes_back_to_the_model(self, run, backend) -> None:
        @run.tool()
        def fetch(url: str) -> str:
            raise ConnectionError("down")

        backend.queue(
            "/turns",
            httpx.Response(
                200,
                json={"status": "requires_action", "tool_calls": [{"id": "c", "name": "fetch", "arguments": {"url": "u"}, "step_id": "s"}]},
            ),
            httpx.Response(200, json={"status": "message", "assistant_message": {"role": "assistant", "content": "failed"}}),
        )

        run.create_model_turn([{"role": "user", "content": "go"}], model="m")

        posted = next(body for _, path, body in backend.requests if path.endswith("/tool-results"))["results"][0]
        assert (posted["status"], posted["error_code"], posted["error_summary"]) == ("failed", "ConnectionError", "down")
        tool_message = next(m for m in run.messages if m["role"] == "tool")
        assert json.loads(tool_message["content"]) == {"error": "down"}

    def test_calling_an_unregistered_tool_raises(self, run) -> None:
        with pytest.raises(KeyError, match="not registered"):
            run._execute_tool({"id": "c", "name": "ghost", "arguments": {}, "step_id": "s"})

    def test_redacted_tool_output_is_masked_in_the_summary(self, run) -> None:
        @run.tool(redact_fields=["token"])
        def login(user: str) -> dict:
            return {"user": user, "token": "abc123"}

        payload, _ = run._execute_tool({"id": "c", "name": "login", "arguments": {"user": "ann"}, "step_id": "s"})

        assert "abc123" not in payload["output_summary"]
        assert "[redacted]" in payload["output_summary"]

    def test_redacted_arguments_are_masked_in_what_is_reported_but_the_tool_gets_them(self, run) -> None:
        received: dict = {}

        @run.tool(redact_fields=["api_key"])
        def charge(customer: str, api_key: str) -> dict:
            received.update(customer=customer, api_key=api_key)
            return {"ok": True}

        payload, _ = run._execute_tool({"id": "c", "name": "charge", "arguments": {"customer": "ana", "api_key": "SECRET"}, "step_id": "s"})

        assert received == {"customer": "ana", "api_key": "SECRET"}
        assert payload["args"] == {"customer": "ana", "api_key": "[redacted]"}

    def test_redacted_arguments_are_masked_when_the_tool_fails_too(self, run) -> None:
        @run.tool(redact_fields=["api_key"])
        def charge(customer: str, api_key: str) -> dict:
            raise ValueError("declined")

        payload, _ = run._execute_tool({"id": "c", "name": "charge", "arguments": {"customer": "ana", "api_key": "SECRET"}, "step_id": "s"})

        assert payload["status"] == "failed"
        assert payload["args"]["api_key"] == "[redacted]"


class TestIntegrationsFactories:
    def test_langchain_callback_is_bound_to_the_run(self, run) -> None:
        pytest.importorskip("trace_agent_langchain")
        callback = run.as_langchain_callback(record_chain_events=False)

        assert callback.run_session is run
        assert callback.record_chain_events is False

    def test_pydantic_ai_capability_is_bound_to_the_run(self, run) -> None:
        pytest.importorskip("trace_agent_pydantic_ai")
        capability = run.as_pydantic_ai_capability(record_node_events=True, failure_cooldown=5, flush_timeout=1)

        assert capability.run_session is run
        assert (capability.record_node_events, capability.failure_cooldown, capability.flush_timeout) == (True, 5, 1)
