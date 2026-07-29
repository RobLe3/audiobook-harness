from __future__ import annotations

import json
import re
import unicodedata
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
    return apply_to_phonemes_with_evidence(text, phonemes, lexicon, phonemize)[0]


def apply_to_phonemes_with_evidence(
    text: str, phonemes: str, lexicon: dict[str, dict[str, Any]], phonemize: Any
) -> tuple[str, list[dict[str, Any]]]:
    """Apply reviewed overrides to every non-overlapping source occurrence."""
    normalized = unicodedata.normalize("NFC", text)
    occupied: list[tuple[int, int]] = []
    occurrences: list[tuple[int, int, str, str, dict[str, Any]]] = []
    for published, row in sorted(lexicon.items(), key=lambda item: len(item[0]), reverse=True):
        if row.get("review_status") != "reviewed" or not row.get("phoneme_override"):
            continue
        surfaces = [published, *row.get("aliases", [])]
        for surface in surfaces:
            if not isinstance(surface, str) or not surface:
                continue
            for match in re.finditer(re.escape(unicodedata.normalize("NFC", surface)), normalized, re.IGNORECASE):
                span = match.span()
                if any(span[0] < end and start < span[1] for start, end in occupied):
                    continue
                occupied.append(span)
                occurrences.append((span[0], span[1], match.group(0), published, row))
    resolved = phonemes
    evidence: list[dict[str, Any]] = []
    for start, end, surface, published, row in sorted(occurrences):
        default = str(phonemize(surface))
        if default not in resolved:
            raise ValueError(
                f"Cannot apply lexicon phonemes for occurrence {published} at {start}:{end}"
            )
        override = str(row["phoneme_override"])
        before = resolved
        phoneme_start = before.find(default)
        resolved = before.replace(default, override, 1)
        evidence.append(
            {
                "published": published,
                "surface": surface,
                "source_span": [start, end],
                "phoneme_span": [phoneme_start, phoneme_start + len(override)],
                "default_phonemes": default,
                "resolved_phonemes": override,
            }
        )
    return resolved, evidence
