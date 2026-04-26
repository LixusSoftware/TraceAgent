from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from openai import OpenAI

from visor_agentico.config import Settings
from visor_agentico.redaction import summarize_value
from visor_agentico.schemas import ToolDefinition


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
