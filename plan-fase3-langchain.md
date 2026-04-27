# Fase 3: LangChain Integration — Plan

## Goal
Enable LangChain-based agents to emit observability events into `visor-agentico` via a standard `BaseCallbackHandler`. The backend continues to record, aggregate, and visualize events without schema changes.

## Architecture Decision: Callback-First (Client-Side)

LangChain owns the agent loop, tool execution, and message management. The Visor SDK switches from **active orchestration** (`create_model_turn`) to **passive observation** via callbacks.

```
User Script
    │
    ├───> VisorClient.start_run() ──> RunSession
    │
    ├───> VisorLangChainCallback(run_session)
    │
    └───> LangChain Agent.run(..., callbacks=[callback])
              │
              ├─── on_llm_start/end ──> POST /turns (optional) + events
              ├─── on_tool_start/end ──> POST /tool-results + events
              ├─── on_chain_start/end ──> POST /observations
              └─── on_retriever_start/end ──> POST /observations
```

## 3.1 Dependencies

**`pyproject.toml`**
```toml
[project.optional-dependencies]
providers = ["anthropic>=0.42.0", "google-generativeai>=0.8.0"]
langchain = ["langchain-core>=0.3.0", "langchain>=0.3.0", "langchain-openai>=0.2.0"]
```

Install: `uv pip install -e ".[langchain]"`

## 3.2 Backend Changes (Minimal)

No schema changes required — the `Event.type` column is free-form text.

**File: `visor_agentico/services/analytics.py`**
- Extend ` ExecutionMetadata` counters to include:
  - `chain_step_count`
  - `retriever_count`
  - `llm_call_count`
- Extend `TimelineGroup` logic to recognize new event types for coloring/grouping.

**File: `visor_agentico/services/graph.py`**
- Extend node-type detection to recognize `chain`, `llm`, `retriever` events.

**File: `visor_agentico/api/runs.py`**
- No new endpoints required. Re-use existing:
  - `POST /api/runs/{run_id}/turns` — for LLM calls (optional Turn recording)
  - `POST /api/runs/{run_id}/tool-results` — for tool results
  - `POST /api/runs/{run_id}/observations` — for chain/retriever events
- However, add a **bulk event endpoint** for efficiency:
  - `POST /api/runs/{run_id}/events/bulk` — accepts a list of `EventCreate`-like objects and persists them in a single transaction. This reduces HTTP overhead from N callback events.

## 3.3 Callback Handler (`visor_agentico/langchain_callback.py`)

### Class: `VisorLangChainCallback(BaseCallbackHandler)`

```python
class VisorLangChainCallback(BaseCallbackHandler):
    def __init__(
        self,
        run_session: RunSession,
        *,
        record_turns: bool = True,      # Create Turn rows for each LLM call
        record_chain_events: bool = True,
        record_retriever_events: bool = True,
    ) -> None:
        self.run_session = run_session
        self.record_turns = record_turns
        self.record_chain_events = record_chain_events
        self.record_retriever_events = record_retriever_events
        self._step_map: dict[str, str] = {}   # langchain run_id -> visor step_id
        self._pending_llm: dict[str, dict] = {}  # run_id -> {prompts, start_time, messages}
```

### Event Mapping

| LangChain Callback | Visor Event Type | Actor | Endpoint | Notes |
|---|---|---|---|---|
| `on_chain_start` | `chain.started` | `sdk` | `/observations` | summary = chain type |
| `on_chain_end` | `chain.completed` | `sdk` | `/observations` | duration from start |
| `on_chain_error` | `chain.failed` | `sdk` | `/observations` | error_code, error_summary |
| `on_llm_start` | `model.requested` | `sdk` | internal buffer | store prompts, start_time, messages |
| `on_llm_end` | `model.responded` | `provider` | `/turns` (if record_turns) + `/observations` | extract token usage from `LLMResult.llm_output`, create Turn row |
| `on_llm_error` | `model.failed` | `provider` | `/observations` | error_code from exception |
| `on_tool_start` | `tool.started` | `sdk` | `/observations` | summary = tool name + args |
| `on_tool_end` | `tool.succeeded` | `sdk` | `/tool-results` | POST result, includes output |
| `on_tool_error` | `tool.failed` | `sdk` | `/tool-results` + `/observations` | error_code, error_summary |
| `on_retriever_start` | `retriever.queried` | `sdk` | `/observations` | summary = query |
| `on_retriever_end` | `retriever.responded` | `sdk` | `/observations` | summary = doc count |
| `on_prompt_start` | `prompt.rendered` | `sdk` | `/observations` | (optional, v2) |
| `on_agent_action` | `agent.action` | `sdk` | `/observations` | action type + tool |
| `on_agent_finish` | `agent.finish` | `sdk` | `/observations` | final output |

### Step ID Mapping

LangChain's `run_id` (UUID) → Visor `step_id` (string)
LangChain's `parent_run_id` → Visor `parent_step_id`

This produces a hierarchical tree in the Visor timeline matching LangChain's execution tree.

### Turn Recording from Callbacks

When `record_turns=True`:

1. `on_llm_start`: Buffer the `messages` (extracted from `prompts` or from kwargs if available). LangChain `on_llm_start` receives `prompts: list[str]`, not structured messages. We need to reconstruct or pass messages via a wrapper.

   **Problem:** `on_llm_start` in LangChain gets raw prompts (strings), not the structured `messages` array that the `/turns` endpoint expects.

   **Solution:** Instead of using raw LangChain callbacks, provide a **wrapper** around `ChatOpenAI` (or any ChatModel) that captures the structured messages before they are converted to prompts.

   **Alternative:** Accept that Turn rows for LangChain will have `messages = []` or reconstructed from prompts, and rely on `Event` rows for full observability. This is acceptable for v1.

   **Decision for v1:** Do NOT create Turn rows from callbacks. Instead, record LLM calls as `Event` rows only. Turn rows remain a backend-managed concept for the proxy mode. Future iterations can add a `LangChainChatModelWrapper` that intercepts `.invoke()` calls.

### Re-Evaluating the Approach

Given the complexity of reconstructing messages from LangChain callbacks, the v1 callback handler will:

1. Record all LangChain execution as `Event` rows via `/observations` (with new `kind` values)
2. Record tool results via `/tool-results`
3. NOT create `Turn` rows (avoids message reconstruction problems)
4. Provide clear `step_id` hierarchy

This gives full observability without fighting LangChain's internals.

### Revised Event Mapping (v1)

All events go through `POST /api/runs/{run_id}/observations` with an extended `kind` enum:

```python
class ObservationKind(str, Enum):
    command = "command"
    file_read = "file_read"
    file_write = "file_write"
    patch = "patch"
    artifact = "artifact"
    # NEW for LangChain
    chain_step = "chain_step"
    llm_call = "llm_call"
    tool_call = "tool_call"
    retriever_query = "retriever_query"
    agent_action = "agent_action"
```

The backend endpoint `POST /observations` maps these new `kind` values to event types:
- `chain_step` → `chain.started` / `chain.completed` / `chain.failed`
- `llm_call` → `llm.started` / `llm.completed` / `llm.failed`
- `tool_call` → `tool.started` / `tool.succeeded` / `tool.failed`
- `retriever_query` → `retriever.queried` / `retriever.responded`
- `agent_action` → `agent.action` / `agent.finish`

## 3.4 SDK Changes (`visor_agentico/sdk.py`)

Add method to `RunSession`:

```python
def as_langchain_callback(
    self,
    *,
    record_chain_events: bool = True,
    record_retriever_events: bool = True,
) -> VisorLangChainCallback:
    """Return a LangChain callback handler bound to this run."""
    return VisorLangChainCallback(
        self,
        record_chain_events=record_chain_events,
        record_retriever_events=record_retriever_events,
    )
```

## 3.5 New File: `visor_agentico/langchain_callback.py`

Full implementation of `VisorLangChainCallback` with:
- `BaseCallbackHandler` subclass
- HTTP client reuse (share `RunSession`'s `httpx.Client`)
- Token usage extraction from `LLMResult.llm_output`
- Error handling (don't crash the agent if Visor is unavailable)
- Async support (LangChain supports async callbacks)

## 3.6 New File: `examples/langchain_agent.py`

```python
from langchain import hub
from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain_openai import ChatOpenAI
from visor_agentico.sdk import VisorClient

client = VisorClient(base_url="http://127.0.0.1:8000")
run = client.start_run(agent_name="langchain-weather-agent", goal="Get weather info")

llm = ChatOpenAI(model="gpt-4o")
prompt = hub.pull("hwchase17/openai-tools-agent")
tools = [...]
agent = create_openai_tools_agent(llm, tools, prompt)
executor = AgentExecutor(agent=agent, tools=tools)

# Attach the Visor callback
callback = run.as_langchain_callback()
result = executor.invoke({"input": "What's the weather in Madrid?"}, callbacks=[callback])

run.finish(result["output"])
```

## 3.7 Tests

### Backend Tests
- `tests/test_langchain_callback.py` (mocked, no langchain import needed)
  - Test event mapping logic
  - Test step_id hierarchy construction
  - Test token usage extraction from mock LLMResult
  - Test error resilience (Visor unavailable)

### Integration Tests
- `tests/test_langchain_integration.py` (requires `langchain` installed)
  - Test with a simple `LLMChain`
  - Test with `AgentExecutor` + tools
  - Verify events are persisted in DB
  - Verify SSE notifications fire

### Frontend Tests
- No frontend changes needed for v1 (backend event types are strings, frontend already displays them)
- Optional: add color mapping for new event types in timeline

## 3.8 Implementation Order

1. **Extend `ObservationInput` schema** — add new `kind` values (`visor_agentico/schemas.py`)
2. **Extend `/observations` endpoint** — map new kinds to event types (`visor_agentico/api/runs.py`)
3. **Create `VisorLangChainCallback`** — (`visor_agentico/langchain_callback.py`)
4. **Add `as_langchain_callback()` to `RunSession`** — (`visor_agentico/sdk.py`)
5. **Add example script** — (`examples/langchain_agent.py`)
6. **Add tests** — (`tests/test_langchain_callback.py`, `tests/test_langchain_integration.py`)
7. **Update dependencies** — (`pyproject.toml`)
8. **Verify** — run example against backend

## 3.9 Risks & Mitigations

| Risk | Mitigation |
|---|---|
| `langchain-core` API changes between versions | Pin to `>=0.3.0,<0.4.0` in dependencies |
| Token usage not available in all LangChain providers | Gracefully handle missing `llm_output`; skip usage fields |
| Async callback confusion (sync vs async handlers) | Implement both `on_*` and `on_*_async` methods |
| Message reconstruction for Turn rows | Defer to v2; use Events-only for v1 |
| Circular import between sdk.py and langchain_callback.py | Keep `langchain_callback.py` independent; only import in `RunSession.as_langchain_callback()` |

## 3.10 Success Criteria

- [ ] `VisorLangChainCallback` can be attached to any LangChain chain/agent
- [ ] All chain steps, LLM calls, tool calls, and retriever queries produce Visor events
- [ ] Events have correct `step_id` / `parent_step_id` hierarchy
- [ ] Tool results are persisted correctly
- [ ] Backend tests pass (>80% coverage maintained)
- [ ] Example script runs end-to-end
- [ ] No breaking changes to existing proxy-mode SDK
