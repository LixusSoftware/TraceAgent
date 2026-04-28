from __future__ import annotations

import argparse
import os

from trace_agent_sdk import TraceAgentClient


def build_client() -> TraceAgentClient:
    return TraceAgentClient(
        base_url=os.getenv("TRACE_AGENT_PROXY_URL", "http://127.0.0.1:8000"),
        timeout=float(os.getenv("TRACE_AGENT_PROXY_TIMEOUT", "30")),
    )


def scenario_correct_edit(run) -> None:
    run.record_command(["python", "-m", "pytest", "-q"], cwd="C:/repo", output={"tests": "passed"}, exit_code=0, duration_ms=380)
    run.record_file_read("src/app.py", content="print('before')\n")
    run.record_file_write("src/app.py", before_content="print('before')\n", after_content="print('after')\n")
    run.record_patch("src/app.py", before_content="print('before')\n", after_content="print('after')\n")
    run.record_artifact("report", "patch-report", "Patched src/app.py and tests passed.", content={"status": "ok"})
    run.finish({"summary": "Patched src/app.py and tests passed."})


def scenario_wrong_file(run) -> None:
    run.record_command(
        ["python", "-m", "pytest", "-q"],
        cwd="C:/repo",
        status="failed",
        error_code="CommandError",
        error_summary="pytest failed after editing the wrong file",
        exit_code=1,
        duration_ms=510,
    )
    run.record_file_read("src/app.py", content="print('before')\n")
    run.record_file_write("src/unused.py", before_content="print('noop')\n", after_content="print('changed')\n")
    run.record_patch("src/unused.py", before_content="print('noop')\n", after_content="print('changed')\n")
    run.record_artifact("report", "patch-report", "Patched src/unused.py and tests still failed.", content={"status": "failed"})
    run.fail("wrong_file", "The agent edited the wrong file and did not recover.")


def scenario_retry_without_adaptation(run) -> None:
    run.record_command(
        ["python", "-m", "pytest", "-q"],
        cwd="C:/repo",
        status="failed",
        error_code="CommandError",
        error_summary="pytest failed on first attempt",
        exit_code=1,
        duration_ms=340,
        step_id="pytest-attempt",
    )
    run.record_command(
        ["python", "-m", "pytest", "-q"],
        cwd="C:/repo",
        status="failed",
        error_code="CommandError",
        error_summary="pytest failed again with the same command",
        exit_code=1,
        duration_ms=335,
        step_id="pytest-attempt-2",
    )
    run.record_file_write("src/app.py", before_content="print('before')\n", after_content="print('before')\n")
    run.record_artifact("report", "patch-report", "Retried the same command without changing strategy.", content={"status": "retry"})
    run.fail("retry_without_adaptation", "The agent repeated the same command and stayed stuck.")


def scenario_same_tools_different_artifact(run) -> None:
    run.record_command(["python", "-m", "pytest", "-q"], cwd="C:/repo", output={"tests": "passed"}, exit_code=0, duration_ms=380)
    run.record_file_read("src/app.py", content="print('before')\n")
    run.record_file_write("src/app.py", before_content="print('before')\n", after_content="print('after')\n")
    run.record_artifact("report", "patch-report", "Patch report with a different final artifact.", content={"status": "alt"})
    run.finish({"summary": "Patch report with a different final artifact."})


SCENARIOS = {
    "correct_edit": scenario_correct_edit,
    "wrong_file": scenario_wrong_file,
    "retry_without_adaptation": scenario_retry_without_adaptation,
    "same_tools_different_artifact": scenario_same_tools_different_artifact,
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Record coding-agent runs with side effects for the debugger UI.")
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), default="correct_edit")
    args = parser.parse_args()

    client = build_client()
    run = client.start_run(
        "coding-agent-demo",
        f"Execute coding agent scenario: {args.scenario}",
        {"scenario": args.scenario, "suite": "coding-demo"},
    )
    SCENARIOS[args.scenario](run)
    print(f"Recorded run {run.run_id} for scenario {args.scenario}")


if __name__ == "__main__":
    main()
