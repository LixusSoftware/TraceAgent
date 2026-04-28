from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from trace_agent_server.config import Settings
from trace_agent_server.main import create_app
from trace_agent_sdk import TraceAgentClient
from trace_agent_server.services.provider import ProviderTurnRequest, ProviderTurnResponse


class NoopProvider:
    provider_name = "openai"

    def generate_turn(self, request: ProviderTurnRequest) -> ProviderTurnResponse:  # pragma: no cover
        return ProviderTurnResponse(
            assistant_message={"role": "assistant", "content": "noop"},
            summary="noop",
        )


def build_test_clients(tmp_path: Path) -> tuple[TestClient, TraceAgentClient]:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'test-wrappers.db'}",
        cors_origins=["http://localhost:5173"],
    )
    app = create_app(settings)
    app.state.provider_registry = {"openai": NoopProvider()}
    test_client = TestClient(app)
    sdk_client = TraceAgentClient(base_url="http://testserver", http_client=test_client)
    return test_client, sdk_client


def test_command_wrapper_records_success_and_stdout_summary(tmp_path: Path) -> None:
    test_client, sdk_client = build_test_clients(tmp_path)
    run = sdk_client.start_run("wrapper-agent", "Run a successful command")

    completed = run.commands.run([sys.executable, "-c", "print('wrapper ok')"])

    assert completed.returncode == 0
    overview = test_client.get(f"/api/runs/{run.run_id}").json()
    assert overview["execution"]["command_count"] == 1
    assert overview["command_chain"][0]["status"] == "succeeded"
    assert overview["command_chain"][0]["stdout_summary"] == "wrapper ok\n"


def test_command_wrapper_records_failure_without_raise_when_check_is_false(tmp_path: Path) -> None:
    test_client, sdk_client = build_test_clients(tmp_path)
    run = sdk_client.start_run("wrapper-agent", "Run a failing command")

    completed = run.commands.run(
        [sys.executable, "-c", "import sys; print('boom', file=sys.stderr); sys.exit(1)"],
        check=False,
    )

    assert completed.returncode == 1
    overview = test_client.get(f"/api/runs/{run.run_id}").json()
    assert overview["execution"]["command_count"] == 1
    assert overview["execution"]["command_failure_count"] == 1
    assert overview["command_chain"][0]["status"] == "failed"
    assert overview["command_chain"][0]["stderr_summary"] == "boom\n"


def test_command_wrapper_persists_observation_before_raise(tmp_path: Path) -> None:
    test_client, sdk_client = build_test_clients(tmp_path)
    run = sdk_client.start_run("wrapper-agent", "Raise after recording command failure")

    with pytest.raises(Exception):
        run.commands.run(
            [sys.executable, "-c", "import sys; sys.stderr.write('timeoutish failure'); sys.exit(2)"],
            check=True,
        )

    overview = test_client.get(f"/api/runs/{run.run_id}").json()
    assert overview["execution"]["command_count"] == 1
    assert overview["error_count"] == 1
    assert overview["command_chain"][0]["status"] == "failed"


def test_file_wrappers_record_create_update_delete_and_patch(tmp_path: Path) -> None:
    test_client, sdk_client = build_test_clients(tmp_path)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "notes.txt"
    target.write_text("before\n", encoding="utf-8")
    run = sdk_client.start_run("wrapper-agent", "Track file side effects")

    content = run.files.read_text(str(target))
    run.files.write_text(str(target), "after\n")
    run.files.patch_text(str(target), "patched\n", diff_text="@@ -1 +1 @@\n-after\n+patched")
    run.files.delete(str(target))

    assert content == "before\n"
    overview = test_client.get(f"/api/runs/{run.run_id}").json()
    assert overview["execution"]["file_read_count"] == 1
    assert overview["execution"]["file_write_count"] == 3
    assert overview["execution"]["patch_count"] == 1
    assert [item["change_type"] for item in overview["file_activity"] if item["event_type"] == "file.written"] == [
        "update",
        "update",
        "delete",
    ]
    assert overview["patch_activity"][0]["diff_summary"].startswith("@@ -1 +1 @@")


def test_wrappers_truncate_large_command_output_and_patch_summary(tmp_path: Path) -> None:
    test_client, sdk_client = build_test_clients(tmp_path)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "verbose.txt"
    target.write_text("line-0\n", encoding="utf-8")
    run = sdk_client.start_run("wrapper-agent", "Summaries stay truncated")
    long_output = "x" * 300
    long_diff = "@@ -1 +1 @@\n-" + ("a" * 220) + "\n+" + ("b" * 220)

    run.commands.run([sys.executable, "-c", f"print('{long_output}')"])
    run.files.patch_text(str(target), "line-1\n", diff_text=long_diff)

    overview = test_client.get(f"/api/runs/{run.run_id}").json()
    assert overview["command_chain"][0]["stdout_summary"].endswith("...")
    assert len(overview["command_chain"][0]["stdout_summary"]) < len(long_output)
    assert overview["patch_activity"][0]["diff_summary"].endswith("...")
