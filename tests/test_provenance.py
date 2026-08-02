import json
import subprocess
import sys
from pathlib import Path


def test_offline_provenance_audit_has_one_canonical_lock_and_model_records():
    root = Path(__file__).parents[1]
    result = subprocess.run(
        [sys.executable, "scripts/audit-provenance.py"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["offline"] is True
    assert report["canonical_python_lock"] == "uv.lock"
    assert {"uv.lock", "models.lock.json", "pyproject.toml"} <= set(report["files"])
    assert all(
        row.get("sha256") and row.get("license_note") for row in report["models"]
    )
