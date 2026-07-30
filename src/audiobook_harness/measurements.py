from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import __version__
from .project import write_json


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def build_quality_measurements(project: Path) -> dict[str, Any]:
    production = project / "production"
    verification = _load(production / "verification.json")
    takes = verification.get("takes", [])
    dimensions = {
        "text_accuracy": {
            "ok": bool(takes)
            and all(
                float(row.get("primary_wer", 1)) <= 0.01
                and float(row.get("secondary_wer", 1)) <= 0.01
                for row in takes
            ),
            "maximum_primary_wer": max(
                (float(row.get("primary_wer", 1)) for row in takes), default=None
            ),
            "maximum_secondary_wer": max(
                (float(row.get("secondary_wer", 1)) for row in takes), default=None
            ),
        },
        "pronunciation": _status(production / "pronunciation-audit.json"),
        "alignment": _status(production / "forced-alignment.json"),
        "phoneme_duration": _status(production / "phoneme-duration-audit.json"),
        "pause_economy": _status(production / "pause-economy-lint.json"),
        "speaker_energy": _status(production / "energy-lint.json"),
        "expressive_realization": _status(production / "expressive-realization.json"),
        "full_file_fidelity": _status(production / "full-file-fidelity.json"),
        "chapter_ending": _status(production / "chapter-ending-audit.json"),
        "encoded_media": _status(production / "encoded-deliverable-quality.json"),
        "perceptual_regression": _status(production / "perceptual-regression.json"),
    }
    blocking = {
        name: value
        for name, value in dimensions.items()
        if not bool(value.get("ok", False))
    }
    report = {
        "version": 1,
        "audiobook_harness_version": __version__,
        "dimensions": dimensions,
        "blocking_dimensions": sorted(blocking),
        "ok": not blocking,
        "single_quality_score": None,
    }
    write_json(production / "quality-measurements.json", report)
    return report


def _status(path: Path) -> dict[str, Any]:
    value = _load(path)
    return {
        "available": bool(value),
        "ok": bool(value.get("ok", value.get("release_ready", False))),
        "artifact": path.name,
    }
