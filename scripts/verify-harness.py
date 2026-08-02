#!/usr/bin/env python3
"""Run the deterministic local verification contract and emit JSON evidence."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


PROFILE_TESTS: dict[str, tuple[str, ...]] = {
    "integrity": (
        "tests/test_phase_engine.py",
        "tests/test_run_journal.py",
        "tests/test_stage.py",
        "tests/test_transactional_repair.py",
    ),
    "filesystem": (
        "tests/test_project.py",
        "tests/test_project_lock.py",
        "tests/test_run_journal.py",
        "tests/test_stage.py",
    ),
    "quality": (
        "tests/test_encoded_quality.py",
        "tests/test_gate_results.py",
        "tests/test_quality.py",
        "tests/test_quality_policy.py",
        "tests/test_review_identity.py",
    ),
    "supply-chain": (
        "tests/test_fixture_script.py",
        "tests/test_versioning.py",
    ),
    "operations": (
        "tests/test_cli_errors.py",
        "tests/test_project_lock.py",
        "tests/test_review_center.py",
    ),
}


def verification_commands(
    root: Path, python: Path, profile: str
) -> list[tuple[str, list[str], bool]]:
    """Return the local, deterministic checks required for one closure area."""
    pytest_command = [str(python), "-m", "pytest", "-q"]
    if os.environ.get("AUDIOBOOK_HARNESS_VERIFY_TEST"):
        # The verification-contract test invokes this script.  Keep that child
        # check intentionally narrow so a full-suite invocation cannot recurse
        # into another full-suite invocation through the contract test itself.
        pytest_command.append("tests/test_phase_engine.py")
    elif profile != "release":
        pytest_command.extend(PROFILE_TESTS[profile])
    commands = [
        ("pytest", pytest_command, True),
        ("ruff", [str(python), "-m", "ruff", "check", "src", "tests"], True),
        (
            "format",
            [str(python), "-m", "ruff", "format", "--check", "src", "tests"],
            False,
        ),
    ]
    if profile in {"supply-chain", "release"}:
        uv = shutil.which("uv")
        if uv:
            commands.append(("lock", [uv, "lock", "--check"], False))
    return commands


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path)
    parser.add_argument(
        "--profile",
        choices=(*PROFILE_TESTS, "release"),
        default="release",
        help="Run the local verification set associated with an issue-closure area.",
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    python = Path(sys.executable)
    commands = verification_commands(root, python, args.profile)
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
        "profile": args.profile,
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
