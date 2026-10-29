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
import queue
import sys
import threading
import time
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.exceptions import ApprovalRequired, CallDeferred
from pydantic_core import to_jsonable_python
from trace_agent_sdk.redaction import redact_keys, redact_payload, stable_hash, summarize_value

# Step id of the innermost run/node/tool being executed. ContextVars propagate down
# into model requests and tool tasks (also parallel ones) without sharing state.
_CURRENT_STEP: ContextVar[str | None] = ContextVar("trace_agent_pydantic_ai_step", default=None)

# Longest text kept of one message or tool result: a whole file or a base64 image is not content to audit.
_MAX_TEXT = 20_000


def current_step_id() -> str | None:
    """Id of the step being run: inside a tool, the step of that tool.

    Pass it as ``parent_step_id`` to what you record by hand from inside a tool
    (``run.record_command(..., parent_step_id=current_step_id())``) and it appears under the tool in the timeline.
    """
    return _CURRENT_STEP.get()


def _clip(value: Any) -> Any:
    """A copy of a JSON value with very long texts cut."""
    if isinstance(value, str):
        return value if len(value) <= _MAX_TEXT else f"{value[:_MAX_TEXT]}... [{len(value) - _MAX_TEXT} more characters]"
    if isinstance(value, dict):
        return {str(key): _clip(inner) for key, inner in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clip(inner) for inner in value]
    return value


def _plain(value: Any) -> Any:
    """A value as plain JSON data: an output that is a model object would otherwise be summarized as its Python repr."""
    try:
        return to_jsonable_python(value, fallback=str)
    except Exception:  # noqa: BLE001 - a summary of the repr is better than none
        return value


def _json(value: Any, redact_fields: list[str]) -> Any:
    return _clip(redact_keys(to_jsonable_python(value, fallback=str), redact_fields))


def _text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, (list, tuple)):
        return "\n".join(item if isinstance(item, str) else "[non-text content]" for item in content)
    return str(content)


def _genai_messages(messages: Any, redact_fields: list[str]) -> list[dict[str, Any]]:
    """Pydantic AI messages in the shape of the OpenTelemetry GenAI conventions, which is what the UI reads.

    A request holds several parts (system prompt, user prompt, tool results): each one is a message of its own.
    The instructions of the agent do not travel as a part but beside the request: they come first, as a system message.
    """
    out: list[dict[str, Any]] = []
    instructions = None
    for message in messages or []:
        if getattr(message, "kind", None) != "response" and getattr(message, "instructions", None):
            instructions = message.instructions  # the last request is the one that was sent
    if instructions:
        out.append({"role": "system", "parts": [{"type": "text", "content": _clip(_text(instructions))}]})
    for message in messages or []:
        if getattr(message, "kind", None) == "response":
            out.append({"role": "assistant", "parts": _response_parts(message, redact_fields)})
            continue
        for part in getattr(message, "parts", None) or []:
            kind = getattr(part, "part_kind", "")
            if kind == "system-prompt":
                out.append({"role": "system", "parts": [{"type": "text", "content": _clip(_text(part.content))}]})
            elif kind == "user-prompt":
                out.append({"role": "user", "parts": [{"type": "text", "content": _clip(_text(part.content))}]})
            elif kind == "tool-return":
                result = _json(part.content, redact_fields)
                out.append({"role": "tool", "parts": [{"type": "tool_call_response", "id": part.tool_call_id, "name": part.tool_name, "result": result}]})
            elif kind == "retry-prompt":
                text = part.model_response() if callable(getattr(part, "model_response", None)) else _text(part.content)
                out.append({"role": "tool" if part.tool_name else "user", "parts": [{"type": "text", "content": _clip(text)}]})
    return out


def _response_parts(response: Any, redact_fields: list[str]) -> list[dict[str, Any]]:
    parts: list[dict[str, Any]] = []
    for part in getattr(response, "parts", None) or []:
        kind = getattr(part, "part_kind", "")
        if kind == "text":
            parts.append({"type": "text", "content": _clip(part.content)})
        elif kind == "thinking":
            parts.append({"type": "thinking", "content": _clip(part.content)})
        elif kind == "tool-call":
            try:
                arguments = part.args_as_dict()
            except Exception:  # noqa: BLE001 - arguments that are not valid JSON are kept as text
                arguments = part.args
            parts.append({"type": "tool_call", "id": part.tool_call_id, "name": part.tool_name, "arguments": _json(arguments, redact_fields)})
        else:
            parts.append({"type": kind})
    return parts


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
    graph node lifecycles.  Events are delivered by a background thread, so a slow
    or unreachable backend never stalls or crashes the agent: after a failed
    delivery, events are dropped for ``failure_cooldown`` seconds, and the end of
    the outermost run waits at most ``flush_timeout`` seconds for pending events,
    so that ``run.finish()`` arrives after them.
    """

    run_session: Any = None
    record_model_events: bool = True
    record_tool_events: bool = True
    record_node_events: bool = False
    redact_fields: list[str] = field(default_factory=list)
    failure_cooldown: float = 30.0
    flush_timeout: float = 5.0
    # Send what the model was asked and what it answered, so a call can be audited. The server keeps it only
    # while TRACE_AGENT_CAPTURE_FULL_PAYLOADS is on.
    capture_content: bool = True
    # One consumer keeps events in order. That also matters because the backend
    # numbers events per run without locking, so concurrent posts would collide.
    _queue: queue.Queue = field(default_factory=lambda: queue.Queue(maxsize=1000), init=False, repr=False, compare=False)
    _worker: threading.Thread | None = field(default=None, init=False, repr=False, compare=False)
    _worker_lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False, compare=False)
    _paused_until: float = field(default=0.0, init=False, repr=False, compare=False)

    def _whole_output(self, output: Any) -> Any:
        """What a tool returned, whole, to show it formatted; masked and clipped like the content of a model call."""
        if not self.capture_content:
            return None
        try:
            return _json(output, self.redact_fields)
        except Exception:  # noqa: BLE001 - what cannot be shown is left out; the agent must not notice
            return None

    # ── Delivery ────────────────────────────────────────────────────────────

    def _enqueue(self, path: str, payload: dict[str, Any]) -> None:
        """Queue a payload for the backend; never blocks and never raises."""
        self._ensure_worker()
        try:
            self._queue.put_nowait((path, payload, None))
        except queue.Full:
            pass  # Tracing is best effort: dropping beats stalling the agent.

    def _ensure_worker(self) -> None:
        with self._worker_lock:
            if self._worker is None or not self._worker.is_alive():
                self._worker = threading.Thread(target=self._deliver_forever, name="trace-agent-pydantic-ai", daemon=True)
                self._worker.start()

    def _deliver_forever(self) -> None:
        while True:
            path, payload, flushed = self._queue.get()
            try:
                if flushed is not None:
                    flushed.set()
                elif time.monotonic() >= self._paused_until:
                    self._deliver(path, payload)
            finally:
                self._queue.task_done()

    def _deliver(self, path: str, payload: dict[str, Any]) -> None:
        try:
            self.run_session.client._request("POST", f"/api/runs/{self.run_session.run_id}/{path}", payload)
        except Exception as exc:
            self._paused_until = time.monotonic() + self.failure_cooldown
            print(
                f"[trace-agent] could not deliver trace data ({type(exc).__name__}); "
                f"pausing delivery for {self.failure_cooldown:g}s. The agent is not affected.",
                file=sys.stderr,
            )

    async def _flush(self) -> None:
        """Wait, for a bounded time, until everything queued so far was delivered."""
        flushed = threading.Event()
        try:
            self._ensure_worker()
            self._queue.put_nowait((None, None, flushed))
        except queue.Full:
            return
        try:
            await asyncio.to_thread(flushed.wait, self.flush_timeout)
        except BaseException:  # noqa: BLE001 - never let tracing mask the run's own outcome
            pass

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
        self._enqueue(
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
            self._enqueue(
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
            if parent_step_id is None:
                await self._flush()
            raise
        _CURRENT_STEP.reset(token)
        output = getattr(result, "output", None)
        self._enqueue(
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
                    "output_summary": summarize_value(_plain(output), self.redact_fields, sort_keys=False),
                    "output_hash": stable_hash(output),
                },
            ),
        )
        # The outermost run waits (bounded) for its events, so that a following
        # run.finish() reaches the backend after them.
        if parent_step_id is None:
            await self._flush()
        return result

    # ── Model request lifecycle ─────────────────────────────────────────────

    async def wrap_model_request(self, ctx: Any, *, request_context: Any, handler: Any) -> Any:
        if not self.record_model_events:
            return await handler(request_context)

        step_id = _new_step_id("llm")
        parent_step_id = _CURRENT_STEP.get()
        model = getattr(request_context, "model", None)
        # The model and its provider are known before the model answers: both rows of the call say the same about them.
        model_id = getattr(request_context, "model_id", None) or getattr(model, "model_name", None)
        provider = getattr(model, "system", None)
        started_at = time.perf_counter()
        metadata = {
            "message_count": len(getattr(request_context, "messages", None) or []),
            "run_step": getattr(ctx, "run_step", None),
        }
        self._enqueue(
            "observations",
            self._observation(
                "llm_call",
                step_id,
                parent_step_id,
                "running",
                provider=provider,
                model=model_id,
                input_summary=f"Model request to {model_id or 'model'}",
                metadata=metadata,
            ),
        )
        try:
            response = await handler(request_context)
        except BaseException as exc:
            self._enqueue(
                "observations",
                self._observation(
                    "llm_call",
                    step_id,
                    parent_step_id,
                    "failed",
                    duration_ms=_elapsed_ms(started_at),
                    provider=provider,
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
        answered_by = response.provider_name or provider
        content = None
        if self.capture_content:
            try:
                content = {
                    "input_messages": _genai_messages(getattr(request_context, "messages", None), self.redact_fields),
                    "output_messages": [{"role": "assistant", "parts": _response_parts(response, self.redact_fields)}],
                }
            except Exception:  # noqa: BLE001 - what cannot be shown is left out; the agent must not notice
                content = None
        self._enqueue(
            "observations",
            self._observation(
                "llm_call",
                step_id,
                parent_step_id,
                "succeeded",
                duration_ms=_elapsed_ms(started_at),
                provider=answered_by,
                model=response.model_name or model_id,
                input_summary=f"Model responded via {answered_by or 'provider'}",
                content=content,
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
        # While the tool runs it is the current step: what it records by hand (see current_step_id) and the
        # agents it calls hang from it, as they do over OpenTelemetry.
        token = _CURRENT_STEP.set(step_id)
        try:
            output = await handler(args)
        except (CallDeferred, ApprovalRequired):
            # Deferral is control flow, not a failure: the tool runs again later.
            raise
        except BaseException as exc:
            self._enqueue(
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
        finally:
            _CURRENT_STEP.reset(token)
        self._enqueue(
            "tool-results",
            {
                "results": [
                    {
                        **result,
                        "status": "succeeded",
                        "output_summary": summarize_value(_plain(output), self.redact_fields, sort_keys=False),
                        "output": self._whole_output(output),
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
        self._enqueue(
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
            self._enqueue(
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
        self._enqueue(
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
