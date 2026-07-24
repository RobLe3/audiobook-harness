"""Durable event and receipt primitives for a single-writer production runner."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from .project import write_json


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def append_event(path: Path, event: dict[str, Any]) -> None:
    """Atomically durable JSONL append for child-to-parent progress events."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def write_stage_receipt(
    path: Path, *, run_id: str, chapter_id: str, quality_report: Path, media: list[Path]
) -> dict[str, Any]:
    """Bind a packaged chapter to its verified report and exact output bytes."""
    receipt = {
        "version": 1,
        "run_id": run_id,
        "chapter_id": chapter_id,
        "quality_report_sha256": sha256(quality_report),
        "media": [
            {"name": item.name, "sha256": sha256(item), "bytes": item.stat().st_size}
            for item in media
        ],
    }
    write_json(path, receipt)
    return receipt


def receipt_is_valid(
    receipt: dict[str, Any], *, run_id: str, chapter_id: str, stage: Path,
    quality_report: Path, expected_names: set[str],
) -> bool:
    if receipt.get("run_id") != run_id or receipt.get("chapter_id") != chapter_id:
        return False
    if receipt.get("quality_report_sha256") != sha256(quality_report):
        return False
    rows = receipt.get("media", [])
    if not isinstance(rows, list) or {str(row.get("name")) for row in rows} != expected_names:
        return False
    return all(
        (stage / str(row.get("name"))).is_file()
        and (stage / str(row.get("name"))).stat().st_size == int(row.get("bytes", -1))
        and sha256(stage / str(row.get("name"))) == row.get("sha256")
        for row in rows
    )
