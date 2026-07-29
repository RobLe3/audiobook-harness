from __future__ import annotations

import hashlib
import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .project import write_json


def _canonical(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def build_review(project: Path, stage: Path | None = None) -> dict[str, Any]:
    root = (stage or project / "staging").resolve()
    production = project / "production"
    staged = json.loads((root / "stage-manifest.json").read_text())
    risk_path = production / "tts-risk-map.json"
    risks = (
        json.loads(risk_path.read_text()).get("units", [])
        if risk_path.is_file()
        else []
    )
    mandatory = {str(row["unit"]) for row in risks if row.get("mandatory_review")}
    items = [
        {
            "id": f"chapter:{row['chapter']}",
            "kind": "assembled_chapter",
            "files": [f["file"] for f in row["files"]],
            "mandatory": True,
        }
        for row in staged["outputs"]
    ]
    for unit in staged.get("ordered_units", []):
        if str(unit["id"]) in mandatory:
            items.append(
                {
                    "id": str(unit["id"]),
                    "kind": "high_risk_unit",
                    "audio_sha256": unit["audio_sha256"],
                    "mandatory": True,
                }
            )
    manifest: dict[str, Any] = {
        "version": 1,
        "stage_manifest_sha256": _canonical(staged),
        "items": items,
    }
    manifest["review_identity_sha256"] = _canonical(manifest)
    write_json(production / "review-manifest.json", manifest)
    return manifest


def finalize_review(project: Path, decisions: list[dict[str, str]]) -> dict[str, Any]:
    production = project / "production"
    manifest = json.loads((production / "review-manifest.json").read_text())
    by_id = {str(row.get("id")): str(row.get("decision")) for row in decisions}
    required = [str(row["id"]) for row in manifest["items"] if row.get("mandatory")]
    unresolved = [item for item in required if by_id.get(item) != "approve"]
    report = {
        "version": 1,
        "review_identity_sha256": manifest["review_identity_sha256"],
        "decisions": decisions,
        "unresolved": unresolved,
        "finalized": True,
        "ok": not unresolved,
    }
    report["decisions_sha256"] = _canonical(decisions)
    write_json(production / "review-decisions.json", report)
    return report


def review_is_approved(project: Path) -> bool:
    try:
        manifest = json.loads((project / "production/review-manifest.json").read_text())
        decisions = json.loads(
            (project / "production/review-decisions.json").read_text()
        )
    except (OSError, json.JSONDecodeError):
        return False
    return bool(
        decisions.get("ok")
        and decisions.get("finalized")
        and decisions.get("review_identity_sha256")
        == manifest.get("review_identity_sha256")
    )


def serve_review(project: Path, host: str, port: int) -> None:
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("review server is loopback-only")
    build_review(project)

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args: Any, **kwargs: Any):
            super().__init__(
                *args, directory=str((project / "staging").resolve()), **kwargs
            )

    ThreadingHTTPServer((host, port), Handler).serve_forever()
