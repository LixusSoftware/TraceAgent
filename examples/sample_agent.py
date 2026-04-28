from __future__ import annotations

import os

from dotenv import load_dotenv

from trace_agent_sdk import TraceAgentClient


def main() -> None:
    load_dotenv()
    client = TraceAgentClient(base_url=os.getenv("TRACE_AGENT_PROXY_URL", "http://127.0.0.1:8000"))
    run = client.start_run(
        agent_name="sample-research-agent",
        goal="Summarize the weather workflow and capture the tool trace.",
        metadata={"environment": "local-demo"},
    )

    @run.tool(name="get_weather", description="Return a mock weather report for a city.")
    def get_weather(city: str) -> dict[str, str]:
        return {"city": city, "forecast": "sunny", "temperature_c": "23"}

    model_name = os.getenv("TRACE_AGENT_TEST_MODEL", "local-model")
    result = run.create_model_turn(
        [{"role": "user", "content": "Check the weather in Madrid and summarize it briefly."}],
        model=model_name,
    )
    run.finish(result.assistant_message)


if __name__ == "__main__":
    main()
