from __future__ import annotations

import time

from fastapi.testclient import TestClient

from trace_agent_server.config import Settings
from trace_agent_server.main import create_app


def build_app(tmp_path, timeout_seconds: int):
    return create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'sweep.db'}",
            cors_origins=["http://localhost:5173"],
            run_inactivity_timeout_seconds=timeout_seconds,
        )
    )


def wait_for_status(client: TestClient, run_id: str, status: str, seconds: float) -> str:
    deadline = time.time() + seconds
    current = ""
    while time.time() < deadline:
        current = client.get(f"/api/runs/{run_id}").json()["status"]
        if current == status:
            break
        time.sleep(0.25)
    return current


class TestInactivitySweep:
    def test_a_running_server_closes_a_run_whose_agent_disappeared(self, tmp_path) -> None:
        with TestClient(build_app(tmp_path, timeout_seconds=1)) as client:
            run_id = client.post("/api/runs", json={"agent_name": "a", "goal": "g"}).json()["run_id"]

            assert wait_for_status(client, run_id, "failed", seconds=8) == "failed"

            events = client.get(f"/api/runs/{run_id}/events").json()
            events = events if isinstance(events, list) else events["events"]
            assert events[-1]["type"] == "run.failed"
            assert events[-1]["error_code"] == "RunAbandoned"

    def test_a_timeout_of_zero_turns_the_sweep_off(self, tmp_path) -> None:
        with TestClient(build_app(tmp_path, timeout_seconds=0)) as client:
            run_id = client.post("/api/runs", json={"agent_name": "a", "goal": "g"}).json()["run_id"]

            time.sleep(2.5)

            assert client.get(f"/api/runs/{run_id}").json()["status"] == "running"
