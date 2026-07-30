from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .feedback import defaults_identity, historical_matches, load_defaults
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
            prosody.append(
                {
                    "unit": unit["id"],
                    "boundary_after": boundary,
                    "pause_after_ms": 280 if quote else 180,
                    "breath_eligible": len(words) >= 18,
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
        report["identity_sha256"] = _identity(report)
        write_json(production / name, report)
    return reports
