from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .project import project_paths, write_json


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_run_status(
    project: Path, *, state: str, phase: str, **changes: Any
) -> dict[str, Any]:
    paths = project_paths(project)
    path = paths["production"] / "run-status.json"
    current = (
        json.loads(path.read_text()) if path.exists() else {"version": 1, "steps": []}
    )
    current.update(changes)
    current.update({"state": state, "phase": phase, "updated_at": _now()})
    write_json(path, current)
    render_status(project, current)
    return current


def render_status(project: Path, status: dict[str, Any] | None = None) -> Path:
    paths = project_paths(project)
    status_path = paths["production"] / "run-status.json"
    if status is None:
        status = json.loads(status_path.read_text()) if status_path.exists() else {}
    steps = list(status.get("steps", []))
    completed = sum(1 for row in steps if row.get("state") == "complete")
    active = next(
        (row.get("name") for row in steps if row.get("state") == "running"),
        status.get("phase", "not started"),
    )
    width = 20
    filled = int(width * completed / max(1, len(steps)))
    bar = "█" * filled + (
        "▌" if status.get("state") == "running" and filled < width else ""
    )
    bar += "·" * (width - len(bar))
    output = paths["production"] / "progress.md"
    output.write_text(
        "# Audiobook Harness progress\n\n"
        f"Updated: {status.get('updated_at', _now())}\n\n"
        f"**State:** `{status.get('state', 'not_started')}`\n\n"
        f"`[{bar}] {completed}/{len(steps)} steps complete`\n\n"
        f"**Current:** {active}\n\n"
        + "\n".join(
            f"- {'█' if row.get('state') == 'complete' else '▌' if row.get('state') == 'running' else '·'} {row.get('name')}"
            for row in steps
        )
        + "\n",
        encoding="utf-8",
    )
    return output


def watch(project: Path, interval_seconds: float = 2.0) -> None:
    while True:
        render_status(project)
        time.sleep(max(0.5, interval_seconds))
