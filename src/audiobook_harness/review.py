from __future__ import annotations

import hashlib
import html
import json
import secrets
from mimetypes import guess_type
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from . import __version__
from .feedback import append_observations, compile_feedback, validate_decisions
from .parity import project_profile_identity
from .project import write_json
from .status import asr_activity, owner_activity


def _canonical(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def review_item_identity(item: dict[str, Any]) -> str:
    """Bind a decision to one review item, not to the surrounding page."""

    return _canonical(
        {
            key: item.get(key)
            for key in (
                "id",
                "kind",
                "audio_sha256",
                "files",
                "file_evidence",
                "published_text",
                "spoken_text",
                "source_audio",
                "mastered_context",
            )
        }
    )


def carry_forward_decisions(
    old_manifest: dict[str, Any],
    old_decisions: dict[str, Any],
    new_manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    """Reuse only decisions whose exact item-level review identity survived."""

    old_items = {
        str(row.get("id")): row
        for row in old_manifest.get("items", [])
        if isinstance(row, dict) and row.get("id")
    }
    new_items = {
        str(row.get("id")): row
        for row in new_manifest.get("items", [])
        if isinstance(row, dict) and row.get("id")
    }
    carried = []
    for decision in old_decisions.get("decisions", []):
        if not isinstance(decision, dict):
            continue
        item_id = str(decision.get("id", ""))
        old_item, new_item = old_items.get(item_id), new_items.get(item_id)
        if not old_item or not new_item:
            continue
        old_identity = old_item.get(
            "review_item_identity_sha256"
        ) or review_item_identity(old_item)
        if old_identity != new_item.get("review_item_identity_sha256"):
            continue
        carried.append({**decision, "review_item_identity_sha256": old_identity})
    return carried


def build_review(project: Path, stage: Path | None = None) -> dict[str, Any]:
    root = (stage or project / "staging").resolve()
    production = project / "production"
    old_manifest_path = production / "review-manifest.json"
    old_decisions_path = production / "review-decisions.json"
    old_manifest = (
        json.loads(old_manifest_path.read_text(encoding="utf-8"))
        if old_manifest_path.is_file()
        else {}
    )
    old_decisions = (
        json.loads(old_decisions_path.read_text(encoding="utf-8"))
        if old_decisions_path.is_file()
        else {}
    )
    staged = json.loads((root / "stage-manifest.json").read_text())
    risk_path = production / "tts-risk-map.json"
    risks = (
        json.loads(risk_path.read_text()).get("units", [])
        if risk_path.is_file()
        else []
    )
    mandatory = {str(row["unit"]) for row in risks if row.get("mandatory_review")}
    analysis_path = production / "analysis.json"
    analysis = (
        json.loads(analysis_path.read_text(encoding="utf-8"))
        if analysis_path.is_file()
        else {"chapters": []}
    )
    verification_path = production / "verification.json"
    verification = (
        json.loads(verification_path.read_text(encoding="utf-8"))
        if verification_path.is_file()
        else {"takes": []}
    )
    take_by_id = {
        str(row["id"]): row for row in verification.get("takes", []) if row.get("id")
    }
    unit_rows = [
        unit
        for chapter in analysis.get("chapters", [])
        for unit in chapter.get("units", [])
    ]
    unit_by_id = {str(row["id"]): row for row in unit_rows}
    ordered_ids = [str(row["id"]) for row in staged.get("ordered_units", [])]
    speaker_map = _map_units(production / "dialogue-speaker-map.json")
    prosody_map = _map_units(production / "discourse-prosody-map.json")
    energy_map = _map_units(production / "speaker-energy-map.json")
    risk_map = {str(row["unit"]): row for row in risks}
    chapter_files = {
        str(row["chapter"]): [str(item["file"]) for item in row.get("files", [])]
        for row in staged.get("outputs", [])
    }
    chapter_offsets: dict[str, float] = {}
    cue_timings: dict[str, tuple[float, float]] = {}
    for unit_id in ordered_ids:
        take = take_by_id.get(unit_id, {})
        chapter = str(
            take.get("chapter", unit_by_id.get(unit_id, {}).get("chapter", ""))
        )
        start = chapter_offsets.get(chapter, 0.0)
        end = start + float(take.get("duration_seconds", 0.0))
        cue_timings[unit_id] = (start, end)
        chapter_offsets[chapter] = end
    items = [
        {
            "id": f"chapter:{row['chapter']}",
            "kind": "assembled_chapter",
            "files": [f["file"] for f in row["files"]],
            "file_evidence": row["files"],
            "mandatory": True,
        }
        for row in staged["outputs"]
    ]
    for unit in staged.get("ordered_units", []):
        if str(unit["id"]) in mandatory:
            unit_id = str(unit["id"])
            index = ordered_ids.index(unit_id)
            source = unit_by_id.get(unit_id, {})
            take = take_by_id.get(unit_id, {})
            chapter = str(unit.get("chapter", take.get("chapter", "")))
            start, end = cue_timings.get(unit_id, (0.0, 0.0))
            mastered_file = next(
                (
                    path
                    for path in chapter_files.get(chapter, [])
                    if Path(path).suffix.lower() in {".m4a", ".mp3", ".flac"}
                ),
                None,
            )
            items.append(
                {
                    "id": unit_id,
                    "kind": "high_risk_unit",
                    "audio_sha256": unit["audio_sha256"],
                    "mandatory": True,
                    "published_text": source.get("text", take.get("text")),
                    "spoken_text": take.get("text"),
                    "previous_context": (
                        unit_by_id.get(ordered_ids[index - 1], {}).get("text")
                        if index
                        else None
                    ),
                    "next_context": (
                        unit_by_id.get(ordered_ids[index + 1], {}).get("text")
                        if index + 1 < len(ordered_ids)
                        else None
                    ),
                    "source_audio": f"/api/unit-audio/{unit_id}",
                    "mastered_context": {
                        "audio": mastered_file,
                        "excerpt_start_seconds": max(0.0, start - 1.0),
                        "excerpt_end_seconds": end + 1.0,
                    }
                    if mastered_file
                    else None,
                    "machine_evidence": {
                        "speaker": speaker_map.get(unit_id),
                        "prosody": prosody_map.get(unit_id),
                        "energy": energy_map.get(unit_id),
                        "risk": risk_map.get(unit_id),
                        "primary_wer": take.get("primary_wer"),
                        "secondary_wer": take.get("secondary_wer"),
                    },
                }
            )
    for item in items:
        item["review_item_identity_sha256"] = review_item_identity(item)
    manifest: dict[str, Any] = {
        "version": 3,
        "audiobook_harness_version": __version__,
        "stage_manifest_sha256": _canonical(staged),
        "items": items,
        "cues": [row for row in items if row["kind"] == "high_risk_unit"],
        "decision_values": ["approve", "reject", "uncertain"],
        "defect_categories": [
            "spoken_form",
            "pause",
            "pronunciation",
            "mix_or_loudness",
            "performance",
            "speaker_or_mode",
            "stretch_or_timing",
            "other",
        ],
        "playback_contract": "mastered_context_default_isolated_diagnostic",
    }
    manifest["review_identity_sha256"] = _canonical(manifest)
    write_json(production / "review-manifest.json", manifest)
    carried = carry_forward_decisions(old_manifest, old_decisions, manifest)
    if carried:
        write_json(
            production / "review-draft.json",
            {
                "version": 3,
                "review_identity_sha256": manifest["review_identity_sha256"],
                "decisions": carried,
                "carried_forward": True,
            },
        )
    return manifest


def _map_units(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {
        str(row.get("unit", row.get("id"))): row
        for row in value.get("units", [])
        if isinstance(row, dict) and (row.get("unit") or row.get("id"))
    }


def finalize_review(project: Path, decisions: list[dict[str, Any]]) -> dict[str, Any]:
    production = project / "production"
    manifest = json.loads((production / "review-manifest.json").read_text())
    decisions = validate_decisions(decisions)
    by_id = {str(row.get("id")): str(row.get("decision")) for row in decisions}
    required = [str(row["id"]) for row in manifest["items"] if row.get("mandatory")]
    unresolved = [item for item in required if by_id.get(item) != "approve"]
    report = {
        "version": 2,
        "audiobook_harness_version": __version__,
        "project_profile_sha256": project_profile_identity(project),
        "review_identity_sha256": manifest["review_identity_sha256"],
        "decisions": decisions,
        "unresolved": unresolved,
        "finalized": True,
        "ok": not unresolved,
    }
    report["decisions_sha256"] = _canonical(decisions)
    write_json(production / "review-decisions.json", report)
    append_observations(project, manifest, decisions)
    report["feedback"] = compile_feedback(project)
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


def review_status(project: Path) -> dict[str, Any]:
    """Return identity-safe reviewer instructions from the current local state."""

    production = project / "production"

    def read(name: str) -> dict[str, Any]:
        try:
            value = json.loads((production / name).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return value if isinstance(value, dict) else {}

    run = read("run-status.json")
    manifest = read("review-manifest.json")
    decisions = read("review-decisions.json")
    draft = read("review-draft.json")
    owner, _detail = owner_activity(run)
    current = manifest.get("review_identity_sha256")
    authoritative = decisions.get("review_identity_sha256")
    draft_identity = draft.get("review_identity_sha256")
    state = str(run.get("state", "not_started"))
    if state == "running" and owner == "active":
        action = "wait_for_generation"
        enabled = False
    elif state == "failed":
        action = "generation_blocked"
        enabled = False
    elif not current:
        action = "await_review_media"
        enabled = False
    elif decisions.get("ok") and authoritative == current:
        action = "none"
        enabled = False
    elif decisions.get("finalized") and authoritative == current:
        action = "corrections_queued"
        enabled = False
    elif draft.get("decisions") and draft_identity == current:
        action = "complete_decisions"
        enabled = True
    else:
        action = "listen_and_finalize"
        enabled = True
    return {
        "version": 1,
        "audiobook_harness_version": __version__,
        "generation": {
            "state": state,
            "phase": run.get("phase"),
            "owner": owner,
        },
        "current_review_identity_sha256": current,
        "authoritative_review_identity_sha256": authoritative,
        "draft_review_identity_sha256": draft_identity,
        "draft_matches_current_identity": bool(current and draft_identity == current),
        "review_available": bool(current),
        "reviewer_action": {"code": action, "enabled": enabled},
        "asr": asr_activity(project, worker_active=owner == "active"),
        "review_only": True,
    }


def serve_review(project: Path, host: str, port: int) -> None:
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("review server is loopback-only")
    manifest = build_review(project)
    session_token = secrets.token_urlsafe(32)

    def review_page() -> str:
        items = []
        categories = [
            "spoken_form",
            "pause",
            "pronunciation",
            "mix_or_loudness",
            "performance",
            "speaker_or_mode",
            "stretch_or_timing",
            "other",
        ]
        options = "".join(f"<option>{value}</option>" for value in categories)
        for row in manifest.get("items", []):
            media = list(row.get("files", []))
            if row.get("source_audio"):
                media.append(str(row["source_audio"]))
            mastered = row.get("mastered_context") or {}
            if mastered.get("audio"):
                media.insert(
                    0,
                    f"/{mastered['audio']}#t={mastered['excerpt_start_seconds']},{mastered['excerpt_end_seconds']}",
                )
            links = " ".join(
                f'<audio controls preload="none" src="{html.escape(str(path))}"></audio>'
                for path in media
            )
            item_id = html.escape(str(row["id"]))
            items.append(
                f"""<section data-id="{item_id}">
<h2>{item_id}</h2>{links}
<select class="decision"><option value="">Choose</option><option>approve</option><option>reject</option><option>uncertain</option></select>
<select class="category"><option value="">Defect category</option>{options}</select>
<input class="note" placeholder="Note (required for other)">
</section>"""
            )
        data = json.dumps(manifest, ensure_ascii=False).replace("</", "<\\/")
        return f"""<!doctype html><meta charset="utf-8"><title>Audiobook review</title>
<style>body{{font:16px system-ui;max-width:980px;margin:auto;padding:24px}}section{{padding:16px 0;border-bottom:1px solid #ccc}}audio{{display:block;width:100%;margin:8px 0}}select,input,button{{font:inherit;margin:4px;padding:8px}}input{{min-width:320px}}.status{{position:sticky;top:0;background:#fff;padding:8px}}</style>
<h1>Local audiobook review</h1><div class="status" id="status">Decisions save locally.</div>
{"".join(items)}<button id="finalize">Finalize review</button>
<script>const manifest={data};const token={json.dumps(session_token)};
const headers={{"Content-Type":"application/json","X-Audiobook-Review-Token":token}};
function decisions(){{return [...document.querySelectorAll("section")].filter(s=>s.querySelector(".decision").value).map(s=>({{id:s.dataset.id,decision:s.querySelector(".decision").value,defect_category:s.querySelector(".category").value||undefined,note:s.querySelector(".note").value||undefined}}));}}
let timer;document.addEventListener("input",()=>{{clearTimeout(timer);timer=setTimeout(async()=>{{const r=await fetch("/api/review-draft",{{method:"PUT",headers,body:JSON.stringify({{decisions:decisions()}})}});document.querySelector("#status").textContent=r.ok?"Saved locally.":"Save error."; }},250);}});
fetch("/api/review-draft").then(r=>r.json()).then(v=>{{for(const d of v.decisions||[]){{const s=document.querySelector(`section[data-id="${{CSS.escape(d.id)}}"]`);if(!s)continue;s.querySelector(".decision").value=d.decision||"";s.querySelector(".category").value=d.defect_category||"";s.querySelector(".note").value=d.note||"";}}}});
document.querySelector("#finalize").onclick=async()=>{{const r=await fetch("/api/finalize-review",{{method:"POST",headers,body:JSON.stringify({{decisions:decisions()}})}});const v=await r.json();document.querySelector("#status").textContent=v.ok?"Finalized and approved.":(v.error||"Finalized with unresolved items.");}};
async function refreshStatus(){{const r=await fetch("/api/status",{{cache:"no-store"}});if(!r.ok)return;const v=await r.json();const enabled=Boolean(v.reviewer_action?.enabled);document.querySelector("#finalize").disabled=!enabled;document.querySelectorAll("audio,select,input").forEach(x=>x.disabled=!enabled);document.querySelector("#status").textContent=enabled?"Current review media is ready. Decisions save locally.":`Reviewer action: ${{v.reviewer_action?.code||"unavailable"}}`;}}
refreshStatus();setInterval(refreshStatus,5000);
</script>"""

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args: Any, **kwargs: Any):
            super().__init__(
                *args, directory=str((project / "staging").resolve()), **kwargs
            )

        def _json_body(self) -> Any:
            length = int(self.headers.get("Content-Length", "0"))
            return json.loads(self.rfile.read(length).decode("utf-8"))

        def _respond(self, status: int, value: object) -> None:
            payload = json.dumps(value, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _authorized(self) -> bool:
            return secrets.compare_digest(
                self.headers.get("X-Audiobook-Review-Token", ""), session_token
            )

        def do_GET(self) -> None:
            route = urlparse(self.path).path
            if route == "/":
                payload = review_page().encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return
            if route == "/api/review-draft":
                path = project / "production/review-draft.json"
                value = (
                    json.loads(path.read_text())
                    if path.is_file()
                    else {"decisions": []}
                )
                try:
                    current = json.loads(
                        (project / "production/review-manifest.json").read_text()
                    ).get("review_identity_sha256")
                except (OSError, json.JSONDecodeError):
                    current = None
                if value.get("review_identity_sha256") != current:
                    value = {
                        "decisions": [],
                        "stale": True,
                        "review_identity_sha256": current,
                    }
                self._respond(200, value)
                return
            if route == "/api/status":
                self._respond(200, review_status(project))
                return
            if route == "/api/review-manifest":
                try:
                    value = json.loads(
                        (project / "production/review-manifest.json").read_text()
                    )
                    self._respond(200, value)
                except (OSError, json.JSONDecodeError):
                    self._respond(404, {"ok": False, "error": "review unavailable"})
                return
            if route.startswith("/api/unit-audio/"):
                unit_id = route.rsplit("/", 1)[-1]
                try:
                    verification = json.loads(
                        (project / "production/verification.json").read_text()
                    )
                    row = next(
                        item
                        for item in verification.get("takes", [])
                        if str(item.get("id")) == unit_id
                    )
                    path = (project / str(row["file"])).resolve()
                    if not path.is_relative_to(project.resolve()) or not path.is_file():
                        raise FileNotFoundError(unit_id)
                    payload = path.read_bytes()
                    self.send_response(200)
                    self.send_header(
                        "Content-Type",
                        guess_type(path.name)[0] or "application/octet-stream",
                    )
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                except (OSError, json.JSONDecodeError, StopIteration, KeyError):
                    self.send_error(404)
                return
            super().do_GET()

        def do_PUT(self) -> None:
            if urlparse(self.path).path != "/api/review-draft":
                self._respond(404, {"ok": False})
                return
            if not self._authorized():
                self._respond(403, {"ok": False, "error": "invalid review session"})
                return
            try:
                value = self._json_body()
                decisions = validate_decisions(list(value.get("decisions", [])))
                manifest = json.loads(
                    (project / "production/review-manifest.json").read_text()
                )
                report = {
                    "version": 2,
                    "review_identity_sha256": manifest["review_identity_sha256"],
                    "decisions": decisions,
                    "saved": True,
                }
                write_json(project / "production/review-draft.json", report)
                self._respond(200, {"ok": True})
            except (ValueError, json.JSONDecodeError, OSError) as error:
                self._respond(400, {"ok": False, "error": str(error)})

        def do_POST(self) -> None:
            if urlparse(self.path).path != "/api/finalize-review":
                self._respond(404, {"ok": False})
                return
            if not self._authorized():
                self._respond(403, {"ok": False, "error": "invalid review session"})
                return
            try:
                value = self._json_body()
                report = finalize_review(project, list(value.get("decisions", [])))
                self._respond(200, report)
            except (ValueError, json.JSONDecodeError, OSError) as error:
                self._respond(400, {"ok": False, "error": str(error)})

    ThreadingHTTPServer((host, port), Handler).serve_forever()
