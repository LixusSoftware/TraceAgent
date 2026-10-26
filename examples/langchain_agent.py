"""Example: LangChain agent instrumented with TraceAgent.

This script demonstrates how to attach the TraceAgentLangChainCallback to a
LangChain agent so that every chain step, LLM call, tool call, and retriever
query is recorded in the TraceAgent backend.

Requirements:
    uv pip install -e ".[langchain]"

Environment:
    TRACE_AGENT_BASE_URL=http://127.0.0.1:8000
    OPENAI_BASE_URL=http://localhost:1234/v1   (for LM Studio)
    OPENAI_API_KEY=lm-studio
"""

from __future__ import annotations

import os

from langchain import hub
from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain_openai import ChatOpenAI
from trace_agent_sdk import TraceAgentClient


def get_weather(city: str) -> str:
    """Get the current weather for a city."""
    return f"Sunny, 23°C in {city}."


def get_news(topic: str) -> str:
    """Get the latest news on a topic."""
    return f"Latest news on {topic}: AI agents are becoming mainstream."


def main() -> None:
    base_url = os.getenv("TRACE_AGENT_BASE_URL", "http://127.0.0.1:8000")
    openai_base_url = os.getenv("OPENAI_BASE_URL", "http://localhost:1234/v1")
    openai_api_key = os.getenv("OPENAI_API_KEY", "lm-studio")

    # 1. Start a TraceAgent run
    client = TraceAgentClient(base_url=base_url)
    run = client.start_run(
        agent_name="langchain-news-weather-agent",
        goal="Answer user questions using weather and news tools",
        metadata={"environment": "local", "model": "qwen2.5"},
    )
    print(f"Run started: {run.run_id}")

    # 2. Build a LangChain agent
    llm = ChatOpenAI(
        model="qwen2.5",
        base_url=openai_base_url,
        api_key=openai_api_key,
        temperature=0.2,
    )
    prompt = hub.pull("hwchase17/openai-tools-agent")

    tools = [
        # Simple Python functions wrapped as LangChain tools
        # (In production you would use @tool decorator or StructuredTool)
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get the current weather for a city",
                "parameters": {
                    "type": "object",
                    "properties": {"city": {"type": "string"}},
                    "required": ["city"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_news",
                "description": "Get the latest news on a topic",
                "parameters": {
                    "type": "object",
                    "properties": {"topic": {"type": "string"}},
                    "required": ["topic"],
                },
            },
        },
    ]

    # For a real LangChain agent we need proper Tool objects.
    # Here we create a minimal demonstration using bind_tools.
    llm_with_tools = llm.bind_tools(tools)

    # 3. Attach the TraceAgent callback
    callback = run.as_langchain_callback()

    # 4. Invoke the model (single turn with tool calling)
    messages = [
        ("system", "You are a helpful assistant. Use tools when needed."),
        ("human", "What's the weather in Madrid and any news about AI?"),
    ]

    response = llm_with_tools.invoke(messages, config={"callbacks": [callback]})
    print(f"Assistant response: {response.content}")

    # 5. Finish the run
    run.finish(response.content)
    print(f"Run finished: {run.run_id}")
    print(f"View at: {base_url}/runs/{run.run_id}")


if __name__ == "__main__":
    main()
