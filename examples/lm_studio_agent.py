from __future__ import annotations

import os

from dotenv import load_dotenv

from visor_agentico.sdk import VisorClient


def main() -> None:
    load_dotenv()
    proxy_url = os.getenv("VISOR_PROXY_URL", "http://127.0.0.1:8000")
    model_name = os.getenv("VISOR_TEST_MODEL", "local-model")
    timeout = float(os.getenv("VISOR_PROXY_TIMEOUT", "60"))
    client = VisorClient(base_url=proxy_url, timeout=timeout)
    run = client.start_run(
        agent_name="lmstudio-local-agent",
        goal="Use a local OpenAI-compatible model to call a tool and summarize the result.",
        metadata={"environment": "lm-studio-demo"},
    )

    @run.tool(name="get_weather", description="Return a mock weather report for a city.")
    def get_weather(city: str) -> dict[str, str]:
        return {"city": city, "forecast": "sunny", "temperature_c": "23"}

    result = run.create_model_turn(
        [
            {
                "role": "system",
                "content": "Always call the available tool before answering, even if the answer seems obvious.",
            },
            {"role": "user", "content": "Check the weather in Madrid and summarize it briefly."},
        ],
        model=model_name,
    )
    run.finish(result.assistant_message)


if __name__ == "__main__":
    main()
