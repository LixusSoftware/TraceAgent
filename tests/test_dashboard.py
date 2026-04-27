from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from visor_agentico.config import Settings
from visor_agentico.main import create_app
from visor_agentico.models import Event, Run, Turn
from visor_agentico.services.dashboard import build_dashboard


@pytest.fixture
def test_client(tmp_path) -> TestClient:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        cors_origins=["http://localhost:5173"],
    )
    app = create_app(settings)
    return TestClient(app)


class TestDashboardApi:
    def test_dashboard_stats_empty(self, test_client) -> None:
        client = test_client
        resp = client.get("/api/dashboard?period=24h")
        assert resp.status_code == 200
        data = resp.json()
        assert data["stats"]["total_runs"] == 0
        assert data["stats"]["total_errors"] == 0
        assert len(data["trend"]) == 7
        assert data["top_tools"] == []

    def test_dashboard_with_runs_and_events(self, test_client) -> None:
        client = test_client
        with client.app.state.session_factory() as session:
            # Create completed run
            run1 = Run(
                id="run-1",
                agent_name="agent-a",
                goal="Test 1",
                status="completed",
                metadata={},
                explanation_cache={},
                flag_cache=[],
                total_prompt_tokens=100,
                total_completion_tokens=50,
                started_at=datetime.now(timezone.utc) - timedelta(hours=1),
                ended_at=datetime.now(timezone.utc),
            )
            session.add(run1)
            session.flush()

            # Create turn
            turn1 = Turn(
                run_id="run-1",
                seq=1,
                provider="openai",
                model="gpt-4",
                messages=[],
                prompt_tokens=100,
                completion_tokens=50,
            )
            session.add(turn1)

            # Create events
            event1 = Event(
                run_id="run-1",
                seq=1,
                type="tool.started",
                actor="sdk",
                summary="Tool started",
                status="succeeded",
                tool_name="search",
                duration_ms=100,
            )
            event2 = Event(
                run_id="run-1",
                seq=2,
                type="tool.succeeded",
                actor="sdk",
                summary="Tool done",
                status="succeeded",
                tool_name="search",
                duration_ms=200,
            )
            session.add_all([event1, event2])
            session.commit()

        resp = client.get("/api/dashboard?period=24h")
        assert resp.status_code == 200
        data = resp.json()
        assert data["stats"]["total_runs"] == 1
        assert data["stats"]["completed_runs"] == 1
        assert data["stats"]["total_errors"] == 0
        assert data["stats"]["total_prompt_tokens"] == 100
        assert data["stats"]["total_completion_tokens"] == 50
        assert len(data["top_tools"]) == 1
        assert data["top_tools"][0]["tool_name"] == "search"
        assert data["top_tools"][0]["call_count"] == 1

    def test_dashboard_periods(self, test_client) -> None:
        client = test_client
        with client.app.state.session_factory() as session:
            # Old run (8 days ago)
            old_run = Run(
                id="run-old",
                agent_name="agent-a",
                goal="Old",
                status="completed",
                metadata={},
                explanation_cache={},
                flag_cache=[],
                started_at=datetime.now(timezone.utc) - timedelta(days=8),
                ended_at=datetime.now(timezone.utc) - timedelta(days=8),
            )
            # Recent run
            recent_run = Run(
                id="run-recent",
                agent_name="agent-a",
                goal="Recent",
                status="completed",
                metadata={},
                explanation_cache={},
                flag_cache=[],
                started_at=datetime.now(timezone.utc) - timedelta(hours=1),
                ended_at=datetime.now(timezone.utc),
            )
            session.add_all([old_run, recent_run])
            session.commit()

        # 24h period should only see recent
        resp = client.get("/api/dashboard?period=24h")
        data = resp.json()
        assert data["stats"]["total_runs"] == 1

        # 30d period should see both
        resp = client.get("/api/dashboard?period=30d")
        data = resp.json()
        assert data["stats"]["total_runs"] == 2

    def test_dashboard_top_errors(self, test_client) -> None:
        client = test_client
        with client.app.state.session_factory() as session:
            run = Run(
                id="run-err",
                agent_name="agent-a",
                goal="Test errors",
                status="failed",
                metadata={},
                explanation_cache={},
                flag_cache=[],
                started_at=datetime.now(timezone.utc) - timedelta(hours=1),
                ended_at=datetime.now(timezone.utc),
            )
            session.add(run)
            session.flush()

            event = Event(
                run_id="run-err",
                seq=1,
                type="tool.failed",
                actor="sdk",
                summary="Tool failed",
                status="failed",
                error_code="ToolError",
            )
            session.add(event)
            session.commit()

        resp = client.get("/api/dashboard?period=24h")
        data = resp.json()
        assert len(data["top_errors"]) == 1
        assert data["top_errors"][0]["error_code"] == "ToolError"
