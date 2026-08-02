import subprocess
import sys
from pathlib import Path


def test_model_free_fixture_script_runs_from_checkout():
    root = Path(__file__).parents[1]
    result = subprocess.run(
        [sys.executable, "scripts/run-fixture.py"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "fixture deterministic core passed" in result.stdout
