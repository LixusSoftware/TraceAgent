from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from trace_agent_server.config import Settings
from trace_agent_server.main import create_app
from trace_agent_server.models import Run
from trace_agent_server.services.events import (
    _get_sse_queues,
    _notify_sse_listeners,
    _register_sse_queue,
    _unregister_sse_queue,
)


@pytest.fixture
def test_client(tmp_path) -> TestClient:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        cors_origins=["http://localhost:5173"],
    )
    app = create_app(settings)
    return TestClient(app)


class TestSsePubSub:
    def test_register_and_unregister_queue(self) -> None:
        queue: asyncio.Queue = asyncio.Queue()
        _register_sse_queue("run-1", queue)
        assert len(_get_sse_queues("run-1")) == 1

        _unregister_sse_queue("run-1", queue)
        assert len(_get_sse_queues("run-1")) == 0

    def test_notify_delivers_to_registered_queues(self) -> None:
        queue: asyncio.Queue = asyncio.Queue()
        _register_sse_queue("run-2", queue)
        _notify_sse_listeners("run-2", {"type": "test", "data": "hello"})
        assert queue.qsize() == 1
        item = queue.get_nowait()
        assert item["type"] == "test"
        _unregister_sse_queue("run-2", queue)

    def test_notify_drops_when_queue_full(self) -> None:
        queue: asyncio.Queue = asyncio.Queue(maxsize=1)
        _register_sse_queue("run-3", queue)
        queue.put_nowait({"type": "existing"})
        # Queue is now full
        _notify_sse_listeners("run-3", {"type": "dropped"})
        assert queue.qsize() == 1
        _unregister_sse_queue("run-3", queue)

    def test_notify_ignores_unknown_run(self) -> None:
        # Should not raise
        _notify_sse_listeners("nonexistent", {"type": "test"})


class TestSseEndpoint:
    def test_stream_endpoint_exists(self, test_client) -> None:
        client = test_client
        app = client.app
        with app.state.session_factory() as session:
            run = Run(
                id="run-sse-1",
                agent_name="agent",
                goal="test sse",
                status="running",
                metadata={},
                explanation_cache={},
                flag_cache=[],
            )
            session.add(run)
            session.commit()

        # Verify endpoint is registered and returns correct content-type
        # We can't easily read the infinite stream in tests, so we verify the route exists
        # by checking app.routes
        from fastapi.routing import APIRoute
        route_paths = [r.path for r in app.routes if isinstance(r, APIRoute)]
        assert "/api/runs/{run_id}/events/stream" in route_paths
