from __future__ import annotations

import json
import difflib
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
    deprecated_phrase_aliases: list[str] = []
    for term, row in lexicon.items():
        equivalents = row.get("asr_equivalents", [])
        if not equivalents:
            continue
        if row.get("scope", "term") == "phrase":
            deprecated_phrase_aliases.append(term)
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
        and not invalid_asr_equivalences
        and not deprecated_phrase_aliases,
        "missing": missing,
        "unreviewed": unreviewed,
        "invalid": invalid,
        "invalid_asr_equivalences": invalid_asr_equivalences,
        "deprecated_phrase_aliases": deprecated_phrase_aliases,
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
            or row.get("scope", "term") != "term"
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


def reviewed_phrase_equivalence(
    *,
    expected: list[str],
    primary: list[str],
    secondary: list[str],
    lexicon: dict[str, dict[str, Any]],
    candidate: dict[str, Any],
) -> dict[str, Any] | None:
    """Accept ASR segmentation drift only inside one evidence-bound phrase."""

    applied = {
        str(row.get("published", "")).casefold()
        for row in candidate.get("pronunciation_occurrences", [])
        if isinstance(row, dict)
    }
    phonemes = re.sub(r"\s+", " ", str(candidate.get("phonemes", "")).strip())
    matches: list[tuple[int, int, str, dict[str, Any], list[str]]] = []
    from .project import normalized_words

    for published, row in lexicon.items():
        terms = normalized_words(str(row.get("spoken", published)))
        override = re.sub(r"\s+", " ", str(row.get("phoneme_override", "")).strip())
        if (
            len(terms) < 2
            or row.get("review_status") != "reviewed"
            or row.get("scope", "term") != "phrase"
            or str(row.get("language", "en")).lower().startswith("en")
            or row.get("validation_policy") != "reviewed_phrase_equivalence"
            or not override
            or published.casefold() not in applied
            or override not in phonemes
        ):
            continue
        for start in range(len(expected) - len(terms) + 1):
            end = start + len(terms)
            if expected[start:end] == terms:
                matches.append((start, end, published, row, terms))
    if len(matches) != 1:
        return None
    start, end, published, row, terms = matches[0]
    prefix, suffix = expected[:start], expected[end:]

    def observed_phrase(tokens: list[str]) -> list[str] | None:
        if tokens[: len(prefix)] != prefix:
            return None
        if suffix and tokens[-len(suffix) :] != suffix:
            return None
        stop = len(tokens) - len(suffix) if suffix else len(tokens)
        return tokens[len(prefix) : stop] or None

    first = observed_phrase(primary)
    second = observed_phrase(secondary)
    if first is None or second is None:
        return None
    compact = "".join(terms)
    similarity = [
        difflib.SequenceMatcher(None, compact, "".join(tokens)).ratio()
        for tokens in (first, second)
    ]
    if min(similarity) < 0.55:
        return None
    return {
        "acceptance": "reviewed_phrase_equivalence",
        "published": published,
        "source": row.get("source"),
        "resolved_phonemes": row.get("phoneme_override"),
        "primary_phrase": first,
        "secondary_phrase": second,
        "orthographic_similarity": [round(value, 6) for value in similarity],
        "candidate_audio_sha256": candidate.get("sha256"),
        "outside_phrase_exact": True,
    }


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
    for published, row in sorted(
        lexicon.items(), key=lambda item: len(item[0]), reverse=True
    ):
        if row.get("review_status") != "reviewed" or not row.get("phoneme_override"):
            continue
        surfaces = [published, *row.get("aliases", [])]
        for surface in surfaces:
            if not isinstance(surface, str) or not surface:
                continue
            for match in re.finditer(
                re.escape(unicodedata.normalize("NFC", surface)),
                normalized,
                re.IGNORECASE,
            ):
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
