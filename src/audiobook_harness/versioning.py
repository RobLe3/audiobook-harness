from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from ._version import __version__
from .project import sha256, write_json

LEGACY_NORDLICHT_NARRATION_CONTRACT = "8.3.3"
LEGACY_NORDLICHT_SOUNDSCAPE_CONTRACT = "8.4"
COMPATIBILITY_ARTIFACTS = (
    "analysis.json",
    "candidates.json",
    "verification.json",
    "forced-alignment.json",
)


def compatibility_receipt(project: Path, *, apply: bool = False) -> dict[str, Any]:
    """Bind reusable legacy evidence without modifying its bytes or receipts."""
    production = project / "production"
    artifacts = [
        {"path": f"production/{name}", "sha256": sha256(production / name)}
        for name in COMPATIBILITY_ARTIFACTS
        if (production / name).is_file()
    ]
    inputs = []
    for path in [
        project / "project.yaml",
        project / "lexicon.json",
        *sorted((project / "source").glob("*.txt")),
    ]:
        if path.is_file():
            inputs.append(
                {"path": str(path.relative_to(project)), "sha256": sha256(path)}
            )
    payload: dict[str, Any] = {
        "version": 1,
        "product_version": __version__,
        "legacy_contracts": {
            "narration": LEGACY_NORDLICHT_NARRATION_CONTRACT,
            "soundscape": LEGACY_NORDLICHT_SOUNDSCAPE_CONTRACT,
        },
        "inputs": inputs,
        "artifacts": artifacts,
        "legacy_receipts_immutable": True,
        "reuse_authorized": len(artifacts) == len(COMPATIBILITY_ARTIFACTS)
        and bool(inputs),
    }
    payload["compatibility_sha256"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if apply:
        write_json(production / "version-compatibility-receipt.json", payload)
    return payload
