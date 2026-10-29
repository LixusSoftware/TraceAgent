from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from trace_agent_server.config import Settings
from trace_agent_server.main import create_app
from trace_agent_server.services.explanation import command_title

SCRIPT = "python -c \n# OEE de las líneas del 14 al 18 de septiembre\nimport json\nkpis = kpis('L1')\nprint(kpis)"


@pytest.fixture
def client(tmp_path) -> TestClient:
    return TestClient(create_app(Settings(database_url=f"sqlite:///{tmp_path / 'flags.db'}", cors_origins=["http://localhost:5173"])))


def run_with_command(client: TestClient, **observation) -> dict:
    run_id = client.post("/api/runs", json={"agent_name": "a", "goal": "g"}).json()["run_id"]
    body = {"kind": "command", "step_id": "c1", **observation}
    assert client.post(f"/api/runs/{run_id}/observations", json={"observations": [body]}).status_code == 200
    assert client.post(f"/api/runs/{run_id}/finish", json={"final_output": "done"}).status_code == 200
    return client.get(f"/api/runs/{run_id}/explanation").json()


class TestCommandTitle:
    def test_uses_the_first_comment_of_a_script(self) -> None:
        assert command_title(SCRIPT) == "OEE de las líneas del 14 al 18 de septiembre"

    def test_without_a_comment_uses_the_first_line_that_is_not_an_import(self) -> None:
        assert command_title("python -c \nimport json\nfrom os import path\nvalor = 1\nprint(valor)") == "valor = 1"

    def test_a_plain_command_stays_and_a_long_one_is_cut(self) -> None:
        assert command_title("pytest -q packages") == "pytest -q packages"
        cut = command_title("python3 -c " + "x = 1; " * 60)
        assert len(cut) == 80
        assert cut.endswith("…")


class TestCommandFailureFlag:
    def test_says_what_failed_and_with_what_code_instead_of_dumping_the_script(self, client) -> None:
        flags = run_with_command(client, command=SCRIPT, status="failed", exit_code=1)["flags"]

        failure = next(flag for flag in flags if flag["type"] == "command_failure")
        assert failure["label"] == "Command failed (exit code 1): OEE de las líneas del 14 al 18 de septiembre"
        assert "import json" not in failure["label"]

    def test_without_an_exit_code_it_still_reads(self, client) -> None:
        flags = run_with_command(client, command="pytest -q", status="failed")["flags"]

        failure = next(flag for flag in flags if flag["type"] == "command_failure")
        assert failure["label"] == "Command failed: pytest -q"
