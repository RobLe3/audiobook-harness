import json
import os
import subprocess
import sys
from pathlib import Path


def test_local_verification_contract_emits_machine_readable_report(tmp_path: Path):
    root = Path(__file__).parents[1]
    report = tmp_path / "verification.json"
    result = subprocess.run(
        [sys.executable, "scripts/verify-harness.py", "--report", str(report)],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "AUDIOBOOK_HARNESS_VERIFY_TEST": "1"},
    )
    value = json.loads(report.read_text(encoding="utf-8"))
    assert result.returncode == 0
    assert value["offline"] is True
    assert {"pytest", "ruff", "format"}.issubset(
        {row["name"] for row in value["checks"]}
    )
    assert all(row["ok"] for row in value["checks"] if row["required"])
