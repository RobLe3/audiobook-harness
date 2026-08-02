#!/usr/bin/env python3
"""Run the redistributable, model-free onboarding fixture."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    template = root / "templates/project"
    with tempfile.TemporaryDirectory(prefix="audiobook-harness-fixture-") as directory:
        project = Path(directory) / "fixture"
        shutil.copytree(template, project)
        result = subprocess.run(
            [sys.executable, "-m", "audiobook_harness.cli", "analyze", str(project)],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            print(result.stderr, file=sys.stderr, end="")
            return result.returncode
        report = json.loads(
            (project / "production/analysis.json").read_text(encoding="utf-8")
        )
        assert report["project"] == "Untitled audiobook"
        assert report["chapters"][0]["units"]
        print("fixture analysis passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
