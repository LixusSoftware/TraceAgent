from __future__ import annotations

import os

from dotenv import load_dotenv

from visor_agentico.sdk import VisorClient


def main() -> None:
    load_dotenv()
    client = VisorClient(base_url=os.getenv("VISOR_PROXY_URL", "http://127.0.0.1:8000"))
    run = client.start_run(
        agent_name="sample-research-agent",
        goal="Summarize the weather workflow and capture the tool trace.",
        metadata={"environment": "local-demo"},
    )

    @run.tool(name="get_weather", description="Return a mock weather report for a city.")
    def get_weather(city: str) -> dict[str, str]:
        return {"city": city, "forecast": "sunny", "temperature_c": "23"}

    result = run.create_model_turn(
        [{"role": "user", "content": "Check the weather in Madrid and summarize it briefly."}],
        model="gpt-4o-mini",
    )
    run.finish(result.assistant_message)


if __name__ == "__main__":
    main()
