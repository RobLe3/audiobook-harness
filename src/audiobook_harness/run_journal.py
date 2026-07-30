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


def phase_receipt_path(project: Path, step: int) -> Path:
    return project / "production/phase-receipts" / f"step-{step}.json"


def write_phase_receipt(
    project: Path,
    *,
    step: int,
    input_identity: str,
    artifacts: list[Path],
) -> dict[str, Any]:
    """Checkpoint one completed production phase and its exact output bytes."""

    missing = [str(path) for path in artifacts if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            f"phase {step} is missing checkpoint artifacts: {missing}"
        )
    receipt = {
        "version": 1,
        "step": step,
        "input_identity": input_identity,
        "artifacts": [
            {
                "path": str(path.relative_to(project)),
                "sha256": sha256(path),
                "bytes": path.stat().st_size,
            }
            for path in artifacts
        ],
    }
    write_json(phase_receipt_path(project, step), receipt)
    return receipt


def phase_receipt_is_valid(project: Path, *, step: int, input_identity: str) -> bool:
    """Accept reuse only when identity and every checkpointed byte still match."""

    try:
        receipt = json.loads(
            phase_receipt_path(project, step).read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        return False
    if (
        receipt.get("step") != step
        or receipt.get("input_identity") != input_identity
        or not isinstance(receipt.get("artifacts"), list)
        or not receipt["artifacts"]
    ):
        return False
    for row in receipt["artifacts"]:
        path = project / str(row.get("path", ""))
        if (
            not path.is_file()
            or path.stat().st_size != row.get("bytes")
            or sha256(path) != row.get("sha256")
        ):
            return False
    return True


def write_phase_repair_receipt(
    project: Path,
    *,
    owner_phase: int,
    base_input_identity: str,
    current_input_identity: str,
    changed_dependencies: list[Path],
    evidence: list[Path],
) -> dict[str, Any]:
    """Authorize rerunning one phase without discarding valid predecessors.

    Evidence must be machine-readable and explicitly passing. This receipt is
    never review approval and never marks the owning phase complete.
    """

    if owner_phase < 1:
        raise ValueError("owner_phase must be positive")
    if not changed_dependencies or not evidence:
        raise ValueError("phase repair requires changed dependencies and evidence")
    evidence_rows = []
    for path in evidence:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or value.get("ok") is not True:
            raise ValueError(f"repair evidence is not objectively passing: {path}")
        evidence_rows.append(_bound_file(project, path))
    receipt = {
        "version": 1,
        "authority": "objective_phase_scoped_repair",
        "owner_phase": owner_phase,
        "base_input_identity": base_input_identity,
        "current_input_identity": current_input_identity,
        "changed_dependencies": [
            _bound_file(project, path) for path in changed_dependencies
        ],
        "evidence": evidence_rows,
        "human_approval": False,
    }
    write_json(project / "production/phase-repair-receipt.json", receipt)
    return receipt


def valid_phase_repair_receipt(
    project: Path, *, current_input_identity: str
) -> dict[str, Any] | None:
    try:
        receipt = json.loads(
            (project / "production/phase-repair-receipt.json").read_text(
                encoding="utf-8"
            )
        )
    except (OSError, json.JSONDecodeError):
        return None
    if (
        receipt.get("authority") != "objective_phase_scoped_repair"
        or receipt.get("human_approval") is not False
        or receipt.get("current_input_identity") != current_input_identity
        or int(receipt.get("owner_phase", 0)) < 1
    ):
        return None
    for key in ("changed_dependencies", "evidence"):
        rows = receipt.get(key)
        if not isinstance(rows, list) or not rows:
            return None
        for row in rows:
            if not _bound_file_is_current(project, row):
                return None
    for row in receipt["evidence"]:
        try:
            value = json.loads((project / str(row["path"])).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, KeyError):
            return None
        if not isinstance(value, dict) or value.get("ok") is not True:
            return None
    return receipt


def _bound_file(project: Path, path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    if not resolved.is_file():
        raise ValueError(f"repair file must exist: {path}")
    inside = resolved.is_relative_to(project.resolve())
    return {
        "path": str(resolved.relative_to(project.resolve()) if inside else resolved),
        "relative_to_project": inside,
        "sha256": sha256(resolved),
        "bytes": resolved.stat().st_size,
    }


def _bound_file_is_current(project: Path, row: object) -> bool:
    if not isinstance(row, dict):
        return False
    raw = Path(str(row.get("path", "")))
    path = (
        (project / raw).resolve()
        if row.get("relative_to_project", True)
        else raw.resolve()
    )
    return bool(
        path.is_file()
        and path.stat().st_size == row.get("bytes")
        and sha256(path) == row.get("sha256")
    )


def write_stage_receipt(
    path: Path,
    *,
    run_id: str,
    chapter_id: str,
    quality_report: Path,
    media: list[Path],
    dependency_fingerprint: str | None = None,
) -> dict[str, Any]:
    """Bind a packaged chapter to its verified report and exact output bytes."""
    receipt = {
        "version": 1,
        "run_id": run_id,
        "chapter_id": chapter_id,
        "quality_report_sha256": sha256(quality_report),
        # A receipt without this is intentionally legacy evidence: callers that
        # know their current input identity must reject it instead of silently
        # promoting media made from stale source, lexicon, model, or code.
        "dependency_fingerprint": dependency_fingerprint,
        "media": [
            {"name": item.name, "sha256": sha256(item), "bytes": item.stat().st_size}
            for item in media
        ],
    }
    write_json(path, receipt)
    return receipt


def receipt_is_valid(
    receipt: dict[str, Any],
    *,
    run_id: str,
    chapter_id: str,
    stage: Path,
    quality_report: Path,
    expected_names: set[str],
    dependency_fingerprint: str | None = None,
) -> bool:
    if receipt.get("run_id") != run_id or receipt.get("chapter_id") != chapter_id:
        return False
    if receipt.get("quality_report_sha256") != sha256(quality_report):
        return False
    if (
        dependency_fingerprint is not None
        and receipt.get("dependency_fingerprint") != dependency_fingerprint
    ):
        return False
    rows = receipt.get("media", [])
    if (
        not isinstance(rows, list)
        or {str(row.get("name")) for row in rows} != expected_names
    ):
        return False
    return all(
        (stage / str(row.get("name"))).is_file()
        and (stage / str(row.get("name"))).stat().st_size == int(row.get("bytes", -1))
        and sha256(stage / str(row.get("name"))) == row.get("sha256")
        for row in rows
    )
