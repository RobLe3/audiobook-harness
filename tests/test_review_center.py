import json
import http.client
import threading
from contextlib import contextmanager
from pathlib import Path

import audiobook_harness.review_center as review_center_module

from audiobook_harness.review_center import (
    REVIEW_CENTER_STATUS_VERSION,
    ReviewProject,
    _review_page,
    _pid_path,
    control,
    create_review_center_server,
    load_projects,
)


def test_review_page_has_status_schema_reload_handshake(tmp_path: Path):
    page = _review_page(ReviewProject("book", tmp_path, "Book"), {"items": []}, "token")
    assert f"statusSchema={REVIEW_CENTER_STATUS_VERSION}" in page
    assert "review-center-schema-reload" in page
    assert "review_center_schema" in page


def test_load_projects_is_explicit_and_uses_project_titles(tmp_path: Path):
    project = tmp_path / "book"
    project.mkdir()
    (project / "project.yaml").write_text("title: Example Title\n", encoding="utf-8")
    (tmp_path / "review-center.json").write_text(
        json.dumps({"projects": [{"id": "book", "path": "book"}]}),
        encoding="utf-8",
    )
    projects = load_projects(tmp_path)
    assert projects[0].project_id == "book"
    assert projects[0].display_name == "Example Title"
    assert projects[0].automation_enabled is False


def test_load_projects_rejects_paths_outside_workspace(tmp_path: Path):
    (tmp_path / "review-center.json").write_text(
        json.dumps({"projects": [{"id": "book", "path": "../outside"}]}),
        encoding="utf-8",
    )
    try:
        load_projects(tmp_path)
    except ValueError as error:
        assert "Invalid project path" in str(error)
    else:
        raise AssertionError("unsafe project path was accepted")


def test_review_center_start_is_idempotent_while_another_start_holds_lock(
    tmp_path: Path,
):
    lock = _pid_path(tmp_path, None, 8765).with_suffix(".pid.lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("starting")
    result = control("start", tmp_path, "127.0.0.1", 8765)
    assert result["ok"]
    assert result["state"] == "starting"
    assert "already in progress" in result["detail"]


def test_bare_review_center_host_redirects_to_project_chooser(tmp_path: Path):
    project = tmp_path / "book"
    project.mkdir()
    (project / "project.yaml").write_text("title: Example Title\n", encoding="utf-8")
    (tmp_path / "review-center.json").write_text(
        json.dumps({"projects": [{"id": "book", "path": "book"}]}),
        encoding="utf-8",
    )
    server = create_review_center_server(tmp_path, "127.0.0.1", 0)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port)
        connection.request("HEAD", "/")
        response = connection.getresponse()
        assert response.status == 302
        assert response.getheader("Location") == "/review-center/"
        assert response.getheader("Cache-Control") == "no-store, max-age=0"
        connection.close()
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)


def test_review_draft_returns_conflict_while_production_owns_project(
    tmp_path: Path, monkeypatch
):
    """The local API must reject a competing review write without mutation."""
    project = tmp_path / "book"
    project.mkdir()
    (project / "project.yaml").write_text("title: Example Title\n", encoding="utf-8")
    (tmp_path / "review-center.json").write_text(
        json.dumps({"projects": [{"id": "book", "path": "book"}]}),
        encoding="utf-8",
    )

    @contextmanager
    def locked(_project: Path):
        raise RuntimeError("Project is locked by another production process")
        yield

    monkeypatch.setattr(review_center_module, "project_writer_lock", locked)
    monkeypatch.setattr(
        review_center_module.secrets, "token_urlsafe", lambda _: "token"
    )
    server = create_review_center_server(tmp_path, "127.0.0.1", 0)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port)
        connection.request(
            "PUT",
            "/review-center/book/api/review-draft",
            body=json.dumps({"decisions": []}),
            headers={
                "Content-Type": "application/json",
                "X-Audiobook-Review-Token": "token",
            },
        )
        response = connection.getresponse()
        body = json.loads(response.read())
        assert response.status == 409
        assert body["ok"] is False
        assert "locked" in body["error"].lower()
        connection.close()
        assert not (project / "production/review-draft.json").exists()
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)
