from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from trace_agent_server.config import Settings
from trace_agent_server.db import get_session
from trace_agent_server.main import create_app
from trace_agent_server.models import Event, Run
from trace_agent_server.services.events import record_event


@pytest.fixture
def test_client(tmp_path) -> TestClient:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        cors_origins=["http://localhost:5173"],
    )
    app = create_app(settings)
    return TestClient(app)


class TestRecordEvent:
    def test_payload_full_saved_when_enabled(self, test_client) -> None:
        client = test_client
        settings = client.app.state.settings
        assert settings.capture_full_payloads is True

        # Create a run manually via DB session
        with client.app.state.session_factory() as session:
            run = Run(
                id="run-test-1",
                agent_name="agent",
                goal="test",
                status="running",
                metadata={},
                explanation_cache={},
                flag_cache=[],
            )
            session.add(run)
            session.commit()

            event = record_event(
                session=session,
                run=run,
                event_type="test.event",
                actor="sdk",
                summary="Test event",
                payload_full={"key": "value", "nested": {"data": 123}},
                payload_hash="abc123",
            )
            session.commit()
            assert event.payload_full is not None
            assert event.payload_full["key"] == "value"
            assert event.payload_hash is not None

    def test_payload_full_none_when_not_passed(self, test_client) -> None:
        client = test_client

        with client.app.state.session_factory() as session:
            run = Run(
                id="run-test-2",
                agent_name="agent",
                goal="test",
                status="running",
                metadata={},
                explanation_cache={},
                flag_cache=[],
            )
            session.add(run)
            session.commit()

            event = record_event(
                session=session,
                run=run,
                event_type="test.event",
                actor="sdk",
                summary="Test event",
                payload_hash="def456",
            )
            session.commit()
            assert event.payload_full is None
            assert event.payload_hash is not None

    def test_sse_notification_on_record_event(self, test_client) -> None:
        client = test_client
        with client.app.state.session_factory() as session:
            run = Run(
                id="run-test-3",
                agent_name="agent",
                goal="test",
                status="running",
                metadata={},
                explanation_cache={},
                flag_cache=[],
            )
            session.add(run)
            session.commit()

            with patch("trace_agent_server.services.events._notify_sse_listeners") as mock_notify:
                record_event(
                    session=session,
                    run=run,
                    event_type="test.event",
                    actor="sdk",
                    summary="Test event",
                )
                mock_notify.assert_called_once()
                args = mock_notify.call_args[0]
                assert args[0] == "run-test-3"
                assert args[1]["type"] == "test.event"


class TestEventsApi:
    def test_list_events_with_filters(self, test_client) -> None:
        client = test_client
        with client.app.state.session_factory() as session:
            run = Run(
                id="run-test-4",
                agent_name="agent",
                goal="test",
                status="running",
                metadata={},
                explanation_cache={},
                flag_cache=[],
            )
            session.add(run)
            session.commit()

            record_event(session, run, event_type="tool.started", actor="sdk", summary="Tool started")
            record_event(session, run, event_type="tool.succeeded", actor="sdk", summary="Tool done")
            record_event(session, run, event_type="model.requested", actor="proxy", summary="Model call")
            session.commit()

        # Filter by type
        resp = client.get("/api/runs/run-test-4/events?type=tool.started")
        assert resp.status_code == 200
        events = resp.json()
        assert len(events) == 1
        assert events[0]["type"] == "tool.started"

        # Filter by actor
        resp = client.get("/api/runs/run-test-4/events?actor=proxy")
        assert resp.status_code == 200
        events = resp.json()
        assert len(events) == 1
        assert events[0]["actor"] == "proxy"

    def test_list_events_pagination(self, test_client) -> None:
        client = test_client
        with client.app.state.session_factory() as session:
            run = Run(
                id="run-test-5",
                agent_name="agent",
                goal="test",
                status="running",
                metadata={},
                explanation_cache={},
                flag_cache=[],
            )
            session.add(run)
            session.commit()

            for i in range(5):
                record_event(session, run, event_type=f"event.{i}", actor="sdk", summary=f"Event {i}")
            session.commit()

        resp = client.get("/api/runs/run-test-5/events?limit=2&offset=0")
        assert resp.status_code == 200
        events = resp.json()
        assert len(events) == 2

        resp = client.get("/api/runs/run-test-5/events?limit=2&offset=2")
        assert resp.status_code == 200
        events = resp.json()
        assert len(events) == 2
        assert events[0]["summary"] == "Event 2"
