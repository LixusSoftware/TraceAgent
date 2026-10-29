from __future__ import annotations

import threading

import pytest
from fastapi.testclient import TestClient

from trace_agent_server.config import Settings
from trace_agent_server.main import create_app
from trace_agent_server.models import Event, Run
from trace_agent_server.services.events import record_event

WRITERS = 6
EVENTS_EACH = 25


@pytest.fixture
def app(tmp_path):
    return create_app(Settings(database_url=f"sqlite:///{tmp_path / 'writers.db'}", cors_origins=["http://localhost:5173"]))


class TestSeveralWritersOnOneRun:
    """The capability posts from a background thread while the agent records by hand: both write to the same run."""

    def test_events_recorded_at_the_same_time_never_collide(self, app) -> None:
        with app.state.session_factory() as session:
            run = Run(agent_name="agent", goal="goal")
            session.add(run)
            session.commit()
            run_id = run.id

        errors: list[BaseException] = []
        start = threading.Barrier(WRITERS)

        def write(writer: int) -> None:
            try:
                start.wait()
                for index in range(EVENTS_EACH):
                    # Each request loads the run, records an event and commits, as the endpoints do.
                    with app.state.session_factory() as session:
                        run = session.get(Run, run_id)
                        record_event(session, run, actor="sdk", event_type="tool.started", summary=f"writer {writer} event {index}")
                        session.commit()
            except BaseException as exc:  # noqa: BLE001 - reported by the test below
                errors.append(exc)

        threads = [threading.Thread(target=write, args=(writer,)) for writer in range(WRITERS)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=120)

        assert errors == []
        with app.state.session_factory() as session:
            sequence = [seq for (seq,) in session.query(Event.seq).filter_by(run_id=run_id).order_by(Event.seq)]
            assert session.get(Run, run_id).last_event_seq == WRITERS * EVENTS_EACH
        assert sequence == list(range(1, WRITERS * EVENTS_EACH + 1))

    def test_requests_to_the_same_run_at_the_same_time_all_succeed(self, app) -> None:
        client = TestClient(app)
        run_id = client.post("/api/runs", json={"agent_name": "agent", "goal": "goal"}).json()["run_id"]
        failures: list[int] = []
        start = threading.Barrier(4)

        def post(writer: int) -> None:
            start.wait()
            for index in range(10):
                response = client.post(
                    f"/api/runs/{run_id}/observations",
                    json={"observations": [{"kind": "command", "command": f"echo {writer}-{index}", "step_id": f"c-{writer}-{index}", "status": "succeeded", "exit_code": 0}]},
                )
                if response.status_code != 200:
                    failures.append(response.status_code)

        threads = [threading.Thread(target=post, args=(writer,)) for writer in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=120)

        assert failures == []
        with app.state.session_factory() as session:
            seqs = [seq for (seq,) in session.query(Event.seq).filter_by(run_id=run_id).order_by(Event.seq)]
        assert seqs == list(range(1, len(seqs) + 1))
        assert len(seqs) == 1 + 4 * 10 * 2  # run.started, then command.started and command.succeeded for each command
