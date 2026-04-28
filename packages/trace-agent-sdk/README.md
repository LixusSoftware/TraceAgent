# TraceAgent SDK

Python SDK for instrumenting AI agents and streaming events to a TraceAgent backend.

## Install

```bash
pip install trace-agent-sdk
```

## Usage

```python
from trace_agent_sdk import TraceAgentClient

client = TraceAgentClient("http://localhost:8000")
run = client.start_run("my-agent", "Do something")


@run.tool()
def search(query: str) -> str:
    return f"Results for {query}"


result = run.create_model_turn(
    messages=[{"role": "user", "content": "Search for Python"}],
    model="gpt-4",
)

run.finish()
```

## File and command wrappers

```python
# Record a command execution
run.commands.run(["python", "-m", "pytest"], cwd="./my-project")

# Record file operations
run.files.read_text("config.yaml")
run.files.write_text("output.txt", "hello world")
run.files.patch_text("app.py", "print('fixed')\n")
```

## License

MIT
