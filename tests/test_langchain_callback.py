"""Unit tests for VisorLangChainCallback.

These tests mock the HTTP layer and verify that LangChain callbacks are
correctly translated into Visor observations.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from visor_agentico.langchain_callback import VisorLangChainCallback


@pytest.fixture
def mock_run_session() -> MagicMock:
    session = MagicMock()
    session.run_id = "run-123"
    session.client._request = MagicMock(return_value={"status": "ok"})
    return session


@pytest.fixture
def callback(mock_run_session) -> VisorLangChainCallback:
    return VisorLangChainCallback(mock_run_session)


class TestChainCallbacks:
    def test_on_chain_start_posts_observation(self, callback, mock_run_session) -> None:
        callback.on_chain_start(
            serialized={"name": "LLMChain"},
            inputs={"input": "hello"},
            run_id="chain-1",
            parent_run_id=None,
        )
        mock_run_session.client._request.assert_called_once()
        args = mock_run_session.client._request.call_args
        assert args[0][0] == "POST"
        assert "/observations" in args[0][1]
        obs = args[0][2]["observations"][0]
        assert obs["kind"] == "chain_step"
        assert obs["status"] == "running"
        assert obs["step_id"] == "chain-1"
        assert obs["metadata"]["chain_type"] == "LLMChain"

    def test_on_chain_end_posts_observation(self, callback, mock_run_session) -> None:
        callback._starts["chain-1"] = 0.0
        callback.on_chain_end(
            outputs={"output": "world"},
            run_id="chain-1",
            parent_run_id=None,
        )
        args = mock_run_session.client._request.call_args
        obs = args[0][2]["observations"][0]
        assert obs["kind"] == "chain_step"
        assert obs["status"] == "succeeded"
        assert obs["duration_ms"] >= 0

    def test_on_chain_error_posts_failed(self, callback, mock_run_session) -> None:
        callback._starts["chain-1"] = 0.0
        callback.on_chain_error(
            error=ValueError("boom"),
            run_id="chain-1",
            parent_run_id=None,
        )
        args = mock_run_session.client._request.call_args
        obs = args[0][2]["observations"][0]
        assert obs["kind"] == "chain_step"
        assert obs["status"] == "failed"
        assert obs["error_code"] == "ValueError"
        assert "boom" in obs["error_summary"]


class TestLLMCallbacks:
    def test_on_llm_start_posts_observation(self, callback, mock_run_session) -> None:
        callback.on_llm_start(
            serialized={"name": "OpenAI"},
            prompts=["hello"],
            run_id="llm-1",
            parent_run_id="chain-1",
        )
        args = mock_run_session.client._request.call_args
        obs = args[0][2]["observations"][0]
        assert obs["kind"] == "llm_call"
        assert obs["status"] == "running"
        assert obs["step_id"] == "llm-1"
        assert obs["parent_step_id"] == "chain-1"

    def test_on_llm_end_posts_observation(self, callback, mock_run_session) -> None:
        callback._starts["llm-1"] = 0.0
        # Mock LLMResult with OpenAI-style token usage
        result = MagicMock()
        result.llm_output = {"token_usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}
        callback.on_llm_end(
            response=result,
            run_id="llm-1",
            parent_run_id="chain-1",
        )
        args = mock_run_session.client._request.call_args
        obs = args[0][2]["observations"][0]
        assert obs["kind"] == "llm_call"
        assert obs["status"] == "succeeded"
        assert obs["metadata"]["prompt_tokens"] == 10
        assert obs["metadata"]["completion_tokens"] == 5

    def test_on_llm_error_posts_failed(self, callback, mock_run_session) -> None:
        callback._starts["llm-1"] = 0.0
        callback.on_llm_error(
            error=RuntimeError("timeout"),
            run_id="llm-1",
            parent_run_id="chain-1",
        )
        args = mock_run_session.client._request.call_args
        obs = args[0][2]["observations"][0]
        assert obs["kind"] == "llm_call"
        assert obs["status"] == "failed"
        assert obs["error_code"] == "RuntimeError"

    def test_extract_token_usage_openai(self, callback) -> None:
        result = MagicMock()
        result.llm_output = {"token_usage": {"prompt_tokens": 3, "completion_tokens": 2}}
        usage = callback._extract_token_usage(result)
        assert usage["prompt_tokens"] == 3
        assert usage["completion_tokens"] == 2

    def test_extract_token_usage_anthropic(self, callback) -> None:
        result = MagicMock()
        result.llm_output = {"token_usage": {"input_tokens": 4, "output_tokens": 1}}
        usage = callback._extract_token_usage(result)
        assert usage["prompt_tokens"] == 4
        assert usage["completion_tokens"] == 1

    def test_extract_token_usage_empty(self, callback) -> None:
        assert callback._extract_token_usage(None) == {}


class TestToolCallbacks:
    def test_on_tool_start_posts_observation(self, callback, mock_run_session) -> None:
        callback.on_tool_start(
            serialized={"name": "search"},
            input_str='{"q": "hello"}',
            run_id="tool-1",
            parent_run_id="llm-1",
        )
        args = mock_run_session.client._request.call_args
        obs = args[0][2]["observations"][0]
        assert obs["kind"] == "tool_call"
        assert obs["status"] == "running"
        assert obs["tool_name"] == "search"
        assert obs["step_id"] == "tool-1"
        assert obs["parent_step_id"] == "llm-1"

    def test_on_tool_end_posts_result_and_observation(self, callback, mock_run_session) -> None:
        callback._starts["tool-1"] = 0.0
        callback.on_tool_end(
            output="result here",
            run_id="tool-1",
            parent_run_id="llm-1",
            metadata={"name": "search"},
        )
        assert mock_run_session.client._request.call_count == 2
        # First call is tool-results
        args0 = mock_run_session.client._request.call_args_list[0]
        assert "/tool-results" in args0[0][1]
        result = args0[0][2]["results"][0]
        assert result["status"] == "succeeded"
        assert result["name"] == "search"
        # Second call is observation
        args1 = mock_run_session.client._request.call_args_list[1]
        obs = args1[0][2]["observations"][0]
        assert obs["kind"] == "tool_call"
        assert obs["status"] == "succeeded"

    def test_on_tool_error_posts_failed(self, callback, mock_run_session) -> None:
        callback._starts["tool-1"] = 0.0
        callback.on_tool_error(
            error=Exception("fail"),
            run_id="tool-1",
            parent_run_id="llm-1",
            metadata={"name": "search"},
        )
        assert mock_run_session.client._request.call_count == 2
        args0 = mock_run_session.client._request.call_args_list[0]
        result = args0[0][2]["results"][0]
        assert result["status"] == "failed"
        assert result["error_code"] == "Exception"


class TestRetrieverCallbacks:
    def test_on_retriever_start(self, callback, mock_run_session) -> None:
        callback.on_retriever_start(
            serialized={"name": "VectorStore"},
            query="AI agents",
            run_id="ret-1",
            parent_run_id="chain-1",
        )
        args = mock_run_session.client._request.call_args
        obs = args[0][2]["observations"][0]
        assert obs["kind"] == "retriever_query"
        assert obs["status"] == "running"
        assert "AI agents" in obs["input_summary"]

    def test_on_retriever_end(self, callback, mock_run_session) -> None:
        callback._starts["ret-1"] = 0.0
        callback.on_retriever_end(
            documents=[{"page_content": "doc1"}, {"page_content": "doc2"}],
            run_id="ret-1",
            parent_run_id="chain-1",
        )
        args = mock_run_session.client._request.call_args
        obs = args[0][2]["observations"][0]
        assert obs["kind"] == "retriever_query"
        assert obs["status"] == "succeeded"
        assert obs["metadata"]["document_count"] == 2

    def test_retriever_events_disabled(self, mock_run_session) -> None:
        cb = VisorLangChainCallback(mock_run_session, record_retriever_events=False)
        cb.on_retriever_start(
            serialized={"name": "VectorStore"},
            query="AI",
            run_id="ret-1",
        )
        mock_run_session.client._request.assert_not_called()


class TestAgentCallbacks:
    def test_on_agent_action(self, callback, mock_run_session) -> None:
        action = MagicMock()
        action.tool = "search"
        action.tool_input = {"q": "hello"}
        callback.on_agent_action(
            action=action,
            run_id="agent-1",
            parent_run_id="chain-1",
        )
        args = mock_run_session.client._request.call_args
        obs = args[0][2]["observations"][0]
        assert obs["kind"] == "agent_action"
        assert obs["status"] == "running"
        assert obs["tool_name"] == "search"
        assert obs["metadata"]["tool_input"] == {"q": "hello"}

    def test_on_agent_finish(self, callback, mock_run_session) -> None:
        finish = MagicMock()
        finish.return_values = {"output": "done"}
        callback.on_agent_finish(
            finish=finish,
            run_id="agent-1",
            parent_run_id="chain-1",
        )
        args = mock_run_session.client._request.call_args
        obs = args[0][2]["observations"][0]
        assert obs["kind"] == "agent_action"
        assert obs["status"] == "succeeded"
        assert obs["input_summary"] == "Agent finished"


class TestResilience:
    def test_backend_error_is_silenced(self, mock_run_session) -> None:
        mock_run_session.client._request.side_effect = Exception("connection refused")
        callback = VisorLangChainCallback(mock_run_session)
        # Should not raise
        callback.on_chain_start(
            serialized={"name": "Chain"},
            inputs={},
            run_id="chain-1",
        )


class TestSDKNotInstalled:
    def test_raises_when_langchain_missing(self) -> None:
        with patch("visor_agentico.langchain_callback.BaseCallbackHandler", None):
            mock_session = MagicMock()
            with pytest.raises(RuntimeError, match="langchain-core is not installed"):
                VisorLangChainCallback(mock_session)
