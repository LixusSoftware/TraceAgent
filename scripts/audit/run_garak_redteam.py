from __future__ import annotations

import argparse
import os
import sys

from _common import REPORTS_ROOT, run_command, utc_now_iso, write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Garak red-team probes against configured model endpoint.")
    parser.add_argument("--model-type", default="openai", help="Garak model type.")
    parser.add_argument("--model-name", default=os.getenv("VISOR_TEST_MODEL", "gpt-4.1-mini"), help="Model name.")
    parser.add_argument("--probes", default="promptinject,jailbreak", help="Comma-separated probe set.")
    return parser.parse_args()


def _candidate_commands(args: argparse.Namespace, report_prefix: str) -> list[list[str]]:
    return [
        [
            sys.executable,
            "-m",
            "garak",
            "--model_type",
            args.model_type,
            "--model_name",
            args.model_name,
            "--probes",
            args.probes,
            "--report_prefix",
            report_prefix,
        ],
        [
            sys.executable,
            "-m",
            "garak",
            "--model-type",
            args.model_type,
            "--model-name",
            args.model_name,
            "--probes",
            args.probes,
            "--report-prefix",
            report_prefix,
        ],
    ]


def main() -> int:
    args = parse_args()
    garak_dir = REPORTS_ROOT / "garak"
    garak_dir.mkdir(parents=True, exist_ok=True)
    report_prefix = str(garak_dir / "garak")

    env_info = {
        "VISOR_OPENAI_BASE_URL": os.getenv("VISOR_OPENAI_BASE_URL"),
        "VISOR_TEST_MODEL": os.getenv("VISOR_TEST_MODEL"),
        "OPENAI_API_KEY_present": bool(os.getenv("OPENAI_API_KEY") or os.getenv("VISOR_OPENAI_API_KEY")),
    }

    last_result = None
    selected_command: list[str] | None = None
    for command in _candidate_commands(args, report_prefix):
        result = run_command(command)
        last_result = result
        selected_command = command
        if "unrecognized arguments" not in (result.stderr or "").lower():
            break

    assert last_result is not None and selected_command is not None

    summary = {
        "created_at": utc_now_iso(),
        "tool": "garak",
        "command": selected_command,
        "returncode": last_result.returncode,
        "stdout": last_result.stdout[-8000:],
        "stderr": last_result.stderr[-8000:],
        "report_prefix": report_prefix,
        "env": env_info,
    }
    write_json(garak_dir / "summary.json", summary)

    print("Garak summary written to", garak_dir / "summary.json")
    return 0 if last_result.returncode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
