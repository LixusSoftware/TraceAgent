# TraceAgent Pydantic AI Integration

![GitHub Release](https://img.shields.io/github/v/release/LixusSoftware/TraceAgent)
![GitHub Stars](https://img.shields.io/github/stars/LixusSoftware/TraceAgent)
![GitHub License](https://img.shields.io/github/license/LixusSoftware/TraceAgent)
![Tests](https://github.com/LixusSoftware/TraceAgent/actions/workflows/test.yml/badge.svg)
[![Website](https://img.shields.io/badge/website-traceagent.vercel.app-blue)](https://traceagent.vercel.app)

Pydantic AI capability that streams agent runs, model requests and tool calls into TraceAgent.
Requires Pydantic AI 2.x.

## Install

```bash
pip install trace-agent-pydantic-ai
```

## Usage

```python
from pydantic_ai import Agent
from trace_agent_sdk import TraceAgentClient

client = TraceAgentClient("http://localhost:8000")
run = client.start_run("my-agent", "Do something")

agent = Agent("openai:gpt-4o", capabilities=[run.as_pydantic_ai_capability()])
result = agent.run_sync("hello")

run.finish(result.output)
```

The capability never breaks or slows the agent. Events are delivered by a background thread; if the backend is unreachable or hangs, a one-line warning is printed, trace delivery pauses for a while, and the agent keeps running. Events produced while paused are dropped. The end of the outermost run waits a few seconds at most for pending events, so `run.finish()` is delivered after them.

Pydantic AI prints a startup banner suggesting Logfire while its own observability is off. It is unrelated to TraceAgent and can be silenced with `PYDANTIC_AI_NO_BANNER=1`.

## Options

`run.as_pydantic_ai_capability(...)` accepts:

| Option | Default | Description |
|---|---|---|
| `record_model_events` | `True` | Record each model request as an LLM call (tokens, model, requested tools) |
| `record_tool_events` | `True` | Record each tool execution (args, output summary, duration, errors) |
| `record_node_events` | `False` | Record every agent graph node |
| `redact_fields` | `[]` | Argument / output keys replaced with `[redacted]` |
| `failure_cooldown` | `30.0` | Seconds to stop sending (and drop events) after a failed delivery. `0` retries every event |
| `flush_timeout` | `5.0` | Maximum seconds the end of the outermost run waits for pending events |

## License

MIT
