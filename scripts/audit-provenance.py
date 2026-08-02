#!/usr/bin/env python3
"""Emit offline, deterministic dependency/model/binary provenance evidence."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    lock = root / "uv.lock"
    models = root / "models.lock.json"
    required = {
        "uv.lock": lock,
        "models.lock.json": models,
        "pyproject.toml": root / "pyproject.toml",
    }
    missing = [name for name, path in required.items() if not path.is_file()]
    payload = {
        "version": 1,
        "offline": True,
        "canonical_python_lock": "uv.lock",
        "files": {
            name: digest(path) for name, path in required.items() if path.is_file()
        },
        "models": json.loads(models.read_text(encoding="utf-8")).get("models", [])
        if models.is_file()
        else [],
        "binaries": {
            name: shutil.which(name)
            for name in ("ffmpeg", "ffprobe", "mfa", "espeak-ng", "espeak")
        },
        "missing": missing,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if not missing else 1


if __name__ == "__main__":
    raise SystemExit(main())
