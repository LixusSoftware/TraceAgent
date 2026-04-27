from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from openai import OpenAI

from visor_agentico.config import Settings
from visor_agentico.redaction import summarize_value
from visor_agentico.schemas import ToolDefinition


try:
    from anthropic import Anthropic
except ImportError:  # pragma: no cover
    Anthropic = None  # type: ignore[misc,assignment]

try:
    import google.generativeai as genai
    from google.generativeai import protos
except ImportError:  # pragma: no cover
    genai = None  # type: ignore[assignment]
    protos = None  # type: ignore[assignment]


@dataclass
class ProviderToolCall:
    id: str
    name: str
    arguments: dict[str, Any]
    step_id: str
    parent_step_id: str | None = None


@dataclass
class ProviderTurnRequest:
    model: str
    messages: list[dict[str, Any]]
    tools: list[ToolDefinition]
    tool_choice: str | dict[str, Any] = "auto"


@dataclass
class ProviderTurnResponse:
    assistant_message: dict[str, Any] | None = None
    tool_calls: list[ProviderToolCall] = field(default_factory=list)
    summary: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseProviderAdapter(ABC):
    provider_name: str

    @abstractmethod
    def generate_turn(self, request: ProviderTurnRequest) -> ProviderTurnResponse:
        raise NotImplementedError


class OpenAIProviderAdapter(BaseProviderAdapter):
    provider_name = "openai"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def generate_turn(self, request: ProviderTurnRequest) -> ProviderTurnResponse:
        if not self.settings.openai_api_key and not self.settings.openai_base_url:
            raise RuntimeError("VISOR_OPENAI_API_KEY is required for provider 'openai'.")

        api_key = self.settings.openai_api_key or "local-dev"
        client = OpenAI(api_key=api_key, base_url=self.settings.openai_base_url)
        completion = client.chat.completions.create(
            model=request.model,
            messages=request.messages,
            tools=[self._tool_to_openai(tool) for tool in request.tools] or None,
            tool_choice=request.tool_choice,
        )
        message = completion.choices[0].message
        assistant_message = message.model_dump(exclude_none=True)
        tool_calls: list[ProviderToolCall] = []

        for tool_call in message.tool_calls or []:
            arguments = {}
            if tool_call.function.arguments:
                arguments = json.loads(tool_call.function.arguments)
            tool_calls.append(
                ProviderToolCall(
                    id=tool_call.id,
                    name=tool_call.function.name,
                    arguments=arguments,
                    step_id=tool_call.id,
                )
            )

        summary = (
            f"Model requested {len(tool_calls)} tool call(s)."
            if tool_calls
            else summarize_value(message.content or "")
        )
        usage = completion.usage.model_dump(exclude_none=True) if completion.usage else {}
        metadata = {
            "response_id": completion.id,
            "finish_reason": completion.choices[0].finish_reason,
            "tool_call_count": len(tool_calls),
            "usage": usage,
        }
        if getattr(completion, "service_tier", None):
            metadata["service_tier"] = completion.service_tier
        return ProviderTurnResponse(
            assistant_message=assistant_message,
            tool_calls=tool_calls,
            summary=summary,
            metadata=metadata,
        )

    @staticmethod
    def _tool_to_openai(tool: ToolDefinition) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.input_schema or {"type": "object", "properties": {}},
            },
        }


class AnthropicProviderAdapter(BaseProviderAdapter):
    provider_name = "anthropic"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def generate_turn(self, request: ProviderTurnRequest) -> ProviderTurnResponse:
        if Anthropic is None:
            raise RuntimeError("anthropic SDK is not installed. Install it with: uv pip install anthropic")
        if not self.settings.anthropic_api_key and not self.settings.anthropic_base_url:
            raise RuntimeError("VISOR_ANTHROPIC_API_KEY is required for provider 'anthropic'.")

        api_key = self.settings.anthropic_api_key or "local-dev"
        client = Anthropic(api_key=api_key, base_url=self.settings.anthropic_base_url)

        tools = [self._tool_to_anthropic(tool) for tool in request.tools]
        tool_choice = self._map_tool_choice(request.tool_choice)

        completion = client.messages.create(
            model=request.model,
            max_tokens=4096,
            messages=request.messages,  # type: ignore[arg-type]
            tools=tools or None,
            tool_choice=tool_choice,
        )

        content_texts: list[str] = []
        tool_calls: list[ProviderToolCall] = []
        for block in completion.content:
            if block.type == "text":
                content_texts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(
                    ProviderToolCall(
                        id=block.id,
                        name=block.name,
                        arguments=block.input,
                        step_id=block.id,
                    )
                )

        assistant_message: dict[str, Any] = {"role": "assistant"}
        if content_texts:
            assistant_message["content"] = "\n".join(content_texts)
        if tool_calls:
            assistant_message["tool_calls"] = [
                {"id": tc.id, "type": "function", "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)}}
                for tc in tool_calls
            ]

        summary = (
            f"Model requested {len(tool_calls)} tool call(s)."
            if tool_calls
            else summarize_value("\n".join(content_texts))
        )
        usage: dict[str, Any] = {}
        if completion.usage:
            usage = {
                "prompt_tokens": completion.usage.input_tokens,
                "completion_tokens": completion.usage.output_tokens,
                "total_tokens": completion.usage.input_tokens + completion.usage.output_tokens,
            }
        metadata = {
            "response_id": completion.id,
            "finish_reason": completion.stop_reason,
            "tool_call_count": len(tool_calls),
            "usage": usage,
        }
        return ProviderTurnResponse(
            assistant_message=assistant_message,
            tool_calls=tool_calls,
            summary=summary,
            metadata=metadata,
        )

    @staticmethod
    def _tool_to_anthropic(tool: ToolDefinition) -> dict[str, Any]:
        return {
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.input_schema or {"type": "object", "properties": {}},
        }

    @staticmethod
    def _map_tool_choice(tool_choice: str | dict[str, Any]) -> dict[str, Any] | None:
        if tool_choice == "auto":
            return {"type": "auto"}
        if tool_choice == "none":
            return {"type": "none"}
        if tool_choice == "required":
            return {"type": "any"}
        if isinstance(tool_choice, dict) and tool_choice.get("type") == "function":
            return {"type": "tool", "name": tool_choice["function"]["name"]}
        return None


class GoogleProviderAdapter(BaseProviderAdapter):
    provider_name = "google"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def generate_turn(self, request: ProviderTurnRequest) -> ProviderTurnResponse:
        if genai is None or protos is None:
            raise RuntimeError(
                "google-generativeai SDK is not installed. Install it with: uv pip install google-generativeai"
            )
        if not self.settings.google_api_key:
            raise RuntimeError("VISOR_GOOGLE_API_KEY is required for provider 'google'.")

        genai.configure(api_key=self.settings.google_api_key)
        model = genai.GenerativeModel(model_name=request.model)

        contents = self._messages_to_google_contents(request.messages)
        tools = None
        if request.tools:
            decls = [self._tool_to_google(tool) for tool in request.tools]
            tools = [protos.Tool(function_declarations=decls)]

        response = model.generate_content(contents=contents, tools=tools)

        content_texts: list[str] = []
        tool_calls: list[ProviderToolCall] = []
        candidate = response.candidates[0] if response.candidates else None
        if candidate and candidate.content and candidate.content.parts:
            for part in candidate.content.parts:
                if part.text:
                    content_texts.append(part.text)
                if part.function_call:
                    tool_calls.append(
                        ProviderToolCall(
                            id=part.function_call.name,
                            name=part.function_call.name,
                            arguments=dict(part.function_call.args) if part.function_call.args else {},
                            step_id=part.function_call.name,
                        )
                    )

        assistant_message: dict[str, Any] = {"role": "assistant"}
        if content_texts:
            assistant_message["content"] = "\n".join(content_texts)
        if tool_calls:
            assistant_message["tool_calls"] = [
                {"id": tc.id, "type": "function", "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)}}
                for tc in tool_calls
            ]

        summary = (
            f"Model requested {len(tool_calls)} tool call(s)."
            if tool_calls
            else summarize_value("\n".join(content_texts))
        )
        usage: dict[str, Any] = {}
        if response.usage_metadata:
            usage = {
                "prompt_tokens": response.usage_metadata.prompt_token_count,
                "completion_tokens": response.usage_metadata.candidates_token_count,
                "total_tokens": (
                    (response.usage_metadata.prompt_token_count or 0)
                    + (response.usage_metadata.candidates_token_count or 0)
                ),
            }
        metadata = {
            "response_id": getattr(response, "prompt_feedback", None) and getattr(response.prompt_feedback, "block_reason", None) or None,
            "finish_reason": candidate.finish_reason.name if candidate and candidate.finish_reason else None,
            "tool_call_count": len(tool_calls),
            "usage": usage,
        }
        return ProviderTurnResponse(
            assistant_message=assistant_message,
            tool_calls=tool_calls,
            summary=summary,
            metadata=metadata,
        )

    @staticmethod
    def _messages_to_google_contents(messages: list[dict[str, Any]]) -> list[Any]:
        contents: list[Any] = []
        for msg in messages:
            role = msg.get("role", "user")
            text = msg.get("content", "")
            if role == "system":
                # Gemini handles system instructions differently; for simplicity we treat them as user messages
                role = "user"
            contents.append({"role": role, "parts": [text]})
        return contents

    @staticmethod
    def _tool_to_google(tool: ToolDefinition) -> Any:
        if protos is None:
            raise RuntimeError("google-generativeai SDK is not installed.")
        kwargs: dict[str, Any] = {
            "name": tool.name,
            "description": tool.description,
        }
        if tool.input_schema:
            kwargs["parameters"] = tool.input_schema
        return protos.FunctionDeclaration(**kwargs)


class KimiProviderAdapter(OpenAIProviderAdapter):
    provider_name = "kimi"

    def generate_turn(self, request: ProviderTurnRequest) -> ProviderTurnResponse:
        if not self.settings.kimi_api_key and not self.settings.kimi_base_url:
            raise RuntimeError("VISOR_KIMI_API_KEY is required for provider 'kimi'.")

        api_key = self.settings.kimi_api_key or "local-dev"
        client = OpenAI(api_key=api_key, base_url=self.settings.kimi_base_url)
        completion = client.chat.completions.create(
            model=request.model,
            messages=request.messages,
            tools=[self._tool_to_openai(tool) for tool in request.tools] or None,
            tool_choice=request.tool_choice,
        )
        message = completion.choices[0].message
        assistant_message = message.model_dump(exclude_none=True)
        tool_calls: list[ProviderToolCall] = []

        for tool_call in message.tool_calls or []:
            arguments = {}
            if tool_call.function.arguments:
                arguments = json.loads(tool_call.function.arguments)
            tool_calls.append(
                ProviderToolCall(
                    id=tool_call.id,
                    name=tool_call.function.name,
                    arguments=arguments,
                    step_id=tool_call.id,
                )
            )

        summary = (
            f"Model requested {len(tool_calls)} tool call(s)."
            if tool_calls
            else summarize_value(message.content or "")
        )
        usage = completion.usage.model_dump(exclude_none=True) if completion.usage else {}
        metadata = {
            "response_id": completion.id,
            "finish_reason": completion.choices[0].finish_reason,
            "tool_call_count": len(tool_calls),
            "usage": usage,
        }
        return ProviderTurnResponse(
            assistant_message=assistant_message,
            tool_calls=tool_calls,
            summary=summary,
            metadata=metadata,
        )


# ── LM Studio (multi-mode) ──────────────────────────────────────────────────

class _LMStudioSettingsProxy:
    """Inject LM Studio URLs/keys into the fields that existing adapters read."""

    def __init__(self, settings: Settings, mode: str) -> None:
        self._settings = settings
        self._mode = mode
        base = (settings.lmstudio_base_url or "http://localhost:1234").rstrip("/")
        if mode == "openai":
            self._api_key = settings.lmstudio_api_key or "lm-studio"
            self._base_url = f"{base}/v1"
        elif mode == "anthropic":
            self._api_key = settings.lmstudio_api_key or "lm-studio"
            self._base_url = f"{base}/v1"
        else:
            self._api_key = None
            self._base_url = base

    @property
    def openai_api_key(self) -> str | None:
        return self._api_key if self._mode == "openai" else self._settings.openai_api_key

    @property
    def openai_base_url(self) -> str | None:
        return self._base_url if self._mode == "openai" else self._settings.openai_base_url

    @property
    def anthropic_api_key(self) -> str | None:
        return self._api_key if self._mode == "anthropic" else self._settings.anthropic_api_key

    @property
    def anthropic_base_url(self) -> str | None:
        return self._base_url if self._mode == "anthropic" else self._settings.anthropic_base_url

    def __getattr__(self, name: str) -> Any:
        return getattr(self._settings, name)


class _LMStudioNativeAdapter(BaseProviderAdapter):
    """Talk to LM Studio's native /api/v1/chat endpoint via plain HTTP."""

    provider_name = "lmstudio"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def generate_turn(self, request: ProviderTurnRequest) -> ProviderTurnResponse:
        import httpx

        base_url = (self.settings.lmstudio_base_url or "http://localhost:1234").rstrip("/")
        api_key = self.settings.lmstudio_api_key

        payload: dict[str, Any] = {
            "model": request.model,
            "input": self._messages_to_input(request.messages),
        }
        if request.tools:
            # Native API does not accept custom tools in the request;
            # tools must be pre-configured in LM Studio (MCPs / plugins).
            # We still record them in metadata for observability.
            payload["_visor_tools"] = [t.name for t in request.tools]

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        try:
            response = httpx.post(
                f"{base_url}/api/v1/chat",
                json=payload,
                headers=headers,
                timeout=120,
            )
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            raise RuntimeError(f"LM Studio native API request failed: {exc}") from exc

        output = data.get("output", [])
        content_texts: list[str] = []
        tool_calls: list[ProviderToolCall] = []

        for idx, item in enumerate(output):
            if item.get("type") == "message":
                content_texts.append(item.get("content", ""))
            elif item.get("type") == "tool_call":
                tool_name = item.get("tool", "")
                tc_id = f"tc-{tool_name}-{idx}"
                tool_calls.append(
                    ProviderToolCall(
                        id=tc_id,
                        name=tool_name,
                        arguments=item.get("arguments") or {},
                        step_id=tc_id,
                    )
                )

        assistant_message: dict[str, Any] = {"role": "assistant"}
        if content_texts:
            assistant_message["content"] = "\n".join(content_texts)
        if tool_calls:
            assistant_message["tool_calls"] = [
                {"id": tc.id, "type": "function", "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)}}
                for tc in tool_calls
            ]

        summary = (
            f"Model requested {len(tool_calls)} tool call(s)."
            if tool_calls
            else summarize_value("\n".join(content_texts))
        )

        metadata: dict[str, Any] = {
            "model_instance_id": data.get("model_instance_id"),
            "finish_reason": None,
            "tool_call_count": len(tool_calls),
            "usage": {},
        }
        return ProviderTurnResponse(
            assistant_message=assistant_message,
            tool_calls=tool_calls,
            summary=summary,
            metadata=metadata,
        )

    @staticmethod
    def _messages_to_input(messages: list[dict[str, Any]]) -> str:
        parts: list[str] = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                parts.append(f"System: {content}")
            elif role == "user":
                parts.append(f"User: {content}")
            elif role == "assistant":
                parts.append(f"Assistant: {content}")
            elif role == "tool":
                parts.append(f"Tool result: {content}")
        return "\n\n".join(parts)


class LMStudioProviderAdapter(BaseProviderAdapter):
    """Facade that selects the concrete adapter based on lmstudio_mode."""

    provider_name = "lmstudio"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        mode = (settings.lmstudio_mode or "openai").lower()

        if mode == "openai":
            proxy = _LMStudioSettingsProxy(settings, "openai")
            self._delegate: BaseProviderAdapter = OpenAIProviderAdapter(proxy)
        elif mode == "anthropic":
            proxy = _LMStudioSettingsProxy(settings, "anthropic")
            self._delegate = AnthropicProviderAdapter(proxy)
        elif mode == "native":
            self._delegate = _LMStudioNativeAdapter(settings)
        else:
            raise ValueError(
                f"Invalid lmstudio_mode '{mode}'. Must be one of: openai, anthropic, native"
            )

    def generate_turn(self, request: ProviderTurnRequest) -> ProviderTurnResponse:
        return self._delegate.generate_turn(request)
