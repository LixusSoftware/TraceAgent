from __future__ import annotations

import argparse
import sys
from pathlib import Path

from _common import REPORTS_ROOT, run_command, utc_now_iso, write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run semgrep and bandit scans for agent-generated code auditing.")
    parser.add_argument(
        "--targets",
        nargs="+",
        default=["trace_agent", "scripts", "tests"],
        help="Directories to scan.",
    )
    parser.add_argument("--semgrep-config", default="auto", help="Semgrep ruleset configuration.")
    return parser.parse_args()


def run_semgrep(targets: list[str], semgrep_config: str, output_path: Path) -> dict:
    candidate_commands = [
        ["semgrep", "scan", "--config", semgrep_config, "--json", "--output", str(output_path), *targets],
        [sys.executable, "-m", "semgrep", "scan", "--config", semgrep_config, "--json", "--output", str(output_path), *targets],
    ]

    for command in candidate_commands:
        result = run_command(command)
        if result.returncode != 127:
            return {
                "tool": "semgrep",
                "command": command,
                "returncode": result.returncode,
                "stdout": result.stdout[-4000:],
                "stderr": result.stderr[-4000:],
                "output": str(output_path),
            }

    return {
        "tool": "semgrep",
        "command": candidate_commands[-1],
        "returncode": 127,
        "stdout": "",
        "stderr": "semgrep executable not found",
        "output": str(output_path),
    }


def run_bandit(targets: list[str], output_path: Path) -> dict:
    command = [sys.executable, "-m", "bandit", "-r", *targets, "-f", "json", "-o", str(output_path)]
    result = run_command(command)
    return {
        "tool": "bandit",
        "command": command,
        "returncode": result.returncode,
        "stdout": result.stdout[-4000:],
        "stderr": result.stderr[-4000:],
        "output": str(output_path),
    }


def main() -> int:
    args = parse_args()
    security_dir = REPORTS_ROOT / "security"
    security_dir.mkdir(parents=True, exist_ok=True)

    semgrep_out = security_dir / "semgrep.json"
    bandit_out = security_dir / "bandit.json"

    semgrep = run_semgrep(args.targets, args.semgrep_config, semgrep_out)
    bandit = run_bandit(args.targets, bandit_out)

    summary = {
        "created_at": utc_now_iso(),
        "targets": args.targets,
        "tools": [semgrep, bandit],
        "status": "ok" if semgrep["returncode"] in {0, 1} and bandit["returncode"] in {0, 1} else "failed",
    }
    write_json(security_dir / "summary.json", summary)

    print("Security scan summary written to", security_dir / "summary.json")
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
