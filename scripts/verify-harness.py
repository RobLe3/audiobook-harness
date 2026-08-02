#!/usr/bin/env python3
"""Run the deterministic local verification contract and emit JSON evidence."""

from __future__ import annotations

import argparse
import json
import platform
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    python = Path(sys.executable)
    pytest_command = [str(python), "-m", "pytest", "-q"]
    if os.environ.get("AUDIOBOOK_HARNESS_VERIFY_TEST"):
        pytest_command.append("tests/test_phase_engine.py")
    commands = [
        ("pytest", pytest_command, True),
        ("ruff", [str(python), "-m", "ruff", "check", "src", "tests"], True),
        (
            "format",
            [str(python), "-m", "ruff", "format", "--check", "src", "tests"],
            False,
        ),
    ]
    uv = shutil.which("uv")
    if uv:
        commands.append(("lock", [uv, "lock", "--check"], False))
    checks = []
    for name, command, required in commands:
        result = subprocess.run(command, cwd=root, capture_output=True, text=True)
        checks.append(
            {
                "name": name,
                "required": required,
                "ok": result.returncode == 0,
                "returncode": result.returncode,
                "command": command,
                "stdout": result.stdout[-4000:],
                "stderr": result.stderr[-4000:],
            }
        )
    report = {
        "version": 1,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(),
        "root": str(root),
        "offline": True,
        "checks": checks,
        "ok": all(row["ok"] for row in checks if row["required"]),
    }
    encoded = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
