from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from . import __version__
from .project import write_json


CAPABILITIES = (
    ("source_preserving_analysis", "core", ("manuscript-structure.json",)),
    ("spoken_forms", "core", ("spoken-forms.json",)),
    ("dialogue_and_speaker_attribution", "core", ("dialogue-speaker-map.json",)),
    ("discourse_prosody", "core", ("discourse-prosody-map.json",)),
    ("speaker_energy", "core", ("speaker-energy-map.json",)),
    ("contextual_short_utterances", "core", ("performance-units.json",)),
    ("occurrence_aware_pronunciation", "core", ("pronunciation-audit.json",)),
    ("dual_asr", "core", ("verification.json",)),
    ("forced_alignment", "core", ("forced-alignment.json",)),
    ("phoneme_duration", "core", ("phoneme-duration-audit.json",)),
    ("pause_economy", "core", ("pause-economy-lint.json",)),
    ("expressive_realization", "core", ("expressive-realization.json",)),
    ("candidate_selection_integrity", "core", ("candidate-selection-integrity.json",)),
    ("full_file_fidelity", "core", ("full-file-fidelity.json",)),
    ("chapter_ending_protection", "core", ("chapter-ending-audit.json",)),
    ("encoded_media_quality", "core", ("encoded-deliverable-quality.json",)),
    ("mastered_context_review", "core", ("review-manifest.json",)),
    ("listener_feedback_learning", "core", ("listener-learning-summary.json",)),
    ("perceptual_regression", "core", ("perceptual-regression.json",)),
    ("communication_modes", "optional_profile", ("special-mode-quality-audit.json",)),
    ("soundscape", "optional_profile", ("soundscape-narration-lock.json",)),
    ("music", "optional_profile", ("music-cadence-audit.json",)),
    ("battle_audio", "optional_profile", ("battle-background-audit.json",)),
    ("videobook", "optional_profile", ("videobook-quality.json",)),
)


def feature_parity(project: Path) -> dict[str, Any]:
    production = project / "production"
    rows = []
    for capability, ownership, artifacts in CAPABILITIES:
        present = [name for name in artifacts if (production / name).is_file()]
        failed = [name for name in present if _explicitly_failed(production / name)]
        rows.append(
            {
                "capability": capability,
                "ownership": ownership,
                "required_artifacts": list(artifacts),
                "status": (
                    "passing"
                    if len(present) == len(artifacts) and not failed
                    else "failed"
                    if failed
                    else "missing"
                ),
                "present_artifacts": present,
                "failed_artifacts": failed,
            }
        )
    required = [row for row in rows if row["ownership"] == "core"]
    report: dict[str, Any] = {
        "version": 1,
        "audiobook_harness_version": __version__,
        "project_profile_sha256": project_profile_identity(project),
        "capabilities": rows,
        "required_capabilities": len(required),
        "passing_required_capabilities": sum(
            row["status"] == "passing" for row in required
        ),
        "ok": all(row["status"] == "passing" for row in required),
    }
    report["identity_sha256"] = hashlib.sha256(
        json.dumps(report, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    write_json(production / "feature-parity.json", report)
    return report


def _explicitly_failed(path: Path) -> bool:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return True
    for key in ("ok", "release_ready", "complete"):
        if key in value:
            return not bool(value[key])
    return False


def project_profile_identity(project: Path) -> str:
    candidates = (
        project / "project.yaml",
        project / "project-profile.json",
        project / "listener-derived-defaults.json",
    )
    digest = hashlib.sha256()
    for path in candidates:
        if path.is_file():
            digest.update(path.name.encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()
