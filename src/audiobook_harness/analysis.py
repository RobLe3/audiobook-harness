from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .project import load_project, normalized_words, project_paths, sentence_units, write_json

ACRONYM = re.compile(r"\b(?:[A-Z]{2,}|(?:[A-Z]\.){2,})\b")
NUMBER = re.compile(r"\b\d+(?:[.,/]\d+)*\b")
FOREIGN_OR_NAME = re.compile(r"\b[A-Z][A-Za-zÀ-ÖØ-öø-ÿ'’-]+\b")


def analyze(project: Path) -> dict[str, Any]:
    config = load_project(project)
    paths = project_paths(project)
    manuscript_files = sorted(paths["source"].glob("*.txt"))
    if not manuscript_files:
        raise FileNotFoundError("Add one or more UTF-8 .txt chapters under source/")
    chapters: list[dict[str, Any]] = []
    vocabulary: dict[str, set[str]] = {"acronyms": set(), "numbers": set(), "names_or_foreign": set()}
    for source in manuscript_files:
        text = source.read_text(encoding="utf-8").strip()
        units = sentence_units(text)
        for name, pattern in (("acronyms", ACRONYM), ("numbers", NUMBER), ("names_or_foreign", FOREIGN_OR_NAME)):
            vocabulary[name].update(pattern.findall(text))
        chapters.append({
            "id": source.stem,
            "source": str(source.relative_to(project)),
            "text": text,
            "units": [{"id": f"{source.stem}-{index:04d}", "text": unit, "words": normalized_words(unit)} for index, unit in enumerate(units, 1)],
        })
    lexicon = paths["lexicon"]
    known = []
    if lexicon.exists():
        known = [str(row.get("published", "")) for row in __import__("json").loads(lexicon.read_text()).get("entries", [])]
    unresolved = sorted({item for values in vocabulary.values() for item in values if item not in known})
    report = {
        "version": 1,
        "project": config.get("title"),
        "chapters": chapters,
        "vocabulary_candidates": {key: sorted(value) for key, value in vocabulary.items()},
        "unresolved_lexicon_candidates": unresolved,
        "release_blocked": bool(unresolved),
        "next": "Review lexicon.json; set review_status=reviewed for every pronunciation-sensitive entry.",
    }
    write_json(paths["production"] / "analysis.json", report)
    return report
