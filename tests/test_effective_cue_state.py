from __future__ import annotations

import json
from pathlib import Path

from audiobook_harness.effective_cue_state import build_effective_cue_state


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_downstream_pronunciation_failure_keeps_selection_provisional(
    tmp_path: Path,
):
    project = tmp_path / "book"
    production = project / "production"
    verification = {
        "takes": [{"id": "u1", "candidate": "a", "file": "a.flac", "sha256": "abc"}],
        "failures": [],
    }
    _write(
        production / "candidate-strategy-ledger.json",
        {
            "units": [
                {
                    "unit": "u1",
                    "verification": "pending_or_passed",
                    "untried_eligible_families": [],
                }
            ]
        },
    )
    _write(
        production / "pronunciation-audit.json",
        {"ok": False, "failures": ["u1"]},
    )

    report = build_effective_cue_state(project, verification)

    row = report["units"][0]
    assert row["state"] == "repairable"
    assert row["selected_waveform"]["provisional"]
    assert row["failed_gates"] == ["pronunciation-audit.json"]


def test_untried_family_routes_to_automatic_repair(tmp_path: Path):
    project = tmp_path / "book"
    production = project / "production"
    _write(
        production / "candidate-strategy-ledger.json",
        {
            "units": [
                {
                    "unit": "u1",
                    "verification": "rejected",
                    "untried_eligible_families": ["contextual_terminal"],
                }
            ]
        },
    )

    report = build_effective_cue_state(project, {"takes": [], "failures": ["u1"]})

    assert report["units"][0]["state"] == "repairable"
    assert report["units"][0]["next_action"] == "attempt_untried_strategy_family"
