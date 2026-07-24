"""Content-addressed local ASR evidence cache.

The cache is an acceleration layer, not an acceptance shortcut.  Each entry is
bound to the exact audio bytes, recognizer checkpoint, complete decode profile,
and device used by the release verifier.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any


CACHE_VERSION = 1


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def evidence_key(
    *, audio_sha256: str, model_sha256: str, decode: dict[str, object], device: str
) -> str:
    return _canonical_sha256(
        {
            "audio_sha256": audio_sha256,
            "model_sha256": model_sha256,
            "decode": decode,
            "device": device,
        }
    )


def load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"version": CACHE_VERSION, "entries": {}}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": CACHE_VERSION, "entries": {}}
    if value.get("version") != CACHE_VERSION or not isinstance(value.get("entries"), dict):
        return {"version": CACHE_VERSION, "entries": {}}
    return value


def save(path: Path, cache: dict[str, Any]) -> None:
    """Publish cache updates atomically so an interrupted check cannot poison it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(cache, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)
