"""
Rich demo agent for LM Studio.

Generates a run with diverse events (model turns, tools, commands,
file activity, patches), explicit artifacts, and decisions derived
automatically by the backend when the run is finished.

Usage:
    VISOR_PROXY_URL=http://127.0.0.1:8000 \
    VISOR_TEST_MODEL=qwen/qwen3-vl-8b \
    python examples/rich_demo_agent.py
"""
from __future__ import annotations

import os
import time

from dotenv import load_dotenv

from visor_agentico.sdk import VisorClient


def main() -> None:
    load_dotenv()
    proxy_url = os.getenv("VISOR_PROXY_URL", "http://127.0.0.1:8000")
    model_name = os.getenv("VISOR_TEST_MODEL", "qwen/qwen3-vl-8b")
    timeout = float(os.getenv("VISOR_PROXY_TIMEOUT", "120"))

    client = VisorClient(base_url=proxy_url, timeout=timeout)
    run = client.start_run(
        agent_name="rich-demo-agent",
        goal="Build a weather summary report, fix a config file, and capture all traces.",
        metadata={"environment": "lm-studio-rich-demo", "demo_version": "1.0"},
    )

    # ── Tool 1: always succeeds ───────────────────────────────
    @run.tool(
        name="get_weather",
        description="Return a mock weather report for a city.",
    )
    def get_weather(city: str) -> dict[str, str]:
        return {
            "city": city,
            "forecast": "sunny",
            "temperature_c": "23",
            "humidity": "45%",
        }

    # ── Tool 2: fails once, then succeeds on retry ────────────
    _fail_counter = {"get_forecast_risk": 0}

    @run.tool(
        name="get_forecast_risk",
        description="Return a risk assessment for the forecast.",
    )
    def get_forecast_risk(city: str) -> dict[str, str]:
        _fail_counter["get_forecast_risk"] += 1
        if _fail_counter["get_forecast_risk"] == 1:
            raise RuntimeError("Forecast service temporarily unavailable")
        return {"city": city, "risk_level": "low", "advisory": "No action needed"}

    # ── Turn 1: model call that triggers tools ────────────────
    print("[1/5] Creating model turn with tools...")
    result = run.create_model_turn(
        [
            {
                "role": "system",
                "content": (
                    "You are a helpful assistant. "
                    "Use the available tools before answering. "
                    "If a tool fails, retry it once."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Check the weather in Madrid, assess the forecast risk, "
                    "and give me a one-line summary."
                ),
            },
        ],
        model=model_name,
        provider="lmstudio",
    )
    print(f"    Assistant: {result.assistant_message.get('content', '')[:80]}...")

    # ── Manual observations: commands ─────────────────────────
    print("[2/5] Recording command events...")
    run.record_command(
        ["git", "clone", "https://github.com/example/weather-app.git"],
        status="succeeded",
        cwd="/workspace",
        output="Cloning into 'weather-app'... done.",
        duration_ms=1200,
    )
    run.record_command(
        ["pytest", "tests/"],
        status="failed",
        cwd="/workspace/weather-app",
        error_code="TestFailure",
        error_summary="3 tests failed in test_forecast.py",
        stdout_summary="...F.F.F",
        stderr_summary="AssertionError: expected 23 got None",
        duration_ms=4500,
    )
    run.record_command(
        ["pytest", "tests/", "-k", "forecast"],
        status="succeeded",
        cwd="/workspace/weather-app",
        output="1 passed, 2 skipped.",
        duration_ms=2100,
    )

    # ── Manual observations: file activity ────────────────────
    print("[3/5] Recording file events...")
    run.record_file_read(
        "/workspace/weather-app/config.yaml",
        content="api_key: old-key-123\nendpoint: http://api.example.com\n",
        size_bytes=58,
    )
    run.record_file_write(
        "/workspace/weather-app/config.yaml",
        change_type="update",
        before_content="api_key: old-key-123\nendpoint: http://api.example.com\n",
        after_content="api_key: new-key-456\nendpoint: https://api.example.com\ntimeout: 30\n",
    )
    run.record_patch(
        "/workspace/weather-app/src/formatter.py",
        diff_text="@@ -10,3 +10,4 @@ def format_temp(c):\n     return f'{c}°C'\n+    # Added humidity suffix\n",
        before_content="def format_temp(c):\n    return f'{c}°C'\n",
        after_content="def format_temp(c):\n    return f'{c}°C'\n    # Added humidity suffix\n",
    )

    # ── Artifacts ─────────────────────────────────────────────
    print("[4/5] Creating artifacts...")
    run.artifacts.capture(
        kind="report",
        label="Weather Summary",
        summary="One-page weather summary for Madrid including risk assessment.",
        content={"city": "Madrid", "temp_c": 23, "risk": "low"},
        metadata={"format": "json", "pages": 1},
    )
    run.artifacts.capture(
        kind="config",
        label="Updated Config",
        summary="Updated config.yaml with new API key and HTTPS endpoint.",
        content="api_key: new-key-456\nendpoint: https://api.example.com\n",
        metadata={"format": "yaml", "lines": 3},
    )
    run.artifacts.capture(
        kind="patch",
        label="Formatter Patch",
        summary="Diff patch for src/formatter.py adding humidity suffix comment.",
        content="@@ -10,3 +10,4 @@ ...",
        metadata={"format": "diff", "files_changed": 1},
    )

    # ── Finish run (triggers derive_explanation → decisions) ──
    print("[5/5] Finishing run...")
    final_text = result.assistant_message.get("content", "")
    if not final_text:
        final_text = "Weather in Madrid: 23°C, sunny, low risk."
    run.finish(final_text)
    print("Done! Open http://localhost:5173 to inspect the run in the UI.")


if __name__ == "__main__":
    main()
