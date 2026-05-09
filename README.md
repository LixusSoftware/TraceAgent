# TraceAgent

> Observability and tracing platform for  AI agents.

TraceAgent gives you complete visibility into what your autonomous agents are actually doing - every tool call, file operation, terminal command, and decision path, recorded and visualized in real time.

Compatible with modern agent frameworks such as **LangChain**, TraceAgent integrates naturally into existing agent pipelines, letting you trace chains, tool executions, callbacks, memory interactions, and multi-step reasoning flows with minimal instrumentation.

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE) [![Python 3.9+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/) [![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](https://ghcr.io/lixussoftware)

---

## Table of Contents

- [Why TraceAgent?](#why-traceagent)
- [Features](#features)
- [Instrumenting Your Agent](#instrumenting-your-agent)
  - [SDK](#sdk)
  - [LangChain](#langchain)
  - [Configuration](#configuration-environment-variables)
- [Docker Images](#docker-images)
- [Examples](#examples)
- [Installation](#installation)
  - [Option 1 - From Source](#option-1--from-source)
- [Getting Help](#getting-help)
- [License](#license)

---

## Why TraceAgent?

Traditional observability tools were built for microservices - they don't understand what it means for an agent to "call a tool", "write a file", or "retry a failed command".

TraceAgent fills that gap with an **agent-first tracing specification** and a purpose-built audit UI, giving you full data ownership through a self-hosted setup. With first-class support for orchestration ecosystems like LangChain, TraceAgent captures and reconstructs complete execution across chains, agents, tools, prompts, and callbacks - enabling reproducibility, debugging, compliance auditing, and performance analysis for production-grade AI systems.

---

## Features

| Feature | Description |
|---|---|
| **Real-time tracing** | Capture tool calls, file operations, shell commands, and artifacts as they happen. |
| **Execution timeline** | Visualize agent behavior through interactive timelines and execution graphs. |
| **LangChain integration** | Native callback handler for LangChain agents and chains, with zero boilerplate. |
| **Self-hosted** | Full data ownership with a FastAPI backend and SQLite/PostgreSQL support. |

---

## Instrumenting Your Agent

TraceAgent is organized into four packages. Click any name to open its full README:

- [TraceAgent SDK](./packages/trace-agent-sdk/README.md)
- [TraceAgent LangChain Integration](./packages/trace-agent-langchain/README.md)
- [TraceAgent Server](./packages/trace-agent-server/README.md)
- [TraceAgent UI](./packages/trace-agent-ui/README.md)

---

### SDK

Wrap your agent's actions with the SDK to start recording. See the [full SDK README](./packages/trace-agent-sdk/README.md) for installation steps, basic usage, and the complete client reference.

```python
from trace_agent_sdk import TraceAgentClient

client = TraceAgentClient("http://localhost:8000")

# Start a tracked run
run = client.start_run("my-agent", "Perform a system task")

print("RUN:")
print(run)

# Record side-effects
file_result = run.record_file_write(
    "app.py",
    before_content="",
    after_content="print('Hello World')"
)

print("\nFILE RESULT:")
print(file_result)

command_result = run.record_command(
    ["python", "app.py"],
    exit_code=0
)

print("\nCOMMAND RESULT:")
print(command_result)

# Close the session
finish_result = run.finish({"status": "success"})

print("\nFINISH RESULT:")
print(finish_result)
```

---

### LangChain

Add the callback handler to any LangChain agent - all chain steps, LLM calls, and tool uses are captured automatically. See the [full LangChain README](./packages/trace-agent-langchain/README.md) for the list of captured events and configuration options.

```python
from trace_agent_langchain import TraceAgentLangChainCallback

agent.invoke({"input": "..."}, callbacks=[TraceAgentLangChainCallback(run)])
```

---

### Configuration

TraceAgent's behavior can be customized via environment variables. 

| Variable | Default | Description |
|----------|---------|-------------|
| `TRACE_AGENT_DATABASE_URL` | `sqlite:///./data/trace_agent.db` | Database(SQLite or PostgreSQL) connection URL used by the backend to persist trace data. . |
| `TRACE_AGENT_SERVER_URL` | `http://localhost:8000` | Backend URL used by the UI and SDK to communicate. |
| `TRACE_AGENT_AUDIT_METRICS_ENABLED` | `true` | Enables or disables audit metrics collection on the server. |
| `TRACE_AGENT_UI_PORT` | `8080` | Port where the frontend UI is exposed. |
| `OPENAI_BASE_URL` | *(none)* | Optional. Used in examples and LangChain to point to local LLMs like LM Studio. |

---

## Docker Images

Pre-built images are available for the backend and frontend:

| Component | Image |
|-----------|-------|
| [TraceAgent Server](./packages/trace-agent-server/README.md) | `ghcr.io/lixussoftware/trace-agent-server:latest` |
| [TraceAgent UI](./packages/trace-agent-ui/README.md) | `ghcr.io/lixussoftware/trace-agent-ui:latest` |

---

## Examples

Make sure the server is running at `http://127.0.0.1:8000` before running any example. Most scripts load configuration from a local `.env` file, so that is the easiest place to set the backend URL and model settings.

If you want to run the LangChain example, install the extra first:

```bash
uv sync --extra dev --extra providers --extra langchain
```

### `examples/sample_agent.py`

Minimal SDK smoke test. It starts a run, registers a mock `get_weather` tool, performs a single model turn, and closes the run with the assistant response.

```bash
uv run examples/sample_agent.py
```

Use this when you want to confirm that the SDK can create runs, record tool calls, and finish cleanly.

### `examples/langchain_agent.py`

LangChain integration example. It attaches `TraceAgentLangChainCallback` to a LangChain agent so chain steps, LLM calls, tool usage, and retriever activity are traced automatically.

```bash
uv run examples/langchain_agent.py
```

This example expects an OpenAI-compatible endpoint such as LM Studio and uses the following environment variables: `TRACE_AGENT_BASE_URL`, `OPENAI_BASE_URL`, and `OPENAI_API_KEY`.

### `examples/lm_studio_agent.py`

Local-model SDK example. It uses `TraceAgentClient` with LM Studio or any other OpenAI-compatible local model, registers a tool, and records a single traced turn.

```bash
uv run examples/lm_studio_agent.py
```

This is a good fit when you want to validate local model connectivity with `TRACE_AGENT_PROXY_URL`, `TRACE_AGENT_TEST_MODEL`, and `TRACE_AGENT_PROXY_TIMEOUT`.

### `examples/lm_studio_planner_agent.py`

Richer planning demo. It exposes multiple tools for weather, budget policy, venue selection, travel time, and venue cost estimation, then lets the model choose the minimum set of calls needed. It also supports several built-in scenarios through `--scenario` and an optional `--prompt` override.

```bash
uv run examples/lm_studio_planner_agent.py --scenario meetup_plan
```

Available scenarios:

| Scenario | Description |
|----------|-------------|
| `meetup_plan` | Plans a realistic team meetup in Madrid with weather, budget, venue, and travel constraints. |
| `weather_gate` | Checks whether an outdoor meetup is viable without doing extra venue or budget work. |
| `budget_only` | Verifies a selected venue against the budget and avoids unrelated tool calls. |
| `barcelona_shortlist` | Builds a short list of Barcelona venues while prioritizing logistics and reasonable travel from Sants. |

### `examples/coding_agent_debugger_demo.py`

Synthetic debugger and UI demo. It records command executions, file reads and writes, patches, and failure states without needing a live model, which makes it useful for testing divergence detection and trace visualization.

```bash
uv run examples/coding_agent_debugger_demo.py --scenario correct_edit
```

Available scenarios:

| Scenario | Description |
|----------|-------------|
| `correct_edit` | A successful agent run with the expected file edits. |
| `wrong_file` | The agent modifies the wrong file and fails to recover. |
| `retry_without_adaptation` | The agent retries the same failing action without changing strategy. |
| `same_tools_different_artifact` | The tool sequence stays the same, but the final artifact changes. |

### `examples/rich_demo_agent.py`

Full-fidelity trace demo. It combines a model turn, tool retries, shell commands, file reads and writes, patches, artifacts, and derived decisions in a single run.

```bash
uv run examples/rich_demo_agent.py
```

Use this example when you want the densest possible run for inspecting the dashboard, timeline, and artifact views.

---

## Installation

Each TraceAgent package can be installed independently via pip:
 
```bash
pip install trace-agent-sdk
pip install trace-agent-langchain
pip install trace-agent-server
pip install trace-agent-ui
```
 
Or install all packages at once:
 
```bash
pip install trace-agent-sdk trace-agent-langchain trace-agent-server trace-agent-ui
```

## Getting Help

- **Bug reports and feature requests** - [GitHub Issues](https://github.com/LixusSoftware/TraceAgent/issues)
- **Server-side debugging** - See the [Server README](./packages/trace-agent-server/README.md) for log locations and how to interpret them.
- **UI not connecting?** - Verify that `TRACE_AGENT_SERVER_URL` points to the correct backend host.

---

## License

MIT - see the [`LICENSE`](LICENSE) file for details.