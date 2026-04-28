from __future__ import annotations

import json

from fastapi.testclient import TestClient

from trace_agent_server.config import Settings
from trace_agent_server.main import create_app
from trace_agent_sdk import TraceAgentClient
from trace_agent_server.services.provider import ProviderToolCall, ProviderTurnRequest, ProviderTurnResponse


class MultiStepProvider:
    provider_name = "openai"

    def generate_turn(self, request: ProviderTurnRequest) -> ProviderTurnResponse:
        tool_messages = [message for message in request.messages if message.get("role") == "tool"]
        if len(tool_messages) == 0:
            return ProviderTurnResponse(
                tool_calls=[
                    ProviderToolCall(
                        id="call-search",
                        name="search_docs",
                        arguments={"query": "billing retries"},
                        step_id="call-search",
                    )
                ],
                summary="Model requested 1 tool call(s).",
            )
        if len(tool_messages) == 1:
            return ProviderTurnResponse(
                tool_calls=[
                    ProviderToolCall(
                        id="call-report",
                        name="compile_report",
                        arguments={"facts": "billing retries are supported"},
                        step_id="call-report",
                    )
                ],
                summary="Model requested 1 tool call(s).",
            )
        return ProviderTurnResponse(
            assistant_message={"role": "assistant", "content": "Billing retries are active and documented."},
            summary="Billing retries are active and documented.",
        )


class RetryProvider:
    provider_name = "openai"

    def generate_turn(self, request: ProviderTurnRequest) -> ProviderTurnResponse:
        tool_messages = [message for message in request.messages if message.get("role") == "tool"]
        if len(tool_messages) == 0:
            return ProviderTurnResponse(
                tool_calls=[
                    ProviderToolCall(
                        id="call-unstable-1",
                        name="unstable_lookup",
                        arguments={"resource": "pricing"},
                        step_id="lookup-step",
                    )
                ],
                summary="Model requested 1 tool call(s).",
            )
        last_tool_message = json.loads(tool_messages[-1]["content"])
        if "error" in last_tool_message and len(tool_messages) == 1:
            return ProviderTurnResponse(
                tool_calls=[
                    ProviderToolCall(
                        id="call-unstable-2",
                        name="unstable_lookup",
                        arguments={"resource": "pricing"},
                        step_id="lookup-step",
                    )
                ],
                summary="Model requested 1 tool call(s).",
            )
        return ProviderTurnResponse(
            assistant_message={"role": "assistant", "content": "Pricing recovered after retry."},
            summary="Pricing recovered after retry.",
        )


class RedactionProvider:
    provider_name = "openai"

    def generate_turn(self, request: ProviderTurnRequest) -> ProviderTurnResponse:
        tool_messages = [message for message in request.messages if message.get("role") == "tool"]
        if len(tool_messages) == 0:
            return ProviderTurnResponse(
                tool_calls=[
                    ProviderToolCall(
                        id="call-secret",
                        name="fetch_secret",
                        arguments={"token": "super-secret-token", "resource": "internal"},
                        step_id="call-secret",
                    )
                ],
                summary="Model requested 1 tool call(s).",
            )
        return ProviderTurnResponse(
            assistant_message={"role": "assistant", "content": "Secret fetched and sanitized."},
            summary="Secret fetched and sanitized.",
        )


class SimilarityProvider:
    provider_name = "openai"

    def generate_turn(self, request: ProviderTurnRequest) -> ProviderTurnResponse:
        user_prompt = " ".join(str(message.get("content", "")) for message in request.messages if message.get("role") == "user").lower()
        tool_messages = [message for message in request.messages if message.get("role") == "tool"]

        if "weather" in user_prompt and "budget" in user_prompt:
            if len(tool_messages) == 0:
                return ProviderTurnResponse(
                    tool_calls=[
                        ProviderToolCall(
                            id="call-weather",
                            name="weather_lookup",
                            arguments={"city": "madrid"},
                            step_id="weather-step",
                        )
                    ],
                    summary="Model requested 1 tool call(s).",
                )
            if len(tool_messages) == 1:
                return ProviderTurnResponse(
                    tool_calls=[
                        ProviderToolCall(
                            id="call-budget",
                            name="budget_guard",
                            arguments={"budget": 1200},
                            step_id="budget-step",
                            parent_step_id="weather-step",
                        )
                    ],
                    summary="Model requested 1 tool call(s).",
                )
            return ProviderTurnResponse(
                assistant_message={"role": "assistant", "content": "Weather and budget checked."},
                summary="Weather and budget checked.",
            )

        if "weather" in user_prompt:
            if len(tool_messages) == 0:
                return ProviderTurnResponse(
                    tool_calls=[
                        ProviderToolCall(
                            id="call-weather-only",
                            name="weather_lookup",
                            arguments={"city": "madrid"},
                            step_id="weather-only-step",
                        )
                    ],
                    summary="Model requested 1 tool call(s).",
                )
            return ProviderTurnResponse(
                assistant_message={"role": "assistant", "content": "Weather checked."},
                summary="Weather checked.",
            )

        if "budget" in user_prompt:
            if len(tool_messages) == 0:
                return ProviderTurnResponse(
                    tool_calls=[
                        ProviderToolCall(
                            id="call-budget-only",
                            name="budget_guard",
                            arguments={"budget": 800},
                            step_id="budget-only-step",
                        )
                    ],
                    summary="Model requested 1 tool call(s).",
                )
            return ProviderTurnResponse(
                assistant_message={"role": "assistant", "content": "Budget checked."},
                summary="Budget checked.",
            )

        if len(tool_messages) == 0:
            return ProviderTurnResponse(
                tool_calls=[
                    ProviderToolCall(
                        id="call-docs-only",
                        name="search_docs",
                        arguments={"query": "internal docs"},
                        step_id="docs-only-step",
                    )
                ],
                summary="Model requested 1 tool call(s).",
            )
        return ProviderTurnResponse(
            assistant_message={"role": "assistant", "content": "Docs checked."},
            summary="Docs checked.",
        )


def build_test_clients(tmp_path, provider) -> tuple[TestClient, TraceAgentClient]:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        cors_origins=["http://localhost:5173"],
    )
    app = create_app(settings)
    app.state.provider_registry = {"openai": provider}
    test_client = TestClient(app)
    sdk_client = TraceAgentClient(base_url="http://testserver", http_client=test_client)
    return test_client, sdk_client


def execute_similarity_run(
    sdk_client: TraceAgentClient,
    *,
    agent_name: str,
    goal: str,
    fail_weather: bool = False,
    fail_run: bool = False,
):
    run = sdk_client.start_run(agent_name, goal, {"suite": "filters"})

    @run.tool(description="Check the weather.")
    def weather_lookup(city: str) -> dict[str, str]:
        if fail_weather:
            raise RuntimeError(f"weather failed for {city}")
        return {"city": city, "forecast": "clear"}

    @run.tool(description="Validate the budget.")
    def budget_guard(budget: int) -> dict[str, str]:
        return {"budget": str(budget), "status": "ok"}

    @run.tool(description="Search internal docs.")
    def search_docs(query: str) -> dict[str, str]:
        return {"query": query, "match": "doc found"}

    result = run.create_model_turn([{"role": "user", "content": goal}], model="fake-model")
    if fail_run:
        run.fail("manual_failure", "Similarity filter test forced a failed run.")
    else:
        run.finish(result.assistant_message["content"])
    return run


def test_successful_run_generates_timeline_graph_and_explanation(tmp_path) -> None:
    test_client, sdk_client = build_test_clients(tmp_path, MultiStepProvider())
    run = sdk_client.start_run("doc-agent", "Explain billing retries", {"suite": "success"})

    @run.tool(description="Search internal docs.")
    def search_docs(query: str) -> dict[str, str]:
        return {"query": query, "match": "billing retries are supported"}

    @run.tool(description="Compile a short report.")
    def compile_report(facts: str) -> dict[str, str]:
        return {"report": f"Summary: {facts}"}

    result = run.create_model_turn([{"role": "user", "content": "Summarize billing retries."}], model="fake-model")
    run.finish(result.assistant_message["content"])

    runs = test_client.get("/api/runs").json()
    assert len(runs) == 1

    overview = test_client.get(f"/api/runs/{run.run_id}").json()
    assert overview["status"] == "completed"
    assert overview["tool_count"] == 2
    assert overview["execution"]["current_state"] == "completed"
    assert overview["execution"]["model_turn_count"] == 3
    assert overview["execution"]["registered_tool_count"] == 2
    assert len(overview["tool_chain"]) == 2
    assert [item["tool_name"] for item in overview["tool_chain"]] == ["search_docs", "compile_report"]
    assert all(item["status"] == "succeeded" for item in overview["tool_chain"])

    timeline = test_client.get(f"/api/runs/{run.run_id}/timeline").json()
    event_types = [event["type"] for group in timeline["groups"] for event in group["events"]]
    assert "tool.succeeded" in event_types
    assert "run.completed" in event_types
    assert all("event_count" in group for group in timeline["groups"])

    explanation = test_client.get(f"/api/runs/{run.run_id}/explanation").json()
    labels = [decision["label"] for decision in explanation["decisions"]]
    assert "Selected search_docs" in labels
    assert "Selected compile_report" in labels
    assert any("Final outcome" in item["text"] for item in explanation["narrative"])
    assert all(decision["alternatives"] == [] for decision in explanation["decisions"])

    graph = test_client.get(f"/api/runs/{run.run_id}/graph?view=execution").json()
    assert len(graph["nodes"]) >= len(event_types)

    analytics = test_client.get(f"/api/runs/{run.run_id}/analytics").json()
    assert analytics["tool_graph"]["view"] == "tool_chain"
    assert len(analytics["tool_graph"]["nodes"]) == 2
    assert [item["tool_name"] for item in analytics["tool_metrics"]] == ["compile_report", "search_docs"]
    assert analytics["tool_metrics"][0]["avg_duration_ms"] >= 0


def test_retry_and_recovery_are_derived(tmp_path) -> None:
    test_client, sdk_client = build_test_clients(tmp_path, RetryProvider())
    run = sdk_client.start_run("retry-agent", "Recover after a failing lookup")
    attempts = {"count": 0}

    @run.tool(description="Lookup pricing details.")
    def unstable_lookup(resource: str) -> dict[str, str]:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError(f"temporary error for {resource}")
        return {"resource": resource, "status": "ok"}

    result = run.create_model_turn([{"role": "user", "content": "Get pricing and recover if it fails."}], model="fake-model")
    run.finish(result.assistant_message["content"])

    overview = test_client.get(f"/api/runs/{run.run_id}").json()
    assert overview["retry_count"] >= 1
    assert overview["error_count"] == 1
    tool_statuses = [item["status"] for item in overview["tool_chain"]]
    assert "failed" in tool_statuses
    assert "succeeded" in tool_statuses

    explanation = test_client.get(f"/api/runs/{run.run_id}/explanation").json()
    decision_kinds = [decision["kind"] for decision in explanation["decisions"]]
    assert "retry" in decision_kinds
    assert "recovery" in decision_kinds

    analytics = test_client.get(f"/api/runs/{run.run_id}/analytics").json()
    unstable_metrics = next(item for item in analytics["tool_metrics"] if item["tool_name"] == "unstable_lookup")
    assert unstable_metrics["failure_count"] == 1
    assert unstable_metrics["success_count"] == 1


def test_sensitive_fields_are_redacted_in_persisted_summaries(tmp_path) -> None:
    test_client, sdk_client = build_test_clients(tmp_path, RedactionProvider())
    run = sdk_client.start_run("redaction-agent", "Fetch a secret without persisting it")

    @run.tool(description="Fetch an internal secret.", redact_fields=["token"])
    def fetch_secret(token: str, resource: str) -> dict[str, str]:
        return {"token": token, "resource": resource, "value": "sensitive-output"}

    result = run.create_model_turn([{"role": "user", "content": "Fetch the secret."}], model="fake-model")
    run.finish(result.assistant_message["content"])

    timeline = test_client.get(f"/api/runs/{run.run_id}/timeline").json()
    summaries = [event["summary"] for group in timeline["groups"] for event in group["events"]]
    persisted = " ".join(summaries)
    assert "super-secret-token" not in persisted
    assert "[redacted]" in persisted

    explanation = test_client.get(f"/api/runs/{run.run_id}/explanation").json()
    assert all(decision["alternatives"] == [] for decision in explanation["decisions"])


def test_similar_run_filters_apply(tmp_path) -> None:
    test_client, sdk_client = build_test_clients(tmp_path, SimilarityProvider())

    execute_similarity_run(
        sdk_client,
        agent_name="planner-agent",
        goal="Check weather for meetup planning",
    )
    execute_similarity_run(
        sdk_client,
        agent_name="ops-agent",
        goal="Review budget for meetup planning",
    )
    failed_run = execute_similarity_run(
        sdk_client,
        agent_name="planner-agent",
        goal="Check weather for meetup planning",
        fail_weather=True,
        fail_run=True,
    )
    execute_similarity_run(
        sdk_client,
        agent_name="planner-agent",
        goal="Search code docs for onboarding",
    )
    current_run = execute_similarity_run(
        sdk_client,
        agent_name="planner-agent",
        goal="Check weather and budget for meetup planning",
    )

    analytics = test_client.get(f"/api/runs/{current_run.run_id}/analytics").json()
    returned_ids = {item["run_id"] for item in analytics["similar_runs"]}
    assert failed_run.run_id in returned_ids
    assert len(analytics["similar_runs"]) == 4

    same_agent_only = test_client.get(f"/api/runs/{current_run.run_id}/analytics?same_agent_only=true").json()
    assert all(item["agent_name"] == "planner-agent" for item in same_agent_only["similar_runs"])

    failed_only = test_client.get(f"/api/runs/{current_run.run_id}/analytics?status=failed").json()
    assert [item["run_id"] for item in failed_only["similar_runs"]] == [failed_run.run_id]

    shared_tools_only = test_client.get(f"/api/runs/{current_run.run_id}/analytics?shared_tools_only=true").json()
    assert all(item["shared_tools"] for item in shared_tools_only["similar_runs"])
    assert all("docs" not in item["goal"].lower() for item in shared_tools_only["similar_runs"])

    high_score = test_client.get(f"/api/runs/{current_run.run_id}/analytics?min_score=0.4&limit=2").json()
    assert len(high_score["similar_runs"]) == 2
    assert all(item["similarity_score"] >= 0.4 for item in high_score["similar_runs"])


def create_coding_run(
    sdk_client: TraceAgentClient,
    *,
    agent_name: str,
    goal: str,
    command_status: str = "succeeded",
    file_target: str = "app/main.py",
    artifact_summary: str = "Patched main file.",
    final_status: str = "completed",
):
    run = sdk_client.start_run(agent_name, goal, {"suite": "coding"})
    run.record_command(
        ["python", "-m", "pytest", "-q"],
        status=command_status,
        cwd="C:/repo",
        output={"tests": "passed"} if command_status == "succeeded" else None,
        error_code="CommandError" if command_status == "failed" else None,
        error_summary="pytest failed" if command_status == "failed" else None,
        exit_code=1 if command_status == "failed" else 0,
        duration_ms=420,
    )
    run.record_file_read(file_target, content="print('before')\n")
    run.record_file_write(
        file_target,
        before_content="print('before')\n",
        after_content="print('after')\n",
    )
    run.record_patch(
        file_target,
        before_content="print('before')\n",
        after_content="print('after')\n",
    )
    run.record_artifact("report", "patch-report", artifact_summary, content={"summary": artifact_summary})
    if final_status == "failed":
        run.fail("coding_failure", "Coding run ended in failure.")
    else:
        run.finish({"summary": artifact_summary})
    return run


def test_coding_side_effects_are_exposed_in_run_overview(tmp_path) -> None:
    test_client, sdk_client = build_test_clients(tmp_path, MultiStepProvider())
    run = create_coding_run(
        sdk_client,
        agent_name="coding-agent",
        goal="Patch the main file and run tests",
    )

    overview = test_client.get(f"/api/runs/{run.run_id}").json()
    assert overview["execution"]["command_count"] == 1
    assert overview["execution"]["file_read_count"] == 1
    assert overview["execution"]["file_write_count"] == 1
    assert overview["execution"]["patch_count"] == 1
    assert len(overview["command_chain"]) == 1
    assert len(overview["file_activity"]) == 2
    assert len(overview["patch_activity"]) == 1
    assert overview["command_chain"][0]["status"] == "succeeded"
    assert overview["file_activity"][1]["path"] == "app/main.py"


def test_compare_identical_coding_runs_have_no_divergence(tmp_path) -> None:
    test_client, sdk_client = build_test_clients(tmp_path, MultiStepProvider())
    left_run = create_coding_run(
        sdk_client,
        agent_name="coding-agent",
        goal="Patch the main file and run tests",
    )
    right_run = create_coding_run(
        sdk_client,
        agent_name="coding-agent",
        goal="Patch the main file and run tests",
    )

    compare = test_client.get(f"/api/runs/compare?left_run_id={left_run.run_id}&right_run_id={right_run.run_id}").json()
    assert compare["divergence"] is None
    assert compare["root_cause"]["label"] == "no_observable_root_cause"
    assert any(item["relation"] == "shared" for item in compare["command_diff"])


def test_compare_command_failure_is_detected(tmp_path) -> None:
    test_client, sdk_client = build_test_clients(tmp_path, MultiStepProvider())
    left_run = create_coding_run(
        sdk_client,
        agent_name="coding-agent",
        goal="Patch the main file and run tests",
    )
    right_run = create_coding_run(
        sdk_client,
        agent_name="coding-agent",
        goal="Patch the main file and run tests",
        command_status="failed",
        final_status="failed",
    )

    compare = test_client.get(f"/api/runs/compare?left_run_id={left_run.run_id}&right_run_id={right_run.run_id}").json()
    assert compare["divergence"]["first_mismatch_kind"] == "command"
    assert compare["root_cause"]["label"] == "command_failure"
    assert any(item["relation"] == "different" for item in compare["command_diff"])


def test_compare_file_change_divergence_is_detected(tmp_path) -> None:
    test_client, sdk_client = build_test_clients(tmp_path, MultiStepProvider())
    left_run = create_coding_run(
        sdk_client,
        agent_name="coding-agent",
        goal="Patch the main file and run tests",
        file_target="app/main.py",
        artifact_summary="Patched main file.",
    )
    right_run = create_coding_run(
        sdk_client,
        agent_name="coding-agent",
        goal="Patch the main file and run tests",
        file_target="app/other.py",
        artifact_summary="Patched another file.",
    )

    compare = test_client.get(f"/api/runs/compare?left_run_id={left_run.run_id}&right_run_id={right_run.run_id}").json()
    assert compare["root_cause"]["label"] == "file_change_divergence"
    assert any(item["relation"] != "shared" for item in compare["file_diff"])
    assert any(item["relation"] != "shared" for item in compare["artifact_diff"])


def test_compare_retry_without_adaptation_is_detected(tmp_path) -> None:
    test_client, sdk_client = build_test_clients(tmp_path, RetryProvider())

    baseline = sdk_client.start_run("retry-agent", "Recover after a failing lookup", {"suite": "compare"})

    @baseline.tool(name="unstable_lookup", description="Lookup pricing details.")
    def stable_lookup(resource: str) -> dict[str, str]:
        return {"resource": resource, "status": "ok"}

    baseline_result = baseline.create_model_turn(
        [{"role": "user", "content": "Get pricing and recover if it fails."}],
        model="fake-model",
    )
    baseline.finish(baseline_result.assistant_message["content"])

    retry_run = sdk_client.start_run("retry-agent", "Recover after a failing lookup", {"suite": "compare"})
    attempts = {"count": 0}

    @retry_run.tool(name="unstable_lookup", description="Lookup pricing details.")
    def unstable_lookup(resource: str) -> dict[str, str]:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError(f"temporary error for {resource}")
        return {"resource": resource, "status": "ok"}

    retry_result = retry_run.create_model_turn(
        [{"role": "user", "content": "Get pricing and recover if it fails."}],
        model="fake-model",
    )
    retry_run.finish(retry_result.assistant_message["content"])

    compare = test_client.get(f"/api/runs/compare?left_run_id={baseline.run_id}&right_run_id={retry_run.run_id}").json()
    assert compare["root_cause"]["label"] == "retry_without_adaptation"
    assert any(item["relation"] != "shared" for item in compare["tool_diff"])
