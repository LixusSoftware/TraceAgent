"""TraceAgent UI static file server.

Serves the built React SPA from package data and proxies /api/* requests
to the TraceAgent backend server.
"""

from __future__ import annotations

import os
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from starlette.background import BackgroundTask

# Headers that describe one connection, not the message: they must not be copied across the proxy.
_HOP_BY_HOP = {
    "host",
    "content-length",
    "connection",
    "keep-alive",
    "transfer-encoding",
    "upgrade",
    "te",
    "trailers",
    "proxy-authenticate",
    "proxy-authorization",
}


def create_app(
    static_dir: str | None = None,
    api_base_url: str | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> FastAPI:
    app = FastAPI(title="TraceAgent UI")

    if static_dir is None:
        import importlib.resources as pkg_resources

        static_dir = str(pkg_resources.files("trace_agent_ui") / "static")
    static_root = Path(static_dir).resolve()

    api_base = (api_base_url or os.getenv("TRACE_AGENT_SERVER_URL", "http://127.0.0.1:8000")).rstrip("/")

    # The API proxy has to be registered before the catch-all below: routes match in order, so
    # anything registered earlier (or a static mount at "/") would answer /api/* with a 404.
    @app.api_route(
        "/api/{path:path}",
        methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
        response_model=None,
    )
    async def proxy_to_backend(request: Request, path: str) -> StreamingResponse | JSONResponse:
        """Proxy API requests to the TraceAgent backend server, streaming the response (SSE included)."""
        headers = {k: v for k, v in request.headers.items() if k.lower() not in _HOP_BY_HOP}
        # No read timeout: the live event stream stays open as long as the run does.
        client = httpx.AsyncClient(transport=transport, timeout=httpx.Timeout(30.0, read=None))
        upstream_request = client.build_request(
            request.method,
            f"{api_base}/api/{path}",
            headers=headers,
            params=request.query_params,
            content=await request.body(),
        )
        try:
            upstream = await client.send(upstream_request, stream=True)
        except httpx.RequestError as exc:
            await client.aclose()
            return JSONResponse(
                {"detail": f"The TraceAgent server at {api_base} is not reachable ({type(exc).__name__})."},
                status_code=502,
            )

        async def close() -> None:
            await upstream.aclose()
            await client.aclose()

        return StreamingResponse(
            upstream.aiter_raw(),
            status_code=upstream.status_code,
            headers={k: v for k, v in upstream.headers.items() if k.lower() not in _HOP_BY_HOP},
            background=BackgroundTask(close),
        )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str) -> FileResponse:
        """Serve a built asset if it exists, and index.html for any other path (SPA fallback)."""
        candidate = (static_root / full_path).resolve()
        if full_path and candidate.is_file() and static_root in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(static_root / "index.html")

    return app


def main() -> None:
    import uvicorn

    port = int(os.getenv("TRACE_AGENT_UI_PORT", "8080"))
    host = os.getenv("TRACE_AGENT_UI_HOST", "0.0.0.0")
    app = create_app()
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
