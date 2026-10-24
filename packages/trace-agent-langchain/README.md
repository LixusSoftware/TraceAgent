# TraceAgent LangChain Integration

![GitHub Release](https://img.shields.io/github/v/release/LixusSoftware/TraceAgent)
![GitHub Stars](https://img.shields.io/github/stars/LixusSoftware/TraceAgent)
![GitHub License](https://img.shields.io/github/license/LixusSoftware/TraceAgent)
![Tests](https://github.com/LixusSoftware/TraceAgent/actions/workflows/test.yml/badge.svg)
[![Website](https://img.shields.io/badge/website-traceagent.vercel.app-blue)](https://traceagent.vercel.app)

LangChain callback handler that streams execution events into TraceAgent.

## Install

```bash
pip install trace-agent-langchain
```

## Usage

```python
from trace_agent_sdk import TraceAgentClient
from trace_agent_langchain import TraceAgentLangChainCallback

client = TraceAgentClient("http://localhost:8000")
run = client.start_run("my-agent", "Do something")

# Attach the callback to any LangChain chain
callback = run.as_langchain_callback()
chain.invoke({"input": "hello"}, config={"callbacks": [callback]})
```

## License

MIT
