"""TraceAgent UI static file server.

Serves the built React SPA from package data and optionally proxies
/api/* requests to the TraceAgent backend server.
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

import httpx


def create_app(static_dir: str | None = None, api_base_url: str | None = None) -> FastAPI:
    app = FastAPI(title="TraceAgent UI")

    if static_dir is None:
        import importlib.resources as pkg_resources

        static_dir = str(pkg_resources.files("trace_agent_ui") / "static")

    api_base = (api_base_url or os.getenv("TRACE_AGENT_SERVER_URL", "http://127.0.0.1:8000")).rstrip("/")

    # Mount static files
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

    @app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
    async def proxy_to_backend(request: Request, path: str) -> StreamingResponse:
        """Proxy API requests to the TraceAgent backend server."""
        url = f"{api_base}/api/{path}"
        method = request.method
        headers = {k: v for k, v in request.headers.items() if k.lower() not in ("host", "content-length")}
        body = await request.body()

        async with httpx.AsyncClient() as client:
            proxy_resp = await client.request(
                method=method,
                url=url,
                headers=headers,
                content=body,
                params=request.query_params,
                timeout=120.0,
            )

        return StreamingResponse(
            content=proxy_resp.aiter_raw(),
            status_code=proxy_resp.status_code,
            headers=dict(proxy_resp.headers),
            media_type=proxy_resp.headers.get("content-type"),
        )

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str) -> FileResponse:
        """Serve index.html for any non-API route (SPA fallback)."""
        if full_path.startswith("api/"):
            return FileResponse(os.path.join(static_dir, "index.html"), status_code=404)
        return FileResponse(os.path.join(static_dir, "index.html"))

    return app


def main() -> None:
    import uvicorn

    port = int(os.getenv("TRACE_AGENT_UI_PORT", "8080"))
    host = os.getenv("TRACE_AGENT_UI_HOST", "0.0.0.0")
    app = create_app()
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
