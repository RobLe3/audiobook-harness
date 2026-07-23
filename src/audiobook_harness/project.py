from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any

import yaml


def load_project(root: Path) -> dict[str, Any]:
    path = root / "project.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Missing project configuration: {path}")
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("project.yaml must contain a mapping")
    return value


def project_paths(root: Path) -> dict[str, Path]:
    return {
        "source": root / "source",
        "production": root / "production",
        "assets": root / "assets/generated",
        "deliverables": root / "deliverables",
        "lexicon": root / "lexicon.json",
    }


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def normalized_words(value: str) -> list[str]:
    return re.findall(
        r"[a-z0-9]+(?:['-][a-z0-9]+)?", value.casefold().replace("’", "'")
    )


def sentence_units(value: str) -> list[str]:
    compact = re.sub(r"\s+", " ", value.strip())
    # Preserve a closing typographic quote with its sentence. A simple
    # lookbehind split would leave ``”`` attached to the next unit and hide a
    # terse quote from the contextual-dialogue guard.
    return [
        part.strip()
        for part in re.findall(r".+?[.!?](?:[”\"])?(?=\s|$)|.+$", compact)
        if part.strip()
    ]


def is_terse_quoted_dialogue(value: str, *, maximum_words: int = 5) -> bool:
    """Identify a short, self-contained quotation unsafe as an isolated take."""
    text = value.strip()
    quoted = text.startswith(('"', "“")) and text.endswith(('"', "”"))
    return quoted and 0 < len(normalized_words(text)) <= maximum_words


def performance_units(value: str) -> list[dict[str, Any]]:
    """Keep terse adjacent dialogue in real manuscript context.

    Kokoro can over-emphasise terminal vowels when a one-to-five-word quoted
    reply is synthesized as an isolated request.  Rather than inventing actor
    voices or splicing phonemes, this public baseline joins it with a real
    adjacent sentence from the manuscript.  The combined take is released as
    one semantic performance unit and its source sentence IDs remain recorded.
    """
    source = sentence_units(value)
    units: list[dict[str, Any]] = []
    index = 0
    while index < len(source):
        current = source[index]
        if is_terse_quoted_dialogue(current) and index + 1 < len(source):
            units.append(
                {
                    "text": f"{current} {source[index + 1]}",
                    "source_sentence_indexes": [index + 1, index + 2],
                    "context_strategy": "adjacent_manuscript_context",
                    "contains_terse_dialogue": True,
                    "requires_context_review": False,
                }
            )
            index += 2
            continue
        if is_terse_quoted_dialogue(current) and units:
            previous = units[-1]
            previous["text"] = f"{previous['text']} {current}"
            previous["source_sentence_indexes"].append(index + 1)
            previous["context_strategy"] = "adjacent_manuscript_context"
            previous["contains_terse_dialogue"] = True
            previous["requires_context_review"] = False
            index += 1
            continue
        units.append(
            {
                "text": current,
                "source_sentence_indexes": [index + 1],
                "context_strategy": "complete_sentence",
                "contains_terse_dialogue": is_terse_quoted_dialogue(current),
                "requires_context_review": is_terse_quoted_dialogue(current),
            }
        )
        index += 1
    return units


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def scaffold(destination: Path, template_root: Path) -> None:
    if destination.exists() and any(destination.iterdir()):
        raise FileExistsError(f"Destination is not empty: {destination}")
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copytree(template_root, destination, dirs_exist_ok=True)
