"""Series-wide reconciliation of automatic work, dependencies, and review."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any


AUTOMATIC_STATES = {"executable", "verification_pending"}


def _identity(value: object) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def reconcile_outstanding_work(
    episodes: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Return one fixed-point queue without hiding executable work as review."""

    rows = []
    for episode in episodes:
        cue_states = [
            row for row in episode.get("cue_states", []) if isinstance(row, Mapping)
        ]
        repairable = [
            str(row.get("unit"))
            for row in cue_states
            if row.get("state") == "repairable"
        ]
        review = [
            str(row.get("unit"))
            for row in cue_states
            if row.get("state") == "review_required"
        ]
        missing = [str(value) for value in episode.get("missing_evidence", [])]
        dependencies = [
            str(value) for value in episode.get("unresolved_dependencies", [])
        ]
        # An explicit review gate is authoritative for the affected episode.
        # Missing downstream files must not turn a human decision into an
        # endless automatic retry.  Dependencies are considered only after
        # the episode has no local review obligation.
        if episode.get("complete") is True:
            state, action = "complete", "none"
        elif review:
            state, action = "review_required", "build_focused_review"
        elif dependencies:
            state, action = "waiting_dependency", "none"
        elif missing:
            state, action = "verification_pending", "verify_current_outputs"
        elif repairable:
            state, action = "executable", "execute_bounded_repair"
        elif episode.get("fatal_error"):
            state, action = "fatal", "tested_harness_correction"
        else:
            state, action = "executable", "resume_pipeline"
        row = {
            "episode": str(episode.get("episode", "")),
            "state": state,
            "action": action,
            "owner_phase": int(episode.get("owner_phase", 1)),
            "repairable_units": repairable,
            "review_units": review,
            "missing_evidence": missing,
            "dependency_ids": dependencies,
        }
        row["work_identity_sha256"] = _identity(row)
        rows.append(row)
    counts = {
        state: sum(row["state"] == state for row in rows)
        for state in (
            "executable",
            "verification_pending",
            "waiting_dependency",
            "review_required",
            "complete",
            "fatal",
        )
    }
    report = {
        "version": 1,
        "items": rows,
        "counts": counts,
        "automatic_work_remaining": any(
            row["state"] in AUTOMATIC_STATES for row in rows
        ),
        "manual_review_remaining": bool(counts["review_required"]),
        "ok": not counts["fatal"],
    }
    report["identity_sha256"] = _identity(report)
    return report
