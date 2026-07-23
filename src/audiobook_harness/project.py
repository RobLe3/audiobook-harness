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
    return re.findall(r"[a-z0-9]+(?:['-][a-z0-9]+)?", value.casefold().replace("’", "'"))


def sentence_units(value: str) -> list[str]:
    compact = re.sub(r"\s+", " ", value.strip())
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", compact) if part.strip()]


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def scaffold(destination: Path, template_root: Path) -> None:
    if destination.exists() and any(destination.iterdir()):
        raise FileExistsError(f"Destination is not empty: {destination}")
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copytree(template_root, destination, dirs_exist_ok=True)
