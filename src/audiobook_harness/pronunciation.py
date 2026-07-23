from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .project import project_paths, write_json


def load_reviewed_lexicon(project: Path) -> dict[str, dict[str, Any]]:
    path = project_paths(project)["lexicon"]
    data = (
        json.loads(path.read_text(encoding="utf-8"))
        if path.exists()
        else {"entries": []}
    )
    entries = data.get("entries", [])
    if not isinstance(entries, list):
        raise ValueError("lexicon.json entries must be a list")
    result: dict[str, dict[str, Any]] = {}
    for row in entries:
        if not isinstance(row, dict) or not row.get("published"):
            raise ValueError("Every lexicon entry requires published text")
        result[str(row["published"])] = row
    return result


def audit_lexicon(project: Path) -> dict[str, Any]:
    paths = project_paths(project)
    analysis = json.loads(
        (paths["production"] / "analysis.json").read_text(encoding="utf-8")
    )
    lexicon = load_reviewed_lexicon(project)
    required = analysis.get("unresolved_lexicon_candidates", [])
    missing = [term for term in required if term not in lexicon]
    unreviewed = [
        term
        for term in required
        if term in lexicon and lexicon[term].get("review_status") != "reviewed"
    ]
    invalid = [
        term
        for term, row in lexicon.items()
        if row.get("review_status") == "reviewed" and not row.get("phoneme_override")
    ]
    invalid_asr_equivalences: list[str] = []
    for term, row in lexicon.items():
        equivalents = row.get("asr_equivalents", [])
        if not equivalents:
            continue
        valid = (
            row.get("review_status") == "reviewed"
            and row.get("scope", "term") in {"term", "phrase"}
            and bool(row.get("phoneme_override"))
            and bool(str(row.get("source", "")).strip())
            and isinstance(equivalents, list)
            and all(isinstance(value, str) and value.strip() for value in equivalents)
        )
        if not valid:
            invalid_asr_equivalences.append(term)
    report = {
        "ok": not missing
        and not unreviewed
        and not invalid
        and not invalid_asr_equivalences,
        "missing": missing,
        "unreviewed": unreviewed,
        "invalid": invalid,
        "invalid_asr_equivalences": invalid_asr_equivalences,
    }
    write_json(paths["production"] / "pronunciation-audit.json", report)
    return report


def asr_equivalences(lexicon: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    """Return reviewed term/phrase ASR spellings without changing TTS input.

    An equivalence is evidence for decoder orthography only.  It remains
    project-local and is usable only by an authenticated lexicon entry.
    """
    pairs: list[dict[str, str]] = []
    for published, row in lexicon.items():
        if (
            row.get("review_status") != "reviewed"
            or row.get("scope", "term") not in {"term", "phrase"}
            or not row.get("phoneme_override")
            or not str(row.get("source", "")).strip()
        ):
            continue
        for spelling in row.get("asr_equivalents", []):
            if isinstance(spelling, str) and spelling.strip():
                pairs.append(
                    {
                        "observed": spelling.strip(),
                        "expected": str(row.get("spoken", published)),
                        "published": published,
                        "scope": str(row.get("scope", "term")),
                        "source": str(row["source"]),
                    }
                )
    return sorted(pairs, key=lambda item: len(item["observed"]), reverse=True)


def apply_to_phonemes(
    text: str, phonemes: str, lexicon: dict[str, dict[str, Any]], phonemize: Any
) -> str:
    """Replace only the model's matching phoneme spans, never raw words."""
    resolved = phonemes
    for published, row in sorted(
        lexicon.items(), key=lambda item: len(item[0]), reverse=True
    ):
        if (
            published not in text
            or row.get("review_status") != "reviewed"
            or not row.get("phoneme_override")
        ):
            continue
        default = str(phonemize(published))
        if default not in resolved:
            raise ValueError(f"Cannot apply lexicon phonemes in context: {published}")
        resolved = resolved.replace(default, str(row["phoneme_override"]), 1)
    return resolved
