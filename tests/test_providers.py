from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from visor_agentico.config import Settings
from visor_agentico.main import build_provider_registry
from visor_agentico.schemas import ToolDefinition
from visor_agentico.services.provider import (
    AnthropicProviderAdapter,
    GoogleProviderAdapter,
    KimiProviderAdapter,
    LMStudioProviderAdapter,
    OpenAIProviderAdapter,
    ProviderToolCall,
    ProviderTurnRequest,
)


# ── OpenAI ──────────────────────────────────────────────────────────────────

class TestOpenAIProviderAdapter:
    def test_generate_turn_with_tools(self) -> None:
        settings = Settings(openai_api_key="test-key", openai_base_url=None)
        adapter = OpenAIProviderAdapter(settings)

        mock_message = MagicMock()
        mock_message.content = "Using tool"
        mock_message.model_dump.return_value = {"role": "assistant", "content": "Using tool"}
        mock_func = MagicMock()
        mock_func.name = "search"
        mock_func.arguments = json.dumps({"q": "hello"})
        mock_message.tool_calls = [
            MagicMock(id="call-1", function=mock_func)
        ]

        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock(message=mock_message, finish_reason="tool_calls")]
        mock_completion.id = "resp-1"
        mock_completion.usage.model_dump.return_value = {"prompt_tokens": 10, "completion_tokens": 5}
        mock_completion.service_tier = None

        with patch("visor_agentico.services.provider.OpenAI") as MockClient:
            MockClient.return_value.chat.completions.create.return_value = mock_completion
            request = ProviderTurnRequest(
                model="gpt-4",
                messages=[{"role": "user", "content": "Hello"}],
                tools=[ToolDefinition(name="search", description="Search docs", input_schema={})],
            )
            response = adapter.generate_turn(request)

        assert response.summary == "Model requested 1 tool call(s)."
        assert len(response.tool_calls) == 1
        assert response.tool_calls[0].name == "search"
        assert response.tool_calls[0].arguments == {"q": "hello"}
        assert response.metadata["response_id"] == "resp-1"
        assert response.metadata["usage"]["prompt_tokens"] == 10

    def test_generate_turn_without_tools(self) -> None:
        settings = Settings(openai_api_key="test-key", openai_base_url=None)
        adapter = OpenAIProviderAdapter(settings)

        mock_message = MagicMock()
        mock_message.content = "Hello back"
        mock_message.model_dump.return_value = {"role": "assistant", "content": "Hello back"}
        mock_message.tool_calls = None

        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock(message=mock_message, finish_reason="stop")]
        mock_completion.id = "resp-2"
        mock_completion.usage = None

        with patch("visor_agentico.services.provider.OpenAI") as MockClient:
            MockClient.return_value.chat.completions.create.return_value = mock_completion
            request = ProviderTurnRequest(
                model="gpt-4",
                messages=[{"role": "user", "content": "Hello"}],
                tools=[],
            )
            response = adapter.generate_turn(request)

        assert response.summary == "Hello back"
        assert len(response.tool_calls) == 0
        assert response.assistant_message == {"role": "assistant", "content": "Hello back"}

    def test_missing_config(self) -> None:
        settings = Settings(openai_api_key=None, openai_base_url=None)
        adapter = OpenAIProviderAdapter(settings)
        with pytest.raises(RuntimeError, match="VISOR_OPENAI_API_KEY"):
            adapter.generate_turn(
                ProviderTurnRequest(model="gpt-4", messages=[], tools=[])
            )


# ── Anthropic ───────────────────────────────────────────────────────────────

class TestAnthropicProviderAdapter:
    def test_generate_turn_with_tools(self) -> None:
        settings = Settings(anthropic_api_key="test-key", anthropic_base_url=None)
        adapter = AnthropicProviderAdapter(settings)

        mock_block_tool = MagicMock()
        mock_block_tool.type = "tool_use"
        mock_block_tool.id = "tu-1"
        mock_block_tool.name = "search"
        mock_block_tool.input = {"q": "hello"}

        mock_completion = MagicMock()
        mock_completion.content = [mock_block_tool]
        mock_completion.id = "resp-ant-1"
        mock_completion.stop_reason = "tool_use"
        mock_completion.usage.input_tokens = 20
        mock_completion.usage.output_tokens = 10

        with patch("visor_agentico.services.provider.Anthropic") as MockClient:
            MockClient.return_value.messages.create.return_value = mock_completion
            request = ProviderTurnRequest(
                model="claude-3-sonnet",
                messages=[{"role": "user", "content": "Hello"}],
                tools=[ToolDefinition(name="search", description="Search docs", input_schema={})],
            )
            response = adapter.generate_turn(request)

        assert response.summary == "Model requested 1 tool call(s)."
        assert len(response.tool_calls) == 1
        assert response.tool_calls[0].name == "search"
        assert response.metadata["usage"]["prompt_tokens"] == 20

    def test_generate_turn_without_tools(self) -> None:
        settings = Settings(anthropic_api_key="test-key", anthropic_base_url=None)
        adapter = AnthropicProviderAdapter(settings)

        mock_block_text = MagicMock()
        mock_block_text.type = "text"
        mock_block_text.text = "Hello back"

        mock_completion = MagicMock()
        mock_completion.content = [mock_block_text]
        mock_completion.id = "resp-ant-2"
        mock_completion.stop_reason = "end_turn"
        mock_completion.usage.input_tokens = 15
        mock_completion.usage.output_tokens = 5

        with patch("visor_agentico.services.provider.Anthropic") as MockClient:
            MockClient.return_value.messages.create.return_value = mock_completion
            request = ProviderTurnRequest(
                model="claude-3-sonnet",
                messages=[{"role": "user", "content": "Hello"}],
                tools=[],
            )
            response = adapter.generate_turn(request)

        assert response.summary == "Hello back"
        assert len(response.tool_calls) == 0

    def test_missing_config(self) -> None:
        settings = Settings(anthropic_api_key=None, anthropic_base_url=None)
        adapter = AnthropicProviderAdapter(settings)
        with pytest.raises(RuntimeError, match="VISOR_ANTHROPIC_API_KEY"):
            adapter.generate_turn(
                ProviderTurnRequest(model="claude-3", messages=[], tools=[])
            )

    def test_sdk_not_installed(self) -> None:
        settings = Settings(anthropic_api_key="test-key", anthropic_base_url=None)
        adapter = AnthropicProviderAdapter(settings)
        with patch("visor_agentico.services.provider.Anthropic", None):
            with pytest.raises(RuntimeError, match="anthropic SDK is not installed"):
                adapter.generate_turn(
                    ProviderTurnRequest(model="claude-3", messages=[], tools=[])
                )


# ── Google ──────────────────────────────────────────────────────────────────

class TestGoogleProviderAdapter:
    def test_generate_turn_with_tools(self) -> None:
        settings = Settings(google_api_key="test-key")
        adapter = GoogleProviderAdapter(settings)

        mock_part_text = MagicMock()
        mock_part_text.text = "Using tool"
        mock_part_text.function_call = None

        mock_func_call = MagicMock()
        mock_func_call.name = "search"
        mock_func_call.args = {"q": "hello"}
        mock_part_call = MagicMock()
        mock_part_call.text = None
        mock_part_call.function_call = mock_func_call

        mock_candidate = MagicMock()
        mock_candidate.content.parts = [mock_part_text, mock_part_call]
        mock_candidate.finish_reason.name = "STOP"

        mock_response = MagicMock()
        mock_response.candidates = [mock_candidate]
        mock_response.usage_metadata.prompt_token_count = 25
        mock_response.usage_metadata.candidates_token_count = 12

        with patch("visor_agentico.services.provider.genai") as MockGenAI:
            mock_model = MagicMock()
            mock_model.generate_content.return_value = mock_response
            MockGenAI.GenerativeModel.return_value = mock_model
            request = ProviderTurnRequest(
                model="gemini-1.5-pro",
                messages=[{"role": "user", "content": "Hello"}],
                tools=[ToolDefinition(name="search", description="Search docs", input_schema={})],
            )
            response = adapter.generate_turn(request)

        assert response.summary == "Model requested 1 tool call(s)."
        assert len(response.tool_calls) == 1
        assert response.tool_calls[0].name == "search"
        assert response.metadata["usage"]["prompt_tokens"] == 25

    def test_generate_turn_without_tools(self) -> None:
        settings = Settings(google_api_key="test-key")
        adapter = GoogleProviderAdapter(settings)

        mock_part = MagicMock()
        mock_part.text = "Hello back"
        mock_part.function_call = None

        mock_candidate = MagicMock()
        mock_candidate.content.parts = [mock_part]
        mock_candidate.finish_reason.name = "STOP"

        mock_response = MagicMock()
        mock_response.candidates = [mock_candidate]
        mock_response.usage_metadata = None

        with patch("visor_agentico.services.provider.genai") as MockGenAI:
            mock_model = MagicMock()
            mock_model.generate_content.return_value = mock_response
            MockGenAI.GenerativeModel.return_value = mock_model
            request = ProviderTurnRequest(
                model="gemini-1.5-pro",
                messages=[{"role": "user", "content": "Hello"}],
                tools=[],
            )
            response = adapter.generate_turn(request)

        assert response.summary == "Hello back"
        assert len(response.tool_calls) == 0

    def test_missing_config(self) -> None:
        settings = Settings(google_api_key=None)
        adapter = GoogleProviderAdapter(settings)
        with pytest.raises(RuntimeError, match="VISOR_GOOGLE_API_KEY"):
            adapter.generate_turn(
                ProviderTurnRequest(model="gemini", messages=[], tools=[])
            )

    def test_sdk_not_installed(self) -> None:
        settings = Settings(google_api_key="test-key")
        adapter = GoogleProviderAdapter(settings)
        with patch("visor_agentico.services.provider.genai", None):
            with pytest.raises(RuntimeError, match="google-generativeai SDK is not installed"):
                adapter.generate_turn(
                    ProviderTurnRequest(model="gemini", messages=[], tools=[])
                )


# ── Kimi ────────────────────────────────────────────────────────────────────

class TestKimiProviderAdapter:
    def test_generate_turn(self) -> None:
        settings = Settings(kimi_api_key="test-key", kimi_base_url=None)
        adapter = KimiProviderAdapter(settings)

        mock_message = MagicMock()
        mock_message.content = "Hello from Kimi"
        mock_message.model_dump.return_value = {"role": "assistant", "content": "Hello from Kimi"}
        mock_message.tool_calls = None

        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock(message=mock_message, finish_reason="stop")]
        mock_completion.id = "resp-kimi-1"
        mock_completion.usage = None

        with patch("visor_agentico.services.provider.OpenAI") as MockClient:
            MockClient.return_value.chat.completions.create.return_value = mock_completion
            request = ProviderTurnRequest(
                model="kimi-k1",
                messages=[{"role": "user", "content": "Hello"}],
                tools=[],
            )
            response = adapter.generate_turn(request)

        assert response.summary == "Hello from Kimi"
        assert response.metadata["response_id"] == "resp-kimi-1"

    def test_missing_config(self) -> None:
        settings = Settings(kimi_api_key=None, kimi_base_url=None)
        adapter = KimiProviderAdapter(settings)
        with pytest.raises(RuntimeError, match="VISOR_KIMI_API_KEY"):
            adapter.generate_turn(
                ProviderTurnRequest(model="kimi-k1", messages=[], tools=[])
            )


# ── Registry ────────────────────────────────────────────────────────────────

class TestBuildProviderRegistry:
    def test_all_providers_configured(self) -> None:
        settings = Settings(
            openai_api_key="okey",
            openai_base_url=None,
            anthropic_api_key="akey",
            anthropic_base_url=None,
            google_api_key="gkey",
            kimi_api_key="kkey",
            kimi_base_url=None,
        )
        registry = build_provider_registry(settings)
        assert set(registry.keys()) == {"openai", "anthropic", "google", "kimi"}

    def test_only_openai(self) -> None:
        settings = Settings(openai_api_key="okey", openai_base_url=None)
        registry = build_provider_registry(settings)
        assert set(registry.keys()) == {"openai"}

    def test_no_credentials_still_has_openai(self) -> None:
        settings = Settings(
            openai_api_key=None,
            openai_base_url=None,
            anthropic_api_key=None,
            anthropic_base_url=None,
            google_api_key=None,
            kimi_api_key=None,
            kimi_base_url=None,
            lmstudio_base_url=None,
        )
        registry = build_provider_registry(settings)
        assert "openai" in registry
        assert len(registry) == 1

    def test_lmstudio_registered_when_base_url_set(self) -> None:
        settings = Settings(
            openai_api_key=None,
            openai_base_url=None,
            lmstudio_base_url="http://localhost:1234",
        )
        registry = build_provider_registry(settings)
        assert "lmstudio" in registry
        assert isinstance(registry["lmstudio"], LMStudioProviderAdapter)


# ── LM Studio ───────────────────────────────────────────────────────────────

class TestLMStudioProviderAdapter:
    def test_openai_mode_delegates(self) -> None:
        settings = Settings(
            lmstudio_base_url="http://localhost:1234",
            lmstudio_mode="openai",
            lmstudio_api_key=None,
        )
        adapter = LMStudioProviderAdapter(settings)
        assert adapter._delegate.provider_name in ("openai", "lmstudio")

    def test_anthropic_mode_delegates(self) -> None:
        settings = Settings(
            lmstudio_base_url="http://localhost:1234",
            lmstudio_mode="anthropic",
            lmstudio_api_key=None,
        )
        adapter = LMStudioProviderAdapter(settings)
        assert adapter._delegate.provider_name in ("anthropic", "lmstudio")

    def test_native_mode_http(self) -> None:
        settings = Settings(
            lmstudio_base_url="http://localhost:1234",
            lmstudio_mode="native",
            lmstudio_api_key=None,
        )
        adapter = LMStudioProviderAdapter(settings)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "model_instance_id": "mi-1",
            "output": [
                {"type": "message", "content": "Hello from LM Studio native"},
            ],
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.post", return_value=mock_response):
            request = ProviderTurnRequest(
                model="qwen2.5",
                messages=[{"role": "user", "content": "Hello"}],
                tools=[],
            )
            response = adapter.generate_turn(request)

        assert response.summary == "Hello from LM Studio native"
        assert response.metadata["model_instance_id"] == "mi-1"
        assert len(response.tool_calls) == 0

    def test_native_mode_with_tool_call(self) -> None:
        settings = Settings(
            lmstudio_base_url="http://localhost:1234",
            lmstudio_mode="native",
            lmstudio_api_key="secret",
        )
        adapter = LMStudioProviderAdapter(settings)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "model_instance_id": "mi-2",
            "output": [
                {"type": "tool_call", "tool": "search", "arguments": {"q": "hello"}},
            ],
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.post", return_value=mock_response):
            request = ProviderTurnRequest(
                model="qwen2.5",
                messages=[{"role": "user", "content": "Hello"}],
                tools=[],
            )
            response = adapter.generate_turn(request)

        assert response.summary == "Model requested 1 tool call(s)."
        assert len(response.tool_calls) == 1
        assert response.tool_calls[0].name == "search"
        assert response.tool_calls[0].arguments == {"q": "hello"}

    def test_invalid_mode_raises(self) -> None:
        settings = Settings(
            lmstudio_base_url="http://localhost:1234",
            lmstudio_mode="invalid",
        )
        with pytest.raises(ValueError, match="Invalid lmstudio_mode"):
            LMStudioProviderAdapter(settings)
