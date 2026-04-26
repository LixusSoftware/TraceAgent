from __future__ import annotations

import sys
from pathlib import Path

from _common import REPORTS_ROOT, run_command, utc_now_iso, write_json


SCRIPT_SEQUENCE = [
    "scripts/audit/run_security_scans.py",
    "scripts/audit/run_deepeval_suite.py",
    "scripts/audit/run_promptfoo_regression.py",
    "scripts/audit/run_garak_redteam.py",
    "scripts/audit/run_drift_report.py",
]


def main() -> int:
    REPORTS_ROOT.mkdir(parents=True, exist_ok=True)

    results = []
    overall_status = "ok"
    for relative_script in SCRIPT_SEQUENCE:
        command = [sys.executable, relative_script]
        result = run_command(command)
        status = "ok" if result.returncode == 0 else "failed"
        if status != "ok":
            overall_status = "failed"
        results.append(
            {
                "script": relative_script,
                "command": command,
                "returncode": result.returncode,
                "status": status,
                "stdout": result.stdout[-6000:],
                "stderr": result.stderr[-6000:],
            }
        )

    summary = {
        "created_at": utc_now_iso(),
        "status": overall_status,
        "results": results,
    }
    write_json(REPORTS_ROOT / "audit-all-summary.json", summary)

    print("Audit all summary written to", REPORTS_ROOT / "audit-all-summary.json")
    return 0 if overall_status == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
