from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.testclient import TestClient

from trace_agent_ui.app import create_app


def make_upstream() -> FastAPI:
    """A stand-in for the TraceAgent server."""
    upstream = FastAPI()

    @upstream.get("/api/runs")
    def list_runs(status: str | None = None) -> list[dict[str, str | None]]:
        return [{"id": "run-1", "status": status or "running"}]

    @upstream.post("/api/echo")
    async def echo(request: Request) -> dict[str, object]:
        return {"received": await request.json(), "content_type": request.headers.get("content-type")}

    @upstream.get("/api/runs/{run_id}/events/stream")
    def stream(run_id: str) -> StreamingResponse:
        def events():
            yield f"data: {json.dumps({'type': 'connected', 'run_id': run_id})}\n\n"
            yield f"data: {json.dumps({'type': 'tool.succeeded'})}\n\n"

        return StreamingResponse(events(), media_type="text/event-stream")

    @upstream.get("/api/runs/missing")
    def missing() -> JSONResponse:
        return JSONResponse({"detail": "Run not found."}, status_code=404)

    return upstream


@pytest.fixture
def static_dir(tmp_path: Path) -> Path:
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<html>trace-agent-ui</html>")
    (tmp_path / "assets" / "app.js").write_text("console.log('app')")
    (tmp_path.parent / "secret.txt").write_text("do not serve")
    return tmp_path


@pytest.fixture
def client(static_dir: Path) -> TestClient:
    app = create_app(
        static_dir=str(static_dir),
        api_base_url="http://server:8000",
        transport=httpx.ASGITransport(app=make_upstream()),
    )
    return TestClient(app)


class TestApiProxy:
    def test_forwards_get_requests_to_the_server(self, client: TestClient) -> None:
        response = client.get("/api/runs")

        assert response.status_code == 200
        assert response.json() == [{"id": "run-1", "status": "running"}]

    def test_forwards_query_parameters(self, client: TestClient) -> None:
        response = client.get("/api/runs", params={"status": "completed"})

        assert response.json() == [{"id": "run-1", "status": "completed"}]

    def test_forwards_post_bodies(self, client: TestClient) -> None:
        response = client.post("/api/echo", json={"goal": "Find the order"})

        assert response.status_code == 200
        assert response.json()["received"] == {"goal": "Find the order"}
        assert response.json()["content_type"] == "application/json"

    def test_passes_the_status_and_body_of_server_errors_through(self, client: TestClient) -> None:
        response = client.get("/api/runs/missing")

        assert response.status_code == 404
        assert response.json() == {"detail": "Run not found."}

    def test_streams_server_sent_events(self, client: TestClient) -> None:
        with client.stream("GET", "/api/runs/run-1/events/stream") as response:
            body = "".join(response.iter_text())

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        assert '"type": "connected"' in body
        assert '"type": "tool.succeeded"' in body

    def test_an_unknown_api_path_is_never_answered_with_the_page(self, client: TestClient) -> None:
        response = client.get("/api/nope")

        assert response.status_code == 404
        assert "trace-agent-ui" not in response.text

    def test_reports_an_unreachable_server_as_a_bad_gateway(self, static_dir: Path) -> None:
        def refuse(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused", request=request)

        app = create_app(
            static_dir=str(static_dir),
            api_base_url="http://server:8000",
            transport=httpx.MockTransport(refuse),
        )

        response = TestClient(app).get("/api/runs")

        assert response.status_code == 502
        assert "http://server:8000" in response.json()["detail"]
        assert "ConnectError" in response.json()["detail"]


class TestStaticFiles:
    def test_serves_the_page_at_the_root(self, client: TestClient) -> None:
        response = client.get("/")

        assert response.status_code == 200
        assert "trace-agent-ui" in response.text

    def test_serves_built_assets(self, client: TestClient) -> None:
        response = client.get("/assets/app.js")

        assert response.status_code == 200
        assert response.text == "console.log('app')"

    def test_falls_back_to_the_page_for_unknown_paths(self, client: TestClient) -> None:
        response = client.get("/runs/some-run")

        assert response.status_code == 200
        assert "trace-agent-ui" in response.text

    def test_does_not_serve_files_outside_the_static_directory(self, client: TestClient) -> None:
        response = client.get("/%2e%2e/secret.txt")

        assert "do not serve" not in response.text

    def test_health_endpoint(self, client: TestClient) -> None:
        assert client.get("/health").json() == {"status": "ok"}
