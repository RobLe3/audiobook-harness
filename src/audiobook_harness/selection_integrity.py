"""Verify that a selected take still names the exact verified candidate bytes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .project import project_paths, sha256, write_json
from .context_protocol import candidate_protocol_error


def audit_candidate_selection(
    project: Path, verification: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Validate candidate-manifest and waveform hashes behind every selection.

    Candidate generation may be repeated, so a filename alone is not evidence
    that a previously verified waveform is still the waveform being assembled.
    A normal selection must match a current manifest row exactly. A retained
    predecessor is allowed only when its source unit still exists and its
    content-addressed audio file remains hash-identical.
    """
    paths = project_paths(project)
    candidates_path = paths["production"] / "candidates.json"
    verification_path = paths["production"] / "verification.json"
    errors: list[dict[str, str]] = []

    if not candidates_path.is_file():
        errors.append({"rule": "candidate_manifest_missing"})
        candidates: list[dict[str, Any]] = []
        manifest_sha256 = None
    else:
        payload = json.loads(candidates_path.read_text(encoding="utf-8"))
        candidates = list(payload.get("candidates", []))
        manifest_sha256 = sha256(candidates_path)

    if verification is None:
        if not verification_path.is_file():
            errors.append({"rule": "verification_missing"})
            verification = {}
        else:
            verification = json.loads(verification_path.read_text(encoding="utf-8"))

    if verification.get("candidate_manifest_sha256") != manifest_sha256:
        errors.append(
            {
                "rule": "candidate_manifest_hash_mismatch",
                "expected": str(verification.get("candidate_manifest_sha256")),
                "actual": str(manifest_sha256),
            }
        )

    candidate_rows = {
        (
            str(row.get("id")),
            str(row.get("candidate")),
            str(row.get("file")),
            str(row.get("sha256")),
            str(row.get("source_hash")),
        )
        for row in candidates
    }
    source_hashes: dict[str, set[str]] = {}
    for row in candidates:
        source_hashes.setdefault(str(row.get("id")), set()).add(
            str(row.get("source_hash"))
        )

    checked: list[dict[str, str]] = []
    for take in verification.get("takes", []):
        take_id = str(take.get("id"))
        row = {
            "id": take_id,
            "candidate": str(take.get("candidate")),
            "file": str(take.get("file")),
        }
        checked.append(row)
        path = project / row["file"]
        expected_audio_sha = str(take.get("sha256"))
        protocol_error = candidate_protocol_error(take)
        if protocol_error:
            errors.append({"rule": protocol_error, **row})
            continue
        if not path.is_file():
            errors.append({"rule": "selected_audio_missing", **row})
            continue
        if sha256(path) != expected_audio_sha:
            errors.append({"rule": "selected_audio_hash_mismatch", **row})
            continue

        source_hash = str(take.get("source_hash"))
        if take.get("retained_predecessor"):
            if source_hash not in source_hashes.get(take_id, set()):
                errors.append({"rule": "retained_source_not_current", **row})
            continue

        key = (
            take_id,
            str(take.get("candidate")),
            row["file"],
            expected_audio_sha,
            source_hash,
        )
        if key not in candidate_rows:
            errors.append({"rule": "selection_not_current_candidate", **row})

    report: dict[str, Any] = {
        "version": 1,
        "ok": not errors,
        "candidate_manifest_sha256": manifest_sha256,
        "verification_candidate_manifest_sha256": verification.get(
            "candidate_manifest_sha256"
        ),
        "checked": checked,
        "errors": errors,
    }
    write_json(paths["production"] / "candidate-selection-integrity.json", report)
    return report
