# TraceAgent UI

Static file server for the TraceAgent React frontend. Serves the built SPA and proxies `/api/*` to the backend.

## Install

```bash
pip install trace-agent-ui
```

## Run

```bash
TRACE_AGENT_SERVER_URL=http://localhost:8000 trace-agent-ui
```

The UI will be available at `http://localhost:8080` and will proxy API requests to the backend.

## Docker

```bash
docker run \
  -p 8080:8080 \
  -e TRACE_AGENT_SERVER_URL=http://host.docker.internal:8000 \
  ghcr.io/lixussoftware/trace-agent-ui
```

## License

MIT
