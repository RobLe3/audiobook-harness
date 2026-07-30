from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from . import __version__
from .feedback import defaults_identity, historical_matches, load_defaults
from .parity import project_profile_identity
from .project import normalized_words, write_json


def _identity(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode()
    ).hexdigest()


def build_analysis_contracts(
    project: Path, chapters: list[dict[str, Any]], language: str
) -> dict[str, Any]:
    production = project / "production"
    structures: list[dict[str, Any]] = []
    spoken_entries: list[dict[str, Any]] = []
    speakers: list[dict[str, Any]] = []
    prosody: list[dict[str, Any]] = []
    discourse: list[dict[str, Any]] = []
    energy: list[dict[str, Any]] = []
    emotions: list[dict[str, Any]] = []
    candidate_plan: list[dict[str, Any]] = []
    risks: list[dict[str, Any]] = []
    units: list[dict[str, Any]] = []
    learned_defaults = load_defaults(project)
    learned_defaults_sha256 = defaults_identity(learned_defaults)
    structured = re.compile(r"\b(?:\d{1,2}:\d{2}|\d+(?:[.,/]\d+)*%?|[A-Z]{2,})\b")
    for chapter in chapters:
        text = str(chapter["text"])
        paragraphs = []
        for index, match in enumerate(
            re.finditer(r"(?:^|\n\s*\n)(.*?)(?=\n\s*\n|\Z)", text, re.S), 1
        ):
            raw = match.group(1)
            leading = len(raw) - len(raw.lstrip())
            value = raw.strip()
            if not value:
                continue
            start = match.start(1) + leading
            kind = (
                "scene_break"
                if value in {"***", "* * *"}
                else "heading"
                if re.match(r"^(chapter|interlude)\b", value, re.I)
                else "paragraph"
            )
            paragraphs.append(
                {
                    "id": f"{chapter['id']}-p{index:04d}",
                    "kind": kind,
                    "source_span": [start, start + len(value)],
                    "text": value,
                }
            )
        structures.append(
            {
                "chapter": chapter["id"],
                "source": chapter["source"],
                "paragraphs": paragraphs,
                "source_sha256": hashlib.sha256(text.encode()).hexdigest(),
            }
        )
        for unit in chapter["units"]:
            value = str(unit["text"])
            words = normalized_words(value)
            quote = value.lstrip().startswith(('"', "“"))
            question = value.rstrip().endswith(("?", "?”", '?"'))
            exclamation = value.rstrip().endswith(("!", "!”", '!"'))
            factors = []
            learned = historical_matches(project, value)
            if len(words) <= 5:
                factors.append("short_fragment")
            if len(words) >= 35:
                factors.append("long_sentence")
            if quote:
                factors.append("dialogue")
            if structured.search(value):
                factors.append("structured_spoken_form")
            if learned:
                factors.append("listener_history")
            score = min(
                100, len(factors) * 20 + (15 if "…" in value or "..." in value else 0)
            )
            risk = "high" if score >= 50 else "medium" if score >= 25 else "low"
            boundary = (
                "scene_break"
                if any(
                    p["kind"] == "scene_break"
                    and p["source_span"][0] < unit["source_span"][0]
                    for p in paragraphs[-1:]
                )
                else "paragraph"
            )
            units.append(
                {
                    **unit,
                    "spoken_audio_span": unit["source_span"],
                    "context_span": unit["source_span"],
                }
            )
            speakers.append(
                {
                    "unit": unit["id"],
                    "mode": "dialogue" if quote else "narration",
                    "speaker": None if quote else "narrator",
                    "confidence": 0.0 if quote else 1.0,
                }
            )
            sentence_role = (
                "genuine_question_rise"
                if question
                else "emphatic_terminal"
                if exclamation
                else "declarative_terminal"
            )
            pause_after = 280 if quote else 180
            prosody.append(
                {
                    "unit": unit["id"],
                    "boundary_after": boundary,
                    "pause_after_ms": pause_after,
                    "breath_eligible": len(words) >= 18,
                }
            )
            discourse.append(
                {
                    "unit": unit["id"],
                    "sentence_role": sentence_role,
                    "boundary_function": (
                        "dialogue_turn" if quote else "narrative_continuation"
                    ),
                    "pause_target_ms": pause_after,
                    "breath_eligibility": (
                        "eligible" if len(words) >= 18 else "forbidden"
                    ),
                    "source": "deterministic_manuscript_analysis",
                }
            )
            energy_tier = (
                "heightened"
                if exclamation
                else "engaged"
                if quote or question
                else "grounded"
            )
            energy.append(
                {
                    "unit": unit["id"],
                    "tier": energy_tier,
                    "contour": "release" if exclamation else "hold",
                    "delivery": {
                        "pace": "controlled",
                        "prominence_budget": 2 if energy_tier == "heightened" else 1,
                        "pause_after_ms": pause_after,
                    },
                    "source": "punctuation_dialogue_and_density",
                }
            )
            emotions.append(
                {
                    "unit": unit["id"],
                    "label": "unspecified",
                    "confidence": 0.0,
                    "review_required": quote,
                }
            )
            risks.append(
                {
                    "unit": unit["id"],
                    "score": score,
                    "level": risk,
                    "factors": factors,
                    "candidate_budget": 5
                    if risk == "high"
                    else 4
                    if risk == "medium"
                    else 3,
                    "mandatory_review": risk == "high",
                    "listener_derived_defaults": learned,
                    "listener_derived_defaults_sha256": learned_defaults_sha256,
                }
            )
            candidate_plan.append(
                {
                    "unit": unit["id"],
                    "candidate_budget": 5
                    if risk == "high"
                    else 4
                    if risk == "medium"
                    else 3,
                    "dimensions": [
                        "pace",
                        "pause_plan",
                        "phrase_segmentation",
                    ],
                    "listener_derived_defaults": learned,
                    "selection_policy": "quality_vector_then_deterministic_tie_break",
                }
            )
            for match in structured.finditer(value):
                spoken_entries.append(
                    {
                        "unit": unit["id"],
                        "source": match.group(),
                        "spoken": None,
                        "kind": "structured_value",
                        "locale": language,
                        "source_span": [
                            unit["source_span"][0] + match.start(),
                            unit["source_span"][0] + match.end(),
                        ],
                        "review_status": "required",
                    }
                )
    reports = {
        "manuscript-structure.json": {"version": 1, "chapters": structures},
        "spoken-forms.json": {
            "version": 1,
            "entries": spoken_entries,
            "ok": not spoken_entries,
        },
        "dialogue-speaker-map.json": {"version": 1, "units": speakers},
        "discourse-prosody-map.json": {"version": 1, "units": discourse},
        "speaker-energy-map.json": {"version": 1, "units": energy},
        "emotion-map.json": {"version": 1, "units": emotions},
        "prosody-plan.json": {
            "version": 1,
            "units": prosody,
            "defaults_ms": {
                "same_paragraph": 180,
                "dialogue_turn": 280,
                "new_paragraph": 500,
                "scene_break": 1500,
                "chapter_tail": 1500,
            },
        },
        "tts-risk-map.json": {"version": 1, "units": risks},
        "performance-units.json": {"version": 1, "units": units},
        "candidate-plan.json": {"version": 1, "units": candidate_plan},
        "listener-defaults-preflight.json": {
            "version": 1,
            "defaults_sha256": learned_defaults_sha256,
            "defaults_revision": learned_defaults.get("revision", 0),
            "matches": [
                {"unit": row["unit"], "rules": row["listener_derived_defaults"]}
                for row in risks
                if row["listener_derived_defaults"]
            ],
        },
    }
    for name, report in reports.items():
        report["audiobook_harness_version"] = __version__
        report["project_profile_sha256"] = project_profile_identity(project)
        report["identity_sha256"] = _identity(report)
        write_json(production / name, report)
    return reports
