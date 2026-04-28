from __future__ import annotations

import os
import sys
from pathlib import Path

from trace_agent_sdk import TraceAgentClient


def build_client() -> TraceAgentClient:
    return TraceAgentClient(base_url=os.getenv("TRACE_AGENT_PROXY_URL", "http://127.0.0.1:8010"))


def reset_workspace(workspace: Path) -> tuple[Path, Path]:
    src_dir = workspace / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    app_path = src_dir / "app.py"
    unused_path = src_dir / "unused.py"
    app_path.write_text("print('before')\n", encoding="utf-8")
    unused_path.write_text("print('noop')\n", encoding="utf-8")
    return app_path, unused_path


def seed_correct_edit(client: TraceAgentClient, workspace: Path, *, clone: bool = False) -> None:
    app_path, _ = reset_workspace(workspace)
    scenario = "correct_edit_clone" if clone else "correct_edit"
    goal = "Patch app.py and run tests (clone)" if clone else "Patch app.py and run tests"
    run = client.start_run(
        "coding-agent-demo",
        goal,
        {"scenario": scenario, "suite": "e2e"},
    )
    run.files.read_text(str(app_path))
    run.files.patch_text(str(app_path), "print('after')\n")
    run.commands.run([sys.executable, "-c", "print('1 passed')"], cwd=str(workspace), check=True)
    run.artifacts.capture("report", "patch-report", "Patched src/app.py and tests passed.", content={"status": "ok"})
    run.finish({"summary": "Patched src/app.py and tests passed."})


def seed_wrong_file(client: TraceAgentClient, workspace: Path) -> None:
    app_path, unused_path = reset_workspace(workspace)
    run = client.start_run(
        "coding-agent-demo",
        "Patch app.py and run tests (wrong file)",
        {"scenario": "wrong_file", "suite": "e2e"},
    )
    run.files.read_text(str(app_path))
    run.files.patch_text(str(unused_path), "print('changed')\n")
    run.commands.run(
        [sys.executable, "-c", "import sys; sys.stderr.write('1 failed\\n'); sys.exit(1)"],
        cwd=str(workspace),
        check=False,
    )
    run.artifacts.capture("report", "patch-report", "Patched src/unused.py and tests still failed.", content={"scenario": "wrong_file"})
    run.fail("wrong_file", "The agent edited the wrong file and did not recover.")


def seed_retry_without_adaptation(client: TraceAgentClient, workspace: Path) -> None:
    app_path, _ = reset_workspace(workspace)
    run = client.start_run(
        "coding-agent-demo",
        "Patch app.py and run tests (retry)",
        {"scenario": "retry_without_adaptation", "suite": "e2e"},
    )
    run.files.read_text(str(app_path))
    run.commands.run(
        [sys.executable, "-c", "import sys; sys.stderr.write('retry failed\\n'); sys.exit(1)"],
        cwd=str(workspace),
        check=False,
    )
    run.commands.run(
        [sys.executable, "-c", "import sys; sys.stderr.write('retry failed\\n'); sys.exit(1)"],
        cwd=str(workspace),
        check=False,
    )
    run.files.write_text(str(app_path), "print('before')\n")
    run.artifacts.capture("report", "patch-report", "Retried the same command without changing strategy.", content={"scenario": "retry_without_adaptation"})
    run.fail("retry_without_adaptation", "The agent repeated the same command and stayed stuck.")


def seed_same_tools_different_artifact(client: TraceAgentClient, workspace: Path) -> None:
    app_path, _ = reset_workspace(workspace)
    run = client.start_run(
        "coding-agent-demo",
        "Patch app.py and run tests (artifact)",
        {"scenario": "same_tools_different_artifact", "suite": "e2e"},
    )
    run.files.read_text(str(app_path))
    run.files.patch_text(str(app_path), "print('after')\n")
    run.commands.run([sys.executable, "-c", "print('1 passed')"], cwd=str(workspace), check=True)
    run.artifacts.capture("report", "patch-report", "Patch report with a different final artifact.", content={"scenario": "same_tools_different_artifact"})
    run.finish({"summary": "Patch report with a different final artifact."})


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    state_dir = root / "frontend" / ".e2e"
    workspace = state_dir / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    client = build_client()
    seed_correct_edit(client, workspace)
    seed_correct_edit(client, workspace, clone=True)
    seed_wrong_file(client, workspace)
    seed_retry_without_adaptation(client, workspace)
    seed_same_tools_different_artifact(client, workspace)
    print("Seeded deterministic E2E runs.")


if __name__ == "__main__":
    main()
