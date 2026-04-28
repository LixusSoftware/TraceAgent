"""LangChain callback handler that streams execution events into TraceAgent.

Usage:
    from trace_agent_sdk import TraceAgentClient
    from trace_agent_langchain import TraceAgentLangChainCallback

    client = TraceAgentClient(base_url="http://127.0.0.1:8000")
    run = client.start_run(agent_name="my-agent", goal="Do something")

    callback = run.as_langchain_callback()
    chain.invoke({"input": "..."}, config={"callbacks": [callback]})
"""

from __future__ import annotations

import time
import traceback
from typing import Any

try:
    from langchain_core.callbacks import BaseCallbackHandler
    from langchain_core.outputs import ChatResult, LLMResult
except ImportError:  # pragma: no cover
    BaseCallbackHandler = None  # type: ignore[misc,assignment]
    LLMResult = None  # type: ignore[misc,assignment]
    ChatResult = None  # type: ignore[misc,assignment]


class TraceAgentLangChainCallback(BaseCallbackHandler):
    """Record LangChain execution as TraceAgent observations.

    The callback translates LangChain lifecycle events into HTTP POSTs to the
    TraceAgent backend.  If the backend is unreachable the callback logs a warning
    but **never** crashes the calling chain/agent.
    """

    def __init__(
        self,
        run_session: Any,
        *,
        record_chain_events: bool = True,
        record_retriever_events: bool = True,
    ) -> None:
        if BaseCallbackHandler is None:
            raise RuntimeError(
                "langchain-core is not installed. "
                "Install it with: uv pip install -e '.[langchain]'"
            )
        self.run_session = run_session
        self.record_chain_events = record_chain_events
        self.record_retriever_events = record_retriever_events
        # langchain run_id -> start timestamp (for duration calculation)
        self._starts: dict[str, float] = {}

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _post_observations(self, observations: list[dict[str, Any]]) -> None:
        """Send observations to the TraceAgent backend."""
        if not observations:
            return
        try:
            self.run_session.client._request(
                "POST",
                f"/api/runs/{self.run_session.run_id}/observations",
                {"observations": observations},
            )
        except Exception:
            # Silently ignore backend errors so the agent keeps running.
            traceback.print_exc()

    def _post_tool_results(self, results: list[dict[str, Any]]) -> None:
        """Send tool results to the TraceAgent backend."""
        if not results:
            return
        try:
            self.run_session.client._request(
                "POST",
                f"/api/runs/{self.run_session.run_id}/tool-results",
                {"results": results},
            )
        except Exception:
            traceback.print_exc()

    @staticmethod
    def _extract_token_usage(result: LLMResult | ChatResult | None) -> dict[str, Any]:
        """Try to extract token usage from an LLM / Chat result."""
        if result is None:
            return {}
        llm_output = getattr(result, "llm_output", None) or {}
        usage = llm_output.get("token_usage") or {}
        # OpenAI format
        if "prompt_tokens" in usage:
            return {
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                "total_tokens": usage.get("total_tokens"),
            }
        # Anthropic format
        if "input_tokens" in usage:
            return {
                "prompt_tokens": usage.get("input_tokens"),
                "completion_tokens": usage.get("output_tokens"),
                "total_tokens": (
                    (usage.get("input_tokens") or 0)
                    + (usage.get("output_tokens") or 0)
                ),
            }
        return dict(usage)

    # ── Chain lifecycle ─────────────────────────────────────────────────────

    def on_chain_start(
        self,
        serialized: dict[str, Any] | None,
        inputs: dict[str, Any],
        *,
        run_id: str,
        parent_run_id: str | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        if not self.record_chain_events:
            return
        self._starts[run_id] = time.time()
        chain_type = (serialized or {}).get("name", "unknown")
        inputs_keys = list(inputs.keys()) if isinstance(inputs, dict) else []
        self._post_observations(
            [
                {
                    "kind": "chain_step",
                    "step_id": str(run_id),
                    "parent_step_id": str(parent_run_id) if parent_run_id else None,
                    "status": "running",
                    "input_summary": f"Chain '{chain_type}' started",
                    "metadata": {
                        "chain_type": chain_type,
                        "inputs_keys": inputs_keys,
                        "tags": tags,
                        **(metadata or {}),
                    },
                }
            ]
        )

    def on_chain_end(
        self,
        outputs: dict[str, Any],
        *,
        run_id: str,
        parent_run_id: str | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        if not self.record_chain_events:
            return
        duration_ms = int((time.time() - self._starts.pop(run_id, time.time())) * 1000)
        output_keys = list(outputs.keys()) if isinstance(outputs, dict) else []
        self._post_observations(
            [
                {
                    "kind": "chain_step",
                    "step_id": str(run_id),
                    "parent_step_id": str(parent_run_id) if parent_run_id else None,
                    "status": "succeeded",
                    "duration_ms": duration_ms,
                    "input_summary": f"Chain completed",
                    "metadata": {
                        "output_keys": output_keys,
                        "tags": tags,
                        **(metadata or {}),
                    },
                }
            ]
        )

    def on_chain_error(
        self,
        error: BaseException,
        *,
        run_id: str,
        parent_run_id: str | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        if not self.record_chain_events:
            return
        duration_ms = int((time.time() - self._starts.pop(run_id, time.time())) * 1000)
        self._post_observations(
            [
                {
                    "kind": "chain_step",
                    "step_id": str(run_id),
                    "parent_step_id": str(parent_run_id) if parent_run_id else None,
                    "status": "failed",
                    "duration_ms": duration_ms,
                    "error_code": error.__class__.__name__,
                    "error_summary": str(error),
                    "metadata": {"tags": tags, **(metadata or {})},
                }
            ]
        )

    # ── LLM / Chat model lifecycle ──────────────────────────────────────────

    def _on_llm_start(
        self,
        *,
        run_id: str,
        parent_run_id: str | None,
        provider: str | None,
        model: str | None,
        metadata: dict[str, Any] | None,
    ) -> None:
        self._starts[run_id] = time.time()
        self._post_observations(
            [
                {
                    "kind": "llm_call",
                    "step_id": str(run_id),
                    "parent_step_id": str(parent_run_id) if parent_run_id else None,
                    "status": "running",
                    "provider": provider,
                    "model": model,
                    "metadata": metadata or {},
                }
            ]
        )

    def _on_llm_end(
        self,
        result: LLMResult | ChatResult | None,
        *,
        run_id: str,
        parent_run_id: str | None,
        provider: str | None,
        model: str | None,
        metadata: dict[str, Any] | None,
    ) -> None:
        duration_ms = int((time.time() - self._starts.pop(run_id, time.time())) * 1000)
        usage = self._extract_token_usage(result)
        self._post_observations(
            [
                {
                    "kind": "llm_call",
                    "step_id": str(run_id),
                    "parent_step_id": str(parent_run_id) if parent_run_id else None,
                    "status": "succeeded",
                    "duration_ms": duration_ms,
                    "provider": provider,
                    "model": model,
                    "metadata": {**usage, **(metadata or {})},
                }
            ]
        )

    def _on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: str,
        parent_run_id: str | None,
        provider: str | None,
        model: str | None,
        metadata: dict[str, Any] | None,
    ) -> None:
        duration_ms = int((time.time() - self._starts.pop(run_id, time.time())) * 1000)
        self._post_observations(
            [
                {
                    "kind": "llm_call",
                    "step_id": str(run_id),
                    "parent_step_id": str(parent_run_id) if parent_run_id else None,
                    "status": "failed",
                    "duration_ms": duration_ms,
                    "provider": provider,
                    "model": model,
                    "error_code": error.__class__.__name__,
                    "error_summary": str(error),
                    "metadata": metadata or {},
                }
            ]
        )

    def on_llm_start(
        self,
        serialized: dict[str, Any] | None,
        prompts: list[str],
        *,
        run_id: str,
        parent_run_id: str | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        provider = (serialized or {}).get("name", "unknown")
        self._on_llm_start(
            run_id=run_id,
            parent_run_id=parent_run_id,
            provider=provider,
            model=None,
            metadata={"tags": tags, **(metadata or {})},
        )

    def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: str,
        parent_run_id: str | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        provider = (metadata or {}).get("name", "unknown")
        self._on_llm_end(
            response,
            run_id=run_id,
            parent_run_id=parent_run_id,
            provider=provider,
            model=None,
            metadata={"tags": tags, **(metadata or {})},
        )

    def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: str,
        parent_run_id: str | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        provider = (metadata or {}).get("name", "unknown")
        self._on_llm_error(
            error,
            run_id=run_id,
            parent_run_id=parent_run_id,
            provider=provider,
            model=None,
            metadata={"tags": tags, **(metadata or {})},
        )

    def on_chat_model_start(
        self,
        serialized: dict[str, Any] | None,
        messages: list[list[Any]],
        *,
        run_id: str,
        parent_run_id: str | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        provider = (serialized or {}).get("name", "unknown")
        model = (kwargs.get("invocation_params") or {}).get("model")
        self._on_llm_start(
            run_id=run_id,
            parent_run_id=parent_run_id,
            provider=provider,
            model=model,
            metadata={"tags": tags, **(metadata or {})},
        )

    def on_chat_model_end(
        self,
        response: ChatResult,
        *,
        run_id: str,
        parent_run_id: str | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        provider = (metadata or {}).get("name", "unknown")
        model = (kwargs.get("invocation_params") or {}).get("model")
        self._on_llm_end(
            response,
            run_id=run_id,
            parent_run_id=parent_run_id,
            provider=provider,
            model=model,
            metadata={"tags": tags, **(metadata or {})},
        )

    # ── Tool lifecycle ──────────────────────────────────────────────────────

    def on_tool_start(
        self,
        serialized: dict[str, Any] | None,
        input_str: str,
        *,
        run_id: str,
        parent_run_id: str | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        self._starts[run_id] = time.time()
        tool_name = (serialized or {}).get("name", "unknown")
        self._post_observations(
            [
                {
                    "kind": "tool_call",
                    "step_id": str(run_id),
                    "parent_step_id": str(parent_run_id) if parent_run_id else None,
                    "status": "running",
                    "tool_name": tool_name,
                    "input_summary": f"Tool '{tool_name}' started",
                    "metadata": {
                        "input": input_str,
                        "tags": tags,
                        **(metadata or {}),
                    },
                }
            ]
        )

    def on_tool_end(
        self,
        output: Any,
        *,
        run_id: str,
        parent_run_id: str | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        duration_ms = int((time.time() - self._starts.pop(run_id, time.time())) * 1000)
        tool_name = (metadata or {}).get("name", "unknown")
        output_str = str(output) if output is not None else ""
        self._post_tool_results(
            [
                {
                    "call_id": run_id,
                    "name": tool_name,
                    "step_id": run_id,
                    "status": "succeeded",
                    "output_summary": output_str[:500],
                    "output_hash": None,
                    "duration_ms": duration_ms,
                }
            ]
        )
        self._post_observations(
            [
                {
                    "kind": "tool_call",
                    "step_id": str(run_id),
                    "parent_step_id": str(parent_run_id) if parent_run_id else None,
                    "status": "succeeded",
                    "tool_name": tool_name,
                    "duration_ms": duration_ms,
                    "input_summary": f"Tool '{tool_name}' succeeded",
                    "metadata": {"tags": tags, **(metadata or {})},
                }
            ]
        )

    def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: str,
        parent_run_id: str | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        duration_ms = int((time.time() - self._starts.pop(run_id, time.time())) * 1000)
        tool_name = (metadata or {}).get("name", "unknown")
        error_summary = str(error)
        self._post_tool_results(
            [
                {
                    "call_id": run_id,
                    "name": tool_name,
                    "step_id": run_id,
                    "status": "failed",
                    "output_summary": error_summary[:500],
                    "output_hash": None,
                    "error_code": error.__class__.__name__,
                    "error_summary": error_summary,
                    "duration_ms": duration_ms,
                }
            ]
        )
        self._post_observations(
            [
                {
                    "kind": "tool_call",
                    "step_id": str(run_id),
                    "parent_step_id": str(parent_run_id) if parent_run_id else None,
                    "status": "failed",
                    "tool_name": tool_name,
                    "duration_ms": duration_ms,
                    "error_code": error.__class__.__name__,
                    "error_summary": error_summary,
                    "metadata": {"tags": tags, **(metadata or {})},
                }
            ]
        )

    # ── Retriever lifecycle ─────────────────────────────────────────────────

    def on_retriever_start(
        self,
        serialized: dict[str, Any] | None,
        query: str,
        *,
        run_id: str,
        parent_run_id: str | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        if not self.record_retriever_events:
            return
        self._starts[run_id] = time.time()
        self._post_observations(
            [
                {
                    "kind": "retriever_query",
                    "step_id": str(run_id),
                    "parent_step_id": str(parent_run_id) if parent_run_id else None,
                    "status": "running",
                    "input_summary": f"Retriever query: {query[:200]}",
                    "metadata": {"query": query, "tags": tags, **(metadata or {})},
                }
            ]
        )

    def on_retriever_end(
        self,
        documents: list[Any],
        *,
        run_id: str,
        parent_run_id: str | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        if not self.record_retriever_events:
            return
        duration_ms = int((time.time() - self._starts.pop(run_id, time.time())) * 1000)
        self._post_observations(
            [
                {
                    "kind": "retriever_query",
                    "step_id": str(run_id),
                    "parent_step_id": str(parent_run_id) if parent_run_id else None,
                    "status": "succeeded",
                    "duration_ms": duration_ms,
                    "input_summary": f"Retriever returned {len(documents)} documents",
                    "metadata": {
                        "document_count": len(documents),
                        "tags": tags,
                        **(metadata or {}),
                    },
                }
            ]
        )

    def on_retriever_error(
        self,
        error: BaseException,
        *,
        run_id: str,
        parent_run_id: str | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        if not self.record_retriever_events:
            return
        duration_ms = int((time.time() - self._starts.pop(run_id, time.time())) * 1000)
        self._post_observations(
            [
                {
                    "kind": "retriever_query",
                    "step_id": str(run_id),
                    "parent_step_id": str(parent_run_id) if parent_run_id else None,
                    "status": "failed",
                    "duration_ms": duration_ms,
                    "error_code": error.__class__.__name__,
                    "error_summary": str(error),
                    "metadata": {"tags": tags, **(metadata or {})},
                }
            ]
        )

    # ── Agent lifecycle ─────────────────────────────────────────────────────

    def on_agent_action(
        self,
        action: Any,
        *,
        run_id: str,
        parent_run_id: str | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        tool = getattr(action, "tool", None) or "unknown"
        tool_input = getattr(action, "tool_input", None) or {}
        self._post_observations(
            [
                {
                    "kind": "agent_action",
                    "step_id": str(run_id),
                    "parent_step_id": str(parent_run_id) if parent_run_id else None,
                    "status": "running",
                    "tool_name": tool,
                    "input_summary": f"Agent action: {tool}",
                    "metadata": {
                        "tool": tool,
                        "tool_input": tool_input,
                        "tags": tags,
                        **(metadata or {}),
                    },
                }
            ]
        )

    def on_agent_finish(
        self,
        finish: Any,
        *,
        run_id: str,
        parent_run_id: str | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        output = getattr(finish, "return_values", {})
        self._post_observations(
            [
                {
                    "kind": "agent_action",
                    "step_id": str(run_id),
                    "parent_step_id": str(parent_run_id) if parent_run_id else None,
                    "status": "succeeded",
                    "input_summary": "Agent finished",
                    "metadata": {
                        "output_keys": list(output.keys()),
                        "tags": tags,
                        **(metadata or {}),
                    },
                }
            ]
        )
