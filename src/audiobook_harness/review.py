from __future__ import annotations

import hashlib
import html
import json
import secrets
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .feedback import append_observations, validate_decisions
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


def finalize_review(project: Path, decisions: list[dict[str, Any]]) -> dict[str, Any]:
    production = project / "production"
    manifest = json.loads((production / "review-manifest.json").read_text())
    decisions = validate_decisions(decisions)
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
    append_observations(project, manifest, decisions)
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
            links = " ".join(
                f'<audio controls preload="none" src="/{html.escape(str(path))}"></audio>'
                for path in row.get("files", [])
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
                self._respond(200, value)
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
