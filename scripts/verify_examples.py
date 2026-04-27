"""Verify that all examples execute without errors using a mocked provider."""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent


def start_mock_backend(port: int = 9999) -> subprocess.Popen:
    """Start backend with a mock provider by injecting it via a small wrapper module."""
    wrapper_code = '''
import sys
sys.path.insert(0, r"""{root}""")
from visor_agentico.main import create_app
from visor_agentico.config import Settings
from visor_agentico.services.provider import BaseProviderAdapter, ProviderTurnRequest, ProviderTurnResponse, ProviderToolCall

class MockProvider(BaseProviderAdapter):
    provider_name = "openai"
    def generate_turn(self, request):
        tool_messages = [m for m in request.messages if m.get("role") == "tool"]
        if len(tool_messages) == 0:
            return ProviderTurnResponse(
                tool_calls=[ProviderToolCall(id="call-mock-1", name="get_weather", arguments={"city": "Madrid"}, step_id="step-mock-1")],
                summary="Mock provider requested get_weather.",
                metadata={"usage": {"prompt_tokens": 42, "completion_tokens": 15, "total_tokens": 57}},
            )
        return ProviderTurnResponse(
            assistant_message={"role": "assistant", "content": "The weather in Madrid is sunny, 23C."},
            summary="Mock provider answered.",
            metadata={"usage": {"prompt_tokens": 60, "completion_tokens": 20, "total_tokens": 80}},
        )

settings = Settings(openai_api_key="mock-key")
app = create_app(settings)
app.state.provider_registry = {{"openai": MockProvider()}}

import uvicorn
uvicorn.run(app, host="127.0.0.1", port={port}, log_level="warning")
'''.format(root=str(PROJECT_ROOT), port=port)

    proc = subprocess.Popen(
        [sys.executable, "-c", wrapper_code],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    time.sleep(3)
    return proc


def run_example(name: str, env: dict[str, str]) -> bool:
    print(f"\n=== Verifying {name} ===")
    example_path = PROJECT_ROOT / "examples" / name
    if not example_path.exists():
        print(f"SKIP: {example_path} not found")
        return True

    cmd = [sys.executable, str(example_path)]
    try:
        result = subprocess.run(
            cmd,
            env={**os.environ, **env},
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            print(f"PASS: {name}")
            return True
        else:
            print(f"FAIL: {name}")
            print("STDOUT:", result.stdout[-500:] if len(result.stdout) > 500 else result.stdout)
            print("STDERR:", result.stderr[-500:] if len(result.stderr) > 500 else result.stderr)
            return False
    except subprocess.TimeoutExpired:
        print(f"FAIL: {name} timed out")
        return False
    except Exception as exc:
        print(f"FAIL: {name} raised {exc}")
        return False


def main() -> int:
    proc = start_mock_backend(port=9999)
    try:
        base_env = {
            "VISOR_PROXY_URL": "http://127.0.0.1:9999",
            "VISOR_OPENAI_BASE_URL": "",
            "VISOR_OPENAI_API_KEY": "mock",
        }

        results = []

        # sample_agent.py
        results.append(run_example("sample_agent.py", base_env))

        # lm_studio_agent.py
        lm_env = {**base_env, "VISOR_TEST_MODEL": "mock-model"}
        results.append(run_example("lm_studio_agent.py", lm_env))

        # coding_agent_debugger_demo.py scenarios
        for scenario in ["correct_edit", "wrong_file", "retry_without_adaptation", "same_tools_different_artifact"]:
            print(f"\n=== Verifying coding_agent_debugger_demo.py --scenario {scenario} ===")
            cmd = [sys.executable, str(PROJECT_ROOT / "examples" / "coding_agent_debugger_demo.py"), "--scenario", scenario]
            try:
                result = subprocess.run(
                    cmd,
                    env={**os.environ, **base_env},
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                if result.returncode == 0:
                    print(f"PASS: coding_agent_debugger_demo.py --scenario {scenario}")
                    results.append(True)
                else:
                    print(f"FAIL: coding_agent_debugger_demo.py --scenario {scenario}")
                    print("STDERR:", result.stderr[-300:] if len(result.stderr) > 300 else result.stderr)
                    results.append(False)
            except Exception as exc:
                print(f"FAIL: coding_agent_debugger_demo.py --scenario {scenario} raised {exc}")
                results.append(False)

        passed = sum(results)
        total = len(results)
        print(f"\n{'='*40}")
        print(f"Results: {passed}/{total} passed")
        return 0 if passed == total else 1
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    sys.exit(main())
