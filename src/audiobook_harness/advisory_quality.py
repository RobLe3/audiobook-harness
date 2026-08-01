"""Optional local advisory scorers that never grant release authority."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .project import write_json


SCORERS = ("nisqa_tts", "utmos", "speaker_similarity", "ctc_alignment")


def collect_advisory_scores(project: Path) -> dict[str, Any]:
    """Collect precomputed pinned-local scores with an explicit unavailable state."""

    production = project / "production"
    rows = []
    for name in SCORERS:
        source = production / "advisory" / f"{name}.json"
        try:
            value = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            value = None
        rows.append(
            {
                "scorer": name,
                "available": isinstance(value, dict),
                "result": value if isinstance(value, dict) else None,
                "authority": "candidate_ranking_and_review_priority_only",
            }
        )
    report = {
        "version": 1,
        "scorers": rows,
        "automatic_acceptance_authority": False,
        "ok": True,
    }
    write_json(production / "advisory-quality.json", report)
    return report
