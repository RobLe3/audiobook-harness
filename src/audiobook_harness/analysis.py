from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .project import (
    load_project,
    normalized_words,
    performance_units,
    project_paths,
    write_json,
)

ACRONYM = re.compile(r"\b(?:[A-Z]{2,}|(?:[A-Z]\.){2,})\b")
NUMBER = re.compile(r"\b\d+(?:[.,/]\d+)*\b")
FOREIGN_OR_NAME = re.compile(r"\b[A-Z][A-Za-zÀ-ÖØ-öø-ÿ'’-]+\b")
ORDINARY_SENTENCE_STARTERS = {
    "a", "after", "although", "an", "and", "as", "at", "before", "but",
    "during", "for", "he", "her", "his", "however", "i", "if", "in", "it",
    "its", "later", "meanwhile", "on", "or", "she", "so", "that", "the",
    "their", "then", "there", "these", "they", "this", "those", "to", "we",
    "when", "where", "while", "who", "with", "yet", "you",
}


def analyze(project: Path) -> dict[str, Any]:
    config = load_project(project)
    paths = project_paths(project)
    manuscript_files = sorted(paths["source"].glob("*.txt"))
    if not manuscript_files:
        raise FileNotFoundError("Add one or more UTF-8 .txt chapters under source/")
    chapters: list[dict[str, Any]] = []
    contextual_review_units: list[str] = []
    vocabulary: dict[str, set[str]] = {
        "acronyms": set(),
        "numbers": set(),
        "names_or_foreign": set(),
    }
    global_sequence = 0
    for chapter_index, source in enumerate(manuscript_files, 1):
        text = source.read_text(encoding="utf-8").strip()
        units = performance_units(text)
        for name, pattern in (
            ("acronyms", ACRONYM),
            ("numbers", NUMBER),
            ("names_or_foreign", FOREIGN_OR_NAME),
        ):
            found = pattern.findall(text)
            if name == "names_or_foreign":
                found = [
                    value
                    for value in found
                    if value.casefold() not in ORDINARY_SENTENCE_STARTERS
                ]
            vocabulary[name].update(found)
        for index, unit in enumerate(units, 1):
            if bool(unit.get("requires_context_review", False)):
                contextual_review_units.append(f"{source.stem}-{index:04d}")
        unit_rows = []
        search_from = 0
        for index, unit in enumerate(units, 1):
            global_sequence += 1
            unit_text = str(unit["text"])
            source_start = text.find(unit_text, search_from)
            if source_start < 0:
                source_start = text.find(unit_text)
            source_end = source_start + len(unit_text) if source_start >= 0 else -1
            if source_end >= 0:
                search_from = source_end
            unit_rows.append(
                {
                    "id": f"{source.stem}-{index:04d}",
                    "text": unit_text,
                    "words": normalized_words(unit_text),
                    "chapter_index": chapter_index,
                    "unit_index": index,
                    "global_sequence": global_sequence,
                    "source_span": [source_start, source_end],
                    "source_sentence_indexes": unit["source_sentence_indexes"],
                    "context_strategy": unit["context_strategy"],
                    "contains_terse_dialogue": unit["contains_terse_dialogue"],
                    "requires_context_review": unit["requires_context_review"],
                }
            )
        chapters.append(
            {
                "id": source.stem,
                "chapter_index": chapter_index,
                "source": str(source.relative_to(project)),
                "text": text,
                "units": unit_rows,
            }
        )
    lexicon = paths["lexicon"]
    known = []
    if lexicon.exists():
        known = [
            str(row.get("published", ""))
            for row in __import__("json").loads(lexicon.read_text()).get("entries", [])
        ]
    unresolved = sorted(
        {item for values in vocabulary.values() for item in values if item not in known}
    )
    report = {
        "version": 1,
        "project": config.get("title"),
        "chapters": chapters,
        "vocabulary_candidates": {
            key: sorted(value) for key, value in vocabulary.items()
        },
        "unresolved_lexicon_candidates": unresolved,
        "contextual_dialogue_review_required": contextual_review_units,
        "release_blocked": bool(unresolved or contextual_review_units),
        "dialogue_rule": "Terse one-to-five-word quoted dialogue is kept in an adjacent real-manuscript performance unit; it is never synthesized as an isolated take.",
        "next": "Review lexicon.json; set review_status=reviewed for every pronunciation-sensitive entry.",
    }
    write_json(paths["production"] / "analysis.json", report)
    return report
