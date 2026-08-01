from __future__ import annotations

import hashlib
import html
import json
import os
import secrets
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from mimetypes import guess_type
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote, urlparse

from .project import load_project, write_json
from .review import build_review, finalize_review, review_status, validate_decisions


@dataclass(frozen=True)
class ReviewProject:
    project_id: str
    root: Path
    display_name: str


def load_projects(workspace: Path, config: Path | None = None) -> list[ReviewProject]:
    workspace = workspace.resolve()
    config = (config or workspace / "review-center.json").resolve()
    if not config.is_file() or not config.is_relative_to(workspace):
        raise ValueError(f"Missing or unsafe Review Center config: {config}")
    value = json.loads(config.read_text(encoding="utf-8"))
    entries = value.get("projects", []) if isinstance(value, dict) else []
    if not isinstance(entries, list) or not entries:
        raise ValueError("review-center.json must contain a non-empty projects list")
    projects: list[ReviewProject] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("Review Center project entries must be objects")
        project_id = str(entry.get("id", "")).strip()
        if not project_id or any(
            char not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for char in project_id
        ):
            raise ValueError(f"Invalid project id: {project_id!r}")
        root = (workspace / str(entry.get("path", ""))).resolve()
        if not root.is_relative_to(workspace) or not (root / "project.yaml").is_file():
            raise ValueError(f"Invalid project path for {project_id}: {root}")
        project = load_project(root)
        display = str(entry.get("display_name") or project.get("title") or project_id)
        if any(item.project_id == project_id for item in projects):
            raise ValueError(f"Duplicate project id: {project_id}")
        projects.append(ReviewProject(project_id, root, display))
    return projects


def _json_body(handler: SimpleHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0"))
    if length <= 0 or length > 2 * 1024 * 1024:
        raise ValueError("invalid request body")
    value = json.loads(handler.rfile.read(length).decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("JSON body must be an object")
    return value


def _send(
    handler: SimpleHTTPRequestHandler, status: int, content_type: str, payload: bytes
) -> None:
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(payload)))
    handler.end_headers()
    handler.wfile.write(payload)


def _send_json(
    handler: SimpleHTTPRequestHandler, value: object, status: int = 200
) -> None:
    _send(
        handler,
        status,
        "application/json; charset=utf-8",
        json.dumps(value, ensure_ascii=False).encode(),
    )


def _review_page(project: ReviewProject, manifest: dict[str, Any], token: str) -> str:
    base = f"/review-center/{quote(project.project_id)}/"
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
    options = "".join(f"<option>{html.escape(value)}</option>" for value in categories)
    sections: list[str] = []
    for row in manifest.get("items", []):
        item_id = str(row.get("id", ""))
        media = [
            f"{base}media/{quote(str(path), safe='/')}" for path in row.get("files", [])
        ]
        if row.get("source_audio"):
            media.append(f"{base}api/unit-audio/{quote(str(item_id), safe='')}")
        mastered = row.get("mastered_context") or {}
        if mastered.get("audio"):
            media.insert(
                0,
                f"{base}media/{quote(str(mastered['audio']), safe='/')}#t={mastered.get('excerpt_start_seconds', 0)},{mastered.get('excerpt_end_seconds', 0)}",
            )
        audio = "".join(
            f'<audio controls preload="none" src="{html.escape(path)}"></audio>'
            for path in media
        )
        sections.append(f'''<section data-id="{html.escape(item_id)}"><h2>{html.escape(item_id)}</h2>{audio}
<select class="decision"><option value="">Choose</option><option>approve</option><option>reject</option><option>uncertain</option></select>
<select class="category"><option value="">Defect category</option>{options}</select><input class="note" placeholder="Note (required for other)"></section>''')
    data = json.dumps(manifest, ensure_ascii=False).replace("</", "<\\/")
    return f"""<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Review Center · {html.escape(project.display_name)}</title>
<style>body{{font:16px system-ui;max-width:980px;margin:auto;padding:24px;background:#0d1117;color:#edf3f8}}a{{color:#69a7d8}}section{{padding:16px 0;border-bottom:1px solid #334}}audio{{display:block;width:100%;margin:8px 0}}select,input,button{{font:inherit;margin:4px;padding:8px}}input{{min-width:320px}}.status{{position:sticky;top:0;background:#17202b;padding:10px;border-radius:8px}}</style>
<p><a href="/review-center/">← All projects</a></p><h1>Review Center</h1><p>Project: <strong>{html.escape(project.display_name)}</strong></p><div class="status" id="status">Decisions save locally.</div>{"".join(sections)}<button id="finalize">Finalize review</button>
<script>const token={json.dumps(token)},manifest={data},base={json.dumps(base)};const headers={{"Content-Type":"application/json","X-Audiobook-Review-Token":token}};
function decisions(){{return [...document.querySelectorAll("section")].filter(s=>s.querySelector(".decision").value).map(s=>({{id:s.dataset.id,decision:s.querySelector(".decision").value,defect_category:s.querySelector(".category").value||undefined,note:s.querySelector(".note").value||undefined}}));}}
let timer;document.addEventListener("input",()=>{{clearTimeout(timer);timer=setTimeout(async()=>{{const r=await fetch(base+"api/review-draft",{{method:"PUT",headers,body:JSON.stringify({{decisions:decisions()}})}});document.querySelector("#status").textContent=r.ok?"Saved locally.":"Save error."}},250)}});
fetch(base+"api/review-draft").then(r=>r.json()).then(v=>{{for(const d of v.decisions||[]){{const s=document.querySelector(`section[data-id="${{CSS.escape(d.id)}}"]`);if(!s)continue;s.querySelector(".decision").value=d.decision||"";s.querySelector(".category").value=d.defect_category||"";s.querySelector(".note").value=d.note||""}}}});
document.querySelector("#finalize").onclick=async()=>{{const r=await fetch(base+"api/finalize-review",{{method:"POST",headers,body:JSON.stringify({{decisions:decisions()}})}});const v=await r.json();document.querySelector("#status").textContent=v.ok?"Finalized and approved.":(v.error||"Finalize failed.")}};
async function refresh(){{const r=await fetch(base+"api/status",{{cache:"no-store"}});if(!r.ok)return;const v=await r.json();const enabled=Boolean(v.reviewer_action?.enabled);document.querySelector("#finalize").disabled=!enabled;document.querySelectorAll("audio,select,input").forEach(x=>x.disabled=!enabled);document.querySelector("#status").textContent=enabled?"Current review media is ready. Decisions save locally.":`Reviewer action: ${{v.reviewer_action?.code||"unavailable"}}`}}refresh();setInterval(refresh,5000);</script>"""


def chooser(projects: list[ReviewProject]) -> str:
    cards = "".join(
        f'<li><a href="/review-center/{quote(p.project_id)}/">{html.escape(p.display_name)}</a></li>'
        for p in projects
    )
    return f"""<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Review Center</title><style>body{{font:16px system-ui;max-width:760px;margin:3rem auto;padding:24px;background:#0d1117;color:#edf3f8}}a{{color:#69a7d8}}li{{margin:1rem 0;padding:16px;background:#17202b;border:1px solid #334;border-radius:10px}}</style><h1>Review Center</h1><p>Choose a project to review.</p><ul>{cards}</ul>"""


def serve_review_center(
    workspace: Path, host: str, port: int, config: Path | None = None
) -> None:
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("Review Center is loopback-only")
    projects = load_projects(workspace, config)
    tokens = {project.project_id: secrets.token_urlsafe(32) for project in projects}

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args: Any, **kwargs: Any):
            super().__init__(*args, directory=str(workspace), **kwargs)

        def project(self, project_id: str) -> ReviewProject:
            for project in projects:
                if project.project_id == project_id:
                    return project
            raise FileNotFoundError(project_id)

        def route_parts(self) -> list[str]:
            return [part for part in urlparse(self.path).path.split("/") if part]

        def do_GET(self) -> None:
            parts = self.route_parts()
            if parts == ["review-center"]:
                _send(self, 200, "text/html; charset=utf-8", chooser(projects).encode())
                return
            if len(parts) >= 2 and parts[0] == "review-center":
                try:
                    project = self.project(unquote(parts[1]))
                except FileNotFoundError:
                    self.send_error(404)
                    return
                if len(parts) == 2:
                    _send(
                        self,
                        200,
                        "text/html; charset=utf-8",
                        _review_page(
                            project,
                            build_review(project.root),
                            tokens[project.project_id],
                        ).encode(),
                    )
                    return
                if parts[2:] == ["api", "status"]:
                    _send_json(self, review_status(project.root))
                    return
                if parts[2:] == ["api", "review-manifest"]:
                    _send_json(self, build_review(project.root))
                    return
                if parts[2:] == ["api", "review-draft"]:
                    path = project.root / "production/review-draft.json"
                    value = (
                        json.loads(path.read_text())
                        if path.is_file()
                        else {"decisions": []}
                    )
                    current = (
                        json.loads(
                            (
                                project.root / "production/review-manifest.json"
                            ).read_text()
                        ).get("review_identity_sha256")
                        if (project.root / "production/review-manifest.json").is_file()
                        else None
                    )
                    if value.get("review_identity_sha256") != current:
                        value = {
                            "decisions": [],
                            "stale": True,
                            "review_identity_sha256": current,
                        }
                    _send_json(self, value)
                    return
                if len(parts) >= 4 and parts[2] == "media":
                    relative = Path(*[unquote(value) for value in parts[3:]])
                    target = (project.root / "staging" / relative).resolve()
                    root = (project.root / "staging").resolve()
                    if not target.is_relative_to(root) or not target.is_file():
                        self.send_error(404)
                        return
                    payload = target.read_bytes()
                    _send(
                        self,
                        200,
                        guess_type(target.name)[0] or "application/octet-stream",
                        payload,
                    )
                    return
                if (
                    parts[2:]
                    and parts[2] == "api"
                    and len(parts) == 5
                    and parts[3] == "unit-audio"
                ):
                    unit_id = unquote(parts[4])
                    try:
                        verification = json.loads(
                            (project.root / "production/verification.json").read_text()
                        )
                        row = next(
                            item
                            for item in verification.get("takes", [])
                            if str(item.get("id")) == unit_id
                        )
                        target = (project.root / str(row["file"])).resolve()
                        if (
                            not target.is_relative_to(project.root.resolve())
                            or not target.is_file()
                        ):
                            raise FileNotFoundError(unit_id)
                        _send(
                            self,
                            200,
                            guess_type(target.name)[0] or "application/octet-stream",
                            target.read_bytes(),
                        )
                        return
                    except (
                        OSError,
                        ValueError,
                        StopIteration,
                        json.JSONDecodeError,
                        KeyError,
                    ):
                        self.send_error(404)
                        return
                self.send_error(404)
                return
            self.send_error(404)

        def authorized(self, project: ReviewProject) -> bool:
            return secrets.compare_digest(
                self.headers.get("X-Audiobook-Review-Token", ""),
                tokens[project.project_id],
            )

        def do_PUT(self) -> None:
            parts = self.route_parts()
            if (
                len(parts) != 4
                or parts[0] != "review-center"
                or parts[2:] != ["api", "review-draft"]
            ):
                self.send_error(404)
                return
            try:
                project = self.project(unquote(parts[1]))
            except FileNotFoundError:
                self.send_error(404)
                return
            if not self.authorized(project):
                _send_json(self, {"ok": False, "error": "invalid review session"}, 403)
                return
            try:
                value = _json_body(self)
                decisions = validate_decisions(list(value.get("decisions", [])))
                manifest = json.loads(
                    (project.root / "production/review-manifest.json").read_text()
                )
                write_json(
                    project.root / "production/review-draft.json",
                    {
                        "version": 2,
                        "review_identity_sha256": manifest["review_identity_sha256"],
                        "decisions": decisions,
                        "saved": True,
                    },
                )
                _send_json(self, {"ok": True})
            except (ValueError, OSError, json.JSONDecodeError) as error:
                _send_json(self, {"ok": False, "error": str(error)}, 400)

        def do_POST(self) -> None:
            parts = self.route_parts()
            if (
                len(parts) != 4
                or parts[0] != "review-center"
                or parts[2:] != ["api", "finalize-review"]
            ):
                self.send_error(404)
                return
            try:
                project = self.project(unquote(parts[1]))
            except FileNotFoundError:
                self.send_error(404)
                return
            if not self.authorized(project):
                _send_json(self, {"ok": False, "error": "invalid review session"}, 403)
                return
            try:
                _send_json(
                    self,
                    finalize_review(
                        project.root, list(_json_body(self).get("decisions", []))
                    ),
                )
            except (ValueError, OSError, json.JSONDecodeError) as error:
                _send_json(self, {"ok": False, "error": str(error)}, 400)

    ThreadingHTTPServer((host, port), Handler).serve_forever()


def _pid_path(workspace: Path, config: Path | None, port: int) -> Path:
    key = hashlib.sha256(
        f"{workspace.resolve()}:{(config or workspace / 'review-center.json').resolve()}:{port}".encode()
    ).hexdigest()[:16]
    return Path(tempfile.gettempdir()) / f"audiobook-harness-review-center-{key}.pid"


def _pid_record(path: Path) -> tuple[int, dict[str, Any]] | None:
    """Read a controller record, accepting the pre-0.5 plain-PID format."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(value, dict):
            return int(value["pid"]), value
        return int(value), {}
    except (OSError, ValueError, TypeError, json.JSONDecodeError, KeyError):
        path.unlink(missing_ok=True)
        return None


def _process_matches(pid: int, workspace: Path) -> bool:
    """Avoid treating an unrelated process reusing a stale PID as our server."""
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return False
    command = result.stdout.strip()
    return (
        result.returncode == 0
        and "review-center serve" in command
        and str(workspace) in command
    )


def control(
    action: str, workspace: Path, host: str, port: int, config: Path | None = None
) -> dict[str, Any]:
    pid_file = _pid_path(workspace, config, port)
    if action == "status":
        if not pid_file.is_file():
            return {"ok": False, "state": "stopped"}
        record = _pid_record(pid_file)
        if record is None:
            return {"ok": False, "state": "stopped"}
        pid, _ = record
        try:
            os.kill(pid, 0)
        except OSError:
            pid_file.unlink(missing_ok=True)
            return {"ok": False, "state": "stopped"}
        if not _process_matches(pid, workspace):
            pid_file.unlink(missing_ok=True)
            return {"ok": False, "state": "stopped"}
        return {
            "ok": True,
            "state": "running",
            "pid": pid,
            "url": f"http://{host}:{port}/review-center/",
        }
    if action == "stop":
        if pid_file.is_file():
            record = _pid_record(pid_file)
            if record is not None:
                pid, _ = record
                if _process_matches(pid, workspace):
                    try:
                        os.kill(pid, 15)
                    except OSError:
                        pass
            pid_file.unlink(missing_ok=True)
        return {"ok": True, "state": "stopped"}
    if action == "restart":
        control("stop", workspace, host, port, config)
        action = "start"
    if action == "start":
        existing = control("status", workspace, host, port, config)
        if existing.get("ok"):
            return existing
        log = Path(tempfile.gettempdir()) / "audiobook-harness-review-center.log"
        command = [
            sys.executable,
            "-m",
            "audiobook_harness.cli",
            "review-center",
            "serve",
            "--workspace-root",
            str(workspace),
            "--host",
            host,
            "--port",
            str(port),
        ]
        if config:
            command += ["--config", str(config)]
        with log.open("ab") as handle:
            process = subprocess.Popen(
                command,
                stdout=handle,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                close_fds=True,
            )
        pid_file.write_text(
            json.dumps(
                {
                    "pid": process.pid,
                    "workspace": str(workspace),
                    "port": port,
                }
            ),
            encoding="utf-8",
        )
        return {
            "ok": True,
            "state": "starting",
            "pid": process.pid,
            "url": f"http://{host}:{port}/review-center/",
        }
    raise ValueError(f"unknown Review Center action: {action}")
