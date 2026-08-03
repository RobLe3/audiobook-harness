"""Durable, evidence-bounded automatic convergence for local projects."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from .project import write_json
from .review import review_status


AUTOMATIC_REVIEW_ACTIONS = frozenset(
    {
        "corrections_queued",
        "targeted_repair_pending",
        "retry_scheduled",
        "await_review_media",
    }
)


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _file_identity(path: Path) -> str | None:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def automation_snapshot(project: Path) -> dict[str, Any]:
    """Classify current work without changing production or review state."""

    project = project.resolve()
    production = project / "production"
    status = review_status(project)
    action = str(status.get("reviewer_action", {}).get("code") or "")
    run = _read(production / "run-status.json")
    automatic = action in AUTOMATIC_REVIEW_ACTIONS
    blocked_reason = None
    if action in {"focused_review_required", "harness_correction_required"}:
        automatic = False
        blocked_reason = action
    inputs = {
        name: _file_identity(production / name)
        for name in (
            "run-status.json",
            "repair-plan.json",
            "review-processing-receipt.json",
            "review-decisions.json",
            "stage-manifest.json",
            "recovery-ledger.jsonl",
        )
    }
    inputs["project.yaml"] = _file_identity(project / "project.yaml")
    identity = hashlib.sha256(
        json.dumps(inputs, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        "version": 1,
        "project": str(project),
        "state": "automatic_work"
        if automatic
        else "blocked"
        if blocked_reason
        else "review_or_complete",
        "automatic": automatic,
        "reason": action or str(run.get("state") or "not_started"),
        "blocked_reason": blocked_reason,
        "input_identity": identity,
        "run_state": run.get("state", "not_started"),
    }


def converge_project(
    project: Path,
    *,
    maximum_iterations: int = 8,
    performance_profile: str = "auto",
) -> dict[str, Any]:
    """Run distinct automatic transitions until review or a true blocker."""

    project = project.resolve()
    production = project / "production"
    operation_path = production / "automation-operation.json"
    seen: set[str] = set()
    transitions: list[dict[str, Any]] = []
    for iteration in range(1, max(1, maximum_iterations) + 1):
        snapshot = automation_snapshot(project)
        if not snapshot["automatic"]:
            result = {
                "version": 1,
                "state": snapshot["state"],
                "reason": snapshot["reason"],
                "iterations": iteration - 1,
                "transitions": transitions,
            }
            write_json(operation_path, {**result, "owner_pid": os.getpid()})
            return result
        identity = str(snapshot["input_identity"])
        if identity in seen:
            result = {
                "version": 1,
                "state": "blocked",
                "reason": "automatic_repair_made_no_evidence_change",
                "iterations": iteration - 1,
                "input_identity": identity,
                "transitions": transitions,
            }
            write_json(operation_path, {**result, "owner_pid": os.getpid()})
            return result
        seen.add(identity)
        command = [
            sys.executable,
            "-m",
            "audiobook_harness.cli",
            "produce",
            str(project),
            "--performance-profile",
            performance_profile,
            "--max-candidate-retries",
            "3",
        ]
        if (production / "run-status.json").is_file():
            command.append("--resume")
        write_json(
            operation_path,
            {
                "version": 1,
                "state": "running",
                "iteration": iteration,
                "owner_pid": os.getpid(),
                "input_identity": identity,
                "command": command,
            },
        )
        completed = subprocess.run(
            command,
            cwd=project,
            capture_output=True,
            text=True,
            check=False,
        )
        transition = {
            "iteration": iteration,
            "input_identity": identity,
            "returncode": completed.returncode,
            "stdout_tail": completed.stdout[-2000:],
            "stderr_tail": completed.stderr[-2000:],
        }
        transitions.append(transition)
        if completed.returncode != 0:
            next_snapshot = automation_snapshot(project)
            if next_snapshot.get("input_identity") == identity:
                result = {
                    "version": 1,
                    "state": "blocked",
                    "reason": "automatic_repair_failed_without_new_evidence",
                    "iterations": iteration,
                    "transitions": transitions,
                }
                write_json(operation_path, {**result, "owner_pid": os.getpid()})
                return result
        time.sleep(0.05)
    result = {
        "version": 1,
        "state": "blocked",
        "reason": "automatic_iteration_budget_exhausted",
        "iterations": maximum_iterations,
        "transitions": transitions,
    }
    write_json(operation_path, {**result, "owner_pid": os.getpid()})
    return result
