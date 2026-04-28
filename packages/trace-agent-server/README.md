# TraceAgent Server

![GitHub Release](https://img.shields.io/github/v/release/LixusSoftware/TraceAgent)
![GitHub Stars](https://img.shields.io/github/stars/LixusSoftware/TraceAgent)
![GitHub License](https://img.shields.io/github/license/LixusSoftware/TraceAgent)
![Tests](https://github.com/LixusSoftware/TraceAgent/actions/workflows/test.yml/badge.svg)
![Docker Build](https://github.com/LixusSoftware/TraceAgent/actions/workflows/build-docker.yml/badge.svg)

FastAPI backend for TraceAgent. Stores runs, generates timelines, execution graphs, and explanations.

## Install

```bash
pip install trace-agent-server[providers]
```

## Run

```bash
# With the included CLI
trace-agent-server --host 0.0.0.0 --port 8000

# Or directly with uvicorn
uvicorn trace_agent_server.main:app --reload
```

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `TRACE_AGENT_DATABASE_URL` | `sqlite:///./trace_agent.db` | Database URL (SQLite or PostgreSQL) |
| `TRACE_AGENT_OPENAI_API_KEY` | - | OpenAI API key |
| `TRACE_AGENT_OPENAI_BASE_URL` | - | OpenAI-compatible base URL (e.g. LM Studio) |
| `TRACE_AGENT_AUDIT_ENABLE_GUARDRAILS` | `false` | Enable prompt injection and PII checks |
| `TRACE_AGENT_AUDIT_METRICS_ENABLED` | `true` | Expose Prometheus `/metrics` endpoint |

## License

MIT
