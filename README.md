# TraceAgent

![GitHub Release](https://img.shields.io/github/v/release/LixusSoftware/TraceAgent)
![GitHub Stars](https://img.shields.io/github/stars/LixusSoftware/TraceAgent)
![GitHub License](https://img.shields.io/github/license/LixusSoftware/TraceAgent)
![Tests](https://github.com/LixusSoftware/TraceAgent/actions/workflows/test.yml/badge.svg)
![Docker Build](https://github.com/LixusSoftware/TraceAgent/actions/workflows/build-docker.yml/badge.svg)

> Observability and tracing for AI agents with tools.

TraceAgent is a full-stack observability platform for tool-using AI agents. It provides:

- **SDK** to instrument your agents and record tool calls, commands, file operations, and artifacts.
- **Server** (FastAPI) to persist runs, generate timelines, execution graphs, and explanations.
- **LangChain integration** to stream LangChain events into TraceAgent.
- **UI** (React + static server) to inspect runs side-by-side with divergence detection.

---

## Quick start

### Backend

```bash
pip install trace-agent-server[providers]
trace-agent-server --reload
```

### UI

```bash
pip install trace-agent-ui
TRACE_AGENT_SERVER_URL=http://localhost:8000 trace-agent-ui
```

### SDK

```python
from trace_agent_sdk import TraceAgentClient

client = TraceAgentClient("http://localhost:8000")
run = client.start_run("my-agent", "Do something")

# Register tools, run model turns, record side effects...
run.finish()
```

### Docker (imágenes publicadas)

```bash
# Backend
docker run -p 8000:8000 ghcr.io/lixussoftware/trace-agent-server:latest

# UI (apunta al backend)
docker run -p 8080:8080 -e TRACE_AGENT_SERVER_URL=http://host.docker.internal:8000 ghcr.io/lixussoftware/trace-agent-ui:latest
```

### Docker Compose (desde el repo)

Clona el repo y levanta todo con build local:

```bash
git clone https://github.com/LixusSoftware/TraceAgent.git
cd TraceAgent
docker-compose up --build
```

---

## Packages

| Package | Install | Description |
|---------|---------|-------------|
| `trace-agent-sdk` | `pip install trace-agent-sdk` | Core SDK for instrumenting agents |
| `trace-agent-server` | `pip install trace-agent-server` | FastAPI backend and API |
| `trace-agent-langchain` | `pip install trace-agent-langchain` | LangChain callback handler |
| `trace-agent-ui` | `pip install trace-agent-ui` | Static file server for the React UI |

---

## Architecture

1. The agent uses `TraceAgentClient` and opens a `RunSession`.
2. Each model turn goes through the proxy at `POST /api/runs/{id}/turns`.
3. If the model requests tools, the SDK executes them locally and sends results back.
4. On run close, the backend generates timeline, execution graph, decision graph, and narrative with evidence.

---

## Development

Requires [uv](https://docs.astral.sh/uv/).

```bash
# Install the full workspace
uv sync --extra dev --extra providers --extra langchain

# Run backend tests
uv run --package trace-agent-server pytest packages/trace-agent-server/tests -v

# Run LangChain tests
uv run --package trace-agent-langchain pytest packages/trace-agent-langchain/tests -v
```

---

## License

MIT
