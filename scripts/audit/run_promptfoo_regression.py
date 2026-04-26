from __future__ import annotations

import argparse
from pathlib import Path

from _common import REPORTS_ROOT, run_command, utc_now_iso, write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Promptfoo regression suite.")
    parser.add_argument(
        "--config",
        default="audit/promptfoo/promptfooconfig.yaml",
        help="Promptfoo config file path.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    promptfoo_dir = REPORTS_ROOT / "promptfoo"
    promptfoo_dir.mkdir(parents=True, exist_ok=True)
    output_file = promptfoo_dir / "result.json"

    command = [
        "npx",
        "-y",
        "promptfoo@latest",
        "eval",
        "-c",
        args.config,
        "--output",
        str(output_file),
    ]
    result = run_command(command)

    summary = {
        "created_at": utc_now_iso(),
        "tool": "promptfoo",
        "command": command,
        "returncode": result.returncode,
        "stdout": result.stdout[-8000:],
        "stderr": result.stderr[-8000:],
        "output": str(output_file),
    }
    write_json(promptfoo_dir / "summary.json", summary)

    print("Promptfoo summary written to", promptfoo_dir / "summary.json")
    return 0 if result.returncode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
