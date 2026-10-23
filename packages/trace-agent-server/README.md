# TraceAgent Server

![GitHub Release](https://img.shields.io/github/v/release/LixusSoftware/TraceAgent)
![GitHub Stars](https://img.shields.io/github/stars/LixusSoftware/TraceAgent)
![GitHub License](https://img.shields.io/github/license/LixusSoftware/TraceAgent)
![Tests](https://github.com/LixusSoftware/TraceAgent/actions/workflows/test.yml/badge.svg)
![Docker Build](https://github.com/LixusSoftware/TraceAgent/actions/workflows/build-docker.yml/badge.svg)
[![Website](https://img.shields.io/badge/website-traceagent.vercel.app-blue)](https://traceagent.vercel.app)

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

## Tracing agents through OpenTelemetry

The server is also an OTLP/HTTP receiver: an agent that already emits OpenTelemetry spans following the
[GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/) (Pydantic AI does) is
traced by pointing its exporter at `POST /v1/traces`, with nothing from TraceAgent installed in the agent.

```python
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from pydantic_ai import Agent
from pydantic_ai.capabilities import Instrumentation
from pydantic_ai.models.instrumented import InstrumentationSettings

provider = TracerProvider()
provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint="http://localhost:8000/v1/traces")))

agent = Agent("openai:gpt-4o", capabilities=[Instrumentation(settings=InstrumentationSettings(tracer_provider=provider))])
agent.run_sync("hello")
provider.shutdown()  # a short script must flush before exiting
```

- One run is created per trace (the trace id is the run id), named after `gen_ai.agent.name`. Add a `trace_agent.run_id`
  resource attribute to attach the spans to a run you created with the SDK instead.
- `invoke_agent` spans become chain steps, `chat` spans model calls and `execute_tool` spans tools. Event times and
  durations come from the spans; the run gets its provider, model, token totals and tool counters. Other spans are ignored.
- The run ends when its last agent span ends, also when the agent runs under a web server span or calls other agents.
- Prompts and outputs are summarized. Full payloads are stored only if `TRACE_AGENT_CAPTURE_FULL_PAYLOADS` is on.
- Protobuf and JSON bodies are accepted, gzip included. Use either this or the framework integrations for an agent, not
  both, or its run is recorded twice.

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `TRACE_AGENT_DATABASE_URL` | `sqlite:///./trace_agent.db` | Database URL (SQLite or PostgreSQL) |
| `TRACE_AGENT_OTLP_ENABLED` | `true` | Accept OpenTelemetry traces on `POST /v1/traces` |
| `TRACE_AGENT_OTLP_MAX_BODY_BYTES` | `10000000` | Largest accepted OTLP request, after decompression |
| `TRACE_AGENT_CAPTURE_FULL_PAYLOADS` | `true` | Keep full payloads, not only summaries |
| `TRACE_AGENT_OPENAI_API_KEY` | - | OpenAI API key |
| `TRACE_AGENT_OPENAI_BASE_URL` | - | OpenAI-compatible base URL (e.g. LM Studio) |
| `TRACE_AGENT_AUDIT_ENABLE_GUARDRAILS` | `false` | Enable prompt injection and PII checks |
| `TRACE_AGENT_AUDIT_METRICS_ENABLED` | `true` | Expose Prometheus `/metrics` endpoint |

## License

MIT
