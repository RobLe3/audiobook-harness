from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .project import project_paths, write_json


PROGRESS_SCHEMA = "audiobook-harness-progress-v1"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def owner_activity(status: dict[str, Any]) -> tuple[str, str]:
    """Distinguish a durable snapshot from a live command.

    A rendered Markdown file can be regenerated long after a command failed.
    This guard prevents a stale ``running`` status from looking live merely
    because someone opened or watched the file again.
    """
    state = str(status.get("state", "not_started"))
    if state != "running":
        return "terminal", "run is not active"
    raw_pid = status.get("owner_pid")
    try:
        pid = int(raw_pid)
    except (TypeError, ValueError):
        return "inactive", "no owner PID was recorded"
    try:
        command = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            check=False, capture_output=True, text=True,
        ).stdout.strip()
    except OSError:
        command = ""
    if "audiobook-harness" in command or "audiobook_harness" in command:
        return "active", "the production command is running"
    return "inactive", "the recorded production command is no longer running"


def write_run_status(
    project: Path, *, state: str, phase: str, **changes: Any
) -> dict[str, Any]:
    paths = project_paths(project)
    path = paths["production"] / "run-status.json"
    current = (
        json.loads(path.read_text()) if path.exists() else {"version": 2, "steps": []}
    )
    current.update(changes)
    current.update({
        "version": max(int(current.get("version", 1)), 2),
        "progress_schema": PROGRESS_SCHEMA,
        "state": state,
        "phase": phase,
        "updated_at": _now(),
        "owner_pid": os.getpid() if state == "running" else current.get("owner_pid"),
    })
    write_json(path, current)
    render_status(project, current)
    return current


def render_status(project: Path, status: dict[str, Any] | None = None) -> Path:
    paths = project_paths(project)
    status_path = paths["production"] / "run-status.json"
    if status is None:
        status = json.loads(status_path.read_text()) if status_path.exists() else {}
    steps = list(status.get("steps", []))
    owner_state, owner_detail = owner_activity(status)
    completed = sum(1 for row in steps if row.get("state") == "complete")
    active_step = next(
        (row.get("name") for row in steps if row.get("state") == "running"),
        status.get("phase", "not started"),
    )
    width = 20
    filled = int(width * completed / max(1, len(steps)))
    is_active = status.get("state") == "running" and owner_state == "active"
    bar = "█" * filled + (
        "▌" if is_active and filled < width else ""
    )
    bar += "·" * (width - len(bar))
    output = paths["production"] / "progress.md"
    history = ""
    if status.get("state") == "running" and owner_state != "active":
        history = (
            "\n**Run status:** this snapshot is interrupted, not live. Inspect the "
            "last command result, then explicitly retry the affected stage.\n"
        )
    elif status.get("state") in {"failed", "complete"}:
        history = "\n**Run status:** this is a completed historical snapshot, not a live command.\n"
    output.write_text(
        "# Audiobook Harness progress\n\n"
        f"Updated: {status.get('updated_at', _now())}\n\n"
        f"**State:** `{status.get('state', 'not_started')}`\n\n"
        f"**Production owner:** `{owner_state}` — {owner_detail}.\n"
        f"{history}\n"
        f"`[{bar}] {completed}/{len(steps)} steps complete`\n\n"
        f"**Current:** {active_step}\n\n"
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
        rendered = render_status(project)
        content = rendered.read_text(encoding="utf-8")
        if sys.stdout.isatty():
            print("\033[2J\033[H", end="")
        print(content, end="" if content.endswith("\n") else "\n")
        time.sleep(max(0.5, interval_seconds))
