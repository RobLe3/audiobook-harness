import json
from pathlib import Path

from audiobook_harness.review_center import load_projects


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
