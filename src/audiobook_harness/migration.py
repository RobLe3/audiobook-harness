from __future__ import annotations
import hashlib
import json
from pathlib import Path
from typing import Any
from .project import write_json

TARGET_SCHEMA = "0.4"


def upgrade_plan(project: Path) -> dict[str, Any]:
    production = project / "production"
    present = [
        name
        for name in (
            "analysis.json",
            "candidates.json",
            "verification.json",
            "stage-manifest.json",
        )
        if (production / name).is_file()
    ]
    plan: dict[str, Any] = {
        "version": 1,
        "target_schema": TARGET_SCHEMA,
        "project": str(project.resolve()),
        "preserve": present,
        "generate": [
            "manuscript-structure.json",
            "spoken-forms.json",
            "dialogue-speaker-map.json",
            "prosody-plan.json",
            "tts-risk-map.json",
            "performance-units.json",
        ],
        "invalidate_from": "analysis",
    }
    plan["inventory_sha256"] = hashlib.sha256(
        json.dumps(plan, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return plan


def apply_upgrade(project: Path, inventory_sha256: str) -> dict[str, Any]:
    plan = upgrade_plan(project)
    if inventory_sha256 != plan["inventory_sha256"]:
        raise RuntimeError(
            f"Refusing migration: pass --inventory-sha256 {plan['inventory_sha256']}"
        )
    write_json(
        project / "production/project-schema.json",
        {"schema": TARGET_SCHEMA, "migration_inventory_sha256": inventory_sha256},
    )
    return {**plan, "ok": True, "applied": True}
