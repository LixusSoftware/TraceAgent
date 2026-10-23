"""Pydantic AI capability that streams execution events into TraceAgent.

Usage:
    from pydantic_ai import Agent
    from trace_agent_sdk import TraceAgentClient

    client = TraceAgentClient(base_url="http://127.0.0.1:8000")
    run = client.start_run(agent_name="my-agent", goal="Do something")

    agent = Agent("openai:gpt-4o", capabilities=[run.as_pydantic_ai_capability()])
    agent.run_sync("...")
    run.finish("done")
"""

from __future__ import annotations

import asyncio
import threading
import time
import traceback
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.exceptions import ApprovalRequired, CallDeferred
from trace_agent_sdk.redaction import redact_payload, stable_hash, summarize_value

# Step id of the innermost run/node being executed. ContextVars propagate down
# into model requests and tool tasks (also parallel ones) without sharing state.
_CURRENT_STEP: ContextVar[str | None] = ContextVar("trace_agent_pydantic_ai_step", default=None)


def _new_step_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:12]}"


def _elapsed_ms(started_at: float) -> int:
    return int((time.perf_counter() - started_at) * 1000)


def _usage_metadata(usage: Any) -> dict[str, Any]:
    """Translate a Pydantic AI usage object into TraceAgent token metadata."""
    if callable(usage):
        usage = usage()
    if usage is None:
        return {}
    prompt_tokens = getattr(usage, "input_tokens", None) or 0
    completion_tokens = getattr(usage, "output_tokens", None) or 0
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "requests": getattr(usage, "requests", None),
        "tool_calls": getattr(usage, "tool_calls", None),
    }


@dataclass
class TraceAgentCapability(AbstractCapability[Any]):
    """Record a Pydantic AI agent run as TraceAgent observations.

    The capability wraps the run, model request, tool execution and (optionally)
    graph node lifecycles.  If the backend is unreachable it logs a traceback
    but **never** crashes the agent.
    """

    run_session: Any = None
    record_model_events: bool = True
    record_tool_events: bool = True
    record_node_events: bool = False
    redact_fields: list[str] = field(default_factory=list)
    # The backend numbers events per run without locking, so concurrent posts
    # (e.g. parallel tools) would collide; sends are serialized instead.
    _send_lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False, compare=False)

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _post_sync(self, path: str, payload: dict[str, Any]) -> None:
        """Send a payload to the TraceAgent backend, swallowing any error."""
        try:
            with self._send_lock:
                self.run_session.client._request(
                    "POST",
                    f"/api/runs/{self.run_session.run_id}/{path}",
                    payload,
                )
        except Exception:
            traceback.print_exc()

    async def _post(self, path: str, payload: dict[str, Any]) -> None:
        # Off the event loop so a slow backend never stalls the agent.
        await asyncio.to_thread(self._post_sync, path, payload)

    def _observation(
        self,
        kind: str,
        step_id: str,
        parent_step_id: str | None,
        status: str,
        **fields: Any,
    ) -> dict[str, Any]:
        return {
            "observations": [
                {
                    "kind": kind,
                    "step_id": step_id,
                    "parent_step_id": parent_step_id,
                    "status": status,
                    **fields,
                }
            ]
        }

    # ── Run lifecycle ───────────────────────────────────────────────────────

    async def wrap_run(self, ctx: Any, *, handler: Any) -> Any:
        step_id = _new_step_id("run")
        parent_step_id = _CURRENT_STEP.get()
        agent_name = getattr(ctx.agent, "name", None) or "agent"
        started_at = time.perf_counter()
        base_metadata = {
            "agent_name": agent_name,
            "pydantic_run_id": getattr(ctx, "run_id", None),
            "conversation_id": getattr(ctx, "conversation_id", None),
        }
        await self._post(
            "observations",
            self._observation(
                "chain_step",
                step_id,
                parent_step_id,
                "running",
                input_summary=f"Pydantic AI run '{agent_name}' started",
                metadata={**base_metadata, "prompt_summary": summarize_value(ctx.prompt, self.redact_fields)},
            ),
        )
        token = _CURRENT_STEP.set(step_id)
        try:
            result = await handler()
        except BaseException as exc:
            _CURRENT_STEP.reset(token)
            # Sync post: stays safe when the run is being cancelled.
            self._post_sync(
                "observations",
                self._observation(
                    "chain_step",
                    step_id,
                    parent_step_id,
                    "failed",
                    duration_ms=_elapsed_ms(started_at),
                    error_code=exc.__class__.__name__,
                    error_summary=str(exc),
                    metadata=base_metadata,
                ),
            )
            raise
        _CURRENT_STEP.reset(token)
        output = getattr(result, "output", None)
        await self._post(
            "observations",
            self._observation(
                "chain_step",
                step_id,
                parent_step_id,
                "succeeded",
                duration_ms=_elapsed_ms(started_at),
                input_summary=f"Pydantic AI run '{agent_name}' completed",
                metadata={
                    **base_metadata,
                    **_usage_metadata(getattr(result, "usage", None)),
                    "output_summary": summarize_value(output, self.redact_fields),
                    "output_hash": stable_hash(output),
                },
            ),
        )
        return result

    # ── Model request lifecycle ─────────────────────────────────────────────

    async def wrap_model_request(self, ctx: Any, *, request_context: Any, handler: Any) -> Any:
        if not self.record_model_events:
            return await handler(request_context)

        step_id = _new_step_id("llm")
        parent_step_id = _CURRENT_STEP.get()
        model_id = getattr(request_context, "model_id", None)
        started_at = time.perf_counter()
        metadata = {
            "message_count": len(getattr(request_context, "messages", None) or []),
            "run_step": getattr(ctx, "run_step", None),
        }
        await self._post(
            "observations",
            self._observation(
                "llm_call",
                step_id,
                parent_step_id,
                "running",
                model=model_id,
                metadata=metadata,
            ),
        )
        try:
            response = await handler(request_context)
        except BaseException as exc:
            self._post_sync(
                "observations",
                self._observation(
                    "llm_call",
                    step_id,
                    parent_step_id,
                    "failed",
                    duration_ms=_elapsed_ms(started_at),
                    model=model_id,
                    error_code=exc.__class__.__name__,
                    error_summary=str(exc),
                    metadata=metadata,
                ),
            )
            raise
        tool_names = [
            part.tool_name for part in response.parts if getattr(part, "part_kind", None) == "tool-call"
        ]
        await self._post(
            "observations",
            self._observation(
                "llm_call",
                step_id,
                parent_step_id,
                "succeeded",
                duration_ms=_elapsed_ms(started_at),
                provider=response.provider_name,
                model=response.model_name or model_id,
                metadata={
                    **metadata,
                    **_usage_metadata(response.usage),
                    "finish_reason": str(response.finish_reason) if response.finish_reason else None,
                    "requested_tools": tool_names,
                },
            ),
        )
        return response

    # ── Tool execution lifecycle ────────────────────────────────────────────

    async def wrap_tool_execute(
        self, ctx: Any, *, call: Any, tool_def: Any, args: Any, handler: Any
    ) -> Any:
        if not self.record_tool_events:
            return await handler(args)

        step_id = _new_step_id("tool")
        started_at = time.perf_counter()
        # /tool-results records both the started and completed events and keeps
        # tool_count/error_count; an extra tool_call observation would duplicate them.
        result: dict[str, Any] = {
            "call_id": call.tool_call_id,
            "name": call.tool_name,
            "step_id": step_id,
            "parent_step_id": _CURRENT_STEP.get(),
            "args": redact_payload(dict(args), self.redact_fields),
        }
        try:
            output = await handler(args)
        except (CallDeferred, ApprovalRequired):
            # Deferral is control flow, not a failure: the tool runs again later.
            raise
        except BaseException as exc:
            self._post_sync(
                "tool-results",
                {
                    "results": [
                        {
                            **result,
                            "status": "failed",
                            "output_hash": stable_hash({"error": str(exc)}),
                            "error_code": exc.__class__.__name__,
                            "error_summary": str(exc),
                            "duration_ms": _elapsed_ms(started_at),
                        }
                    ]
                },
            )
            raise
        await self._post(
            "tool-results",
            {
                "results": [
                    {
                        **result,
                        "status": "succeeded",
                        "output_summary": summarize_value(output, self.redact_fields),
                        "output_hash": stable_hash(output),
                        "duration_ms": _elapsed_ms(started_at),
                    }
                ]
            },
        )
        return output

    # ── Graph node lifecycle (opt-in) ───────────────────────────────────────

    async def wrap_node_run(self, ctx: Any, *, node: Any, handler: Any) -> Any:
        if not self.record_node_events:
            return await handler(node)

        step_id = _new_step_id("node")
        parent_step_id = _CURRENT_STEP.get()
        node_name = node.__class__.__name__
        started_at = time.perf_counter()
        await self._post(
            "observations",
            self._observation(
                "agent_action",
                step_id,
                parent_step_id,
                "running",
                input_summary=f"Node {node_name}",
                metadata={"node": node_name, "run_step": getattr(ctx, "run_step", None)},
            ),
        )
        try:
            result = await handler(node)
        except BaseException as exc:
            self._post_sync(
                "observations",
                self._observation(
                    "agent_action",
                    step_id,
                    parent_step_id,
                    "failed",
                    duration_ms=_elapsed_ms(started_at),
                    error_code=exc.__class__.__name__,
                    error_summary=str(exc),
                    metadata={"node": node_name},
                ),
            )
            raise
        await self._post(
            "observations",
            self._observation(
                "agent_action",
                step_id,
                parent_step_id,
                "succeeded",
                duration_ms=_elapsed_ms(started_at),
                input_summary=f"Node {node_name} completed",
                metadata={"node": node_name},
            ),
        )
        return result
