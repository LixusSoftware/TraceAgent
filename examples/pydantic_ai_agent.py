"""Example: Pydantic AI agent instrumented with TraceAgent.

A scripted ``FunctionModel`` stands in for a live LLM, so the example runs without
any API key.  Swap it for a real model string such as "openai:gpt-4o" to trace a
real agent: the TraceAgent capability is the only line that changes nothing else.

Requirements:
    uv sync --extra dev --extra pydantic-ai

Environment:
    TRACE_AGENT_PROXY_URL=http://127.0.0.1:8000
"""

from __future__ import annotations

import os

from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from trace_agent_sdk import TraceAgentClient


def scripted_model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    """Ask for both tools first, then answer once their results are in."""
    if len(messages) == 1:
        return ModelResponse(
            parts=[
                ToolCallPart("get_weather", {"city": "Madrid"}),
                ToolCallPart("get_news", {"topic": "AI agents"}),
            ]
        )
    return ModelResponse(parts=[TextPart("Madrid is sunny at 23C and AI agents are all over the news.")])


def main() -> None:
    base_url = os.getenv("TRACE_AGENT_PROXY_URL", "http://127.0.0.1:8000")

    # 1. Start a TraceAgent run
    client = TraceAgentClient(base_url=base_url)
    run = client.start_run(
        agent_name="pydantic-ai-news-weather-agent",
        goal="Answer user questions using weather and news tools",
        metadata={"environment": "local-demo", "framework": "pydantic-ai"},
    )
    print(f"Run started: {run.run_id}")

    # 2. Build a Pydantic AI agent and attach the TraceAgent capability
    agent = Agent(
        FunctionModel(scripted_model),
        name="pydantic-ai-news-weather-agent",
        capabilities=[run.as_pydantic_ai_capability()],
    )

    @agent.tool_plain
    def get_weather(city: str) -> str:
        """Get the current weather for a city."""
        return f"Sunny, 23°C in {city}."

    @agent.tool_plain
    def get_news(topic: str) -> str:
        """Get the latest news on a topic."""
        return f"Latest news on {topic}: AI agents are becoming mainstream."

    # 3. Run the agent as usual
    result = agent.run_sync("What's the weather in Madrid and any news about AI agents?")
    print(f"Assistant response: {result.output}")

    # 4. Finish the run
    run.finish(result.output)
    print(f"Run finished: {run.run_id}")
    print(f"View at: {base_url}/runs/{run.run_id}")


if __name__ == "__main__":
    main()
