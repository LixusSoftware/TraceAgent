from __future__ import annotations

import os

from dotenv import load_dotenv

from trace_agent_sdk import TraceAgentClient


def main() -> None:
    load_dotenv()
    client = TraceAgentClient(
        base_url=os.getenv("TRACE_AGENT_PROXY_URL", "http://127.0.0.1:8000"),
        timeout=120.0,
    )
    run = client.start_run(
        agent_name="e2e-verify-agent",
        goal="Verify Fase 1 integration with LM Studio",
        metadata={"environment": "e2e-test"},
    )

    @run.tool(name="get_weather", description="Return a mock weather report for a city.")
    def get_weather(city: str) -> dict[str, str]:
        return {"city": city, "forecast": "sunny", "temperature_c": "23"}

    model_name = os.getenv("TRACE_AGENT_TEST_MODEL", "qwen/qwen3-vl-8b")
    result = run.create_model_turn(
        [{"role": "user", "content": "Check the weather in Madrid and summarize it briefly."}],
        model=model_name,
    )
    run.finish(result.assistant_message)
    print("Run completed successfully!")
    print(f"Run ID: {run.run_id}")
    print(f"Assistant message: {result.assistant_message}")


if __name__ == "__main__":
    main()
