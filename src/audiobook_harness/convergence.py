"""Durable, evidence-bounded convergence records for local production."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _identity(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()


def iteration_path(project: Path) -> Path:
    return project / "production/convergence-iterations.jsonl"


def append_iteration(project: Path, record: dict[str, Any]) -> dict[str, Any]:
    """Append one compact iteration receipt without manuscript or audio data."""
    row = {
        "version": 1,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        **record,
    }
    row["iteration_identity_sha256"] = _identity(
        {key: value for key, value in row.items() if key != "recorded_at"}
    )
    path = iteration_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return row


def read_iterations(project: Path) -> list[dict[str, Any]]:
    path = iteration_path(project)
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def convergence_summary(project: Path) -> dict[str, Any]:
    """Summarize objective progress and the current automatic stop reason."""
    rows = read_iterations(project)
    latest = rows[-1] if rows else {}
    findings = [int(row.get("findings", 0) or 0) for row in rows]
    scores = [
        row.get("objective_score")
        for row in rows
        if row.get("objective_score") is not None
    ]
    plateau = bool(
        len(rows) >= 2
        and rows[-1].get("evidence_fingerprint") == rows[-2].get("evidence_fingerprint")
    )
    return {
        "version": 1,
        "iterations": len(rows),
        "findings_trajectory": findings,
        "objective_scores": scores,
        "latest": latest,
        "plateau": plateau,
        "automatic_work_active": latest.get("state") == "automatic_work",
        "stop_reason": latest.get("stop_reason"),
    }
