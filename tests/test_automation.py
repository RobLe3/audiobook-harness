import json
from pathlib import Path
from types import SimpleNamespace

import audiobook_harness.automation as automation
import audiobook_harness.review_center as review_center


def _project(tmp_path: Path) -> Path:
    project = tmp_path / "book"
    (project / "production").mkdir(parents=True)
    (project / "project.yaml").write_text("title: Book\n", encoding="utf-8")
    return project


def test_convergence_stops_when_failed_repair_changes_no_evidence(
    tmp_path: Path, monkeypatch
):
    project = _project(tmp_path)
    monkeypatch.setattr(
        automation,
        "review_status",
        lambda _project: {"reviewer_action": {"code": "corrections_queued"}},
    )
    monkeypatch.setattr(
        automation.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=2, stdout="", stderr="failed"
        ),
    )
    result = automation.converge_project(project, maximum_iterations=8)
    assert result["state"] == "blocked"
    assert result["reason"] == "automatic_repair_failed_without_new_evidence"
    assert result["iterations"] == 1


def test_review_center_automation_is_explicit_and_bounded(tmp_path: Path):
    _project(tmp_path)
    (tmp_path / "review-center.json").write_text(
        json.dumps(
            {
                "projects": [
                    {
                        "id": "book",
                        "path": "book",
                        "automation": {
                            "enabled": True,
                            "poll_seconds": 2,
                            "max_iterations": 6,
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    configured = review_center.load_projects(tmp_path)[0]
    assert configured.automation_enabled is True
    assert configured.automation_poll_seconds == 2
    assert configured.automation_max_iterations == 6


def test_project_automation_uses_builtin_convergence_command(
    tmp_path: Path, monkeypatch
):
    project = _project(tmp_path)
    configured = review_center.ReviewProject("book", project, "Book", True, 5.0, 4)
    monkeypatch.setattr(
        review_center,
        "automation_snapshot",
        lambda _project: {"automatic": True, "reason": "corrections_queued"},
    )
    monkeypatch.setattr(
        review_center,
        "_automation_process_is_active",
        lambda _project: False,
    )
    process = SimpleNamespace(pid=1234)
    monkeypatch.setattr(review_center.subprocess, "Popen", lambda *a, **k: process)
    result = review_center.start_project_automation(configured)
    assert result == {"queued": True, "pid": 1234}


def test_finalized_feedback_is_automatic_but_current_replacement_is_not(
    tmp_path: Path, monkeypatch
):
    project = _project(tmp_path)
    monkeypatch.setattr(
        automation,
        "review_status",
        lambda _project: {
            "reviewer_action": {"code": "none"},
            "review_items": [
                {
                    "id": "submitted",
                    "remediation_state": "pending",
                    "review_required": False,
                },
                {
                    "id": "replacement",
                    "remediation_state": "complete",
                    "review_required": True,
                },
            ],
        },
    )
    snapshot = automation.automation_snapshot(project)
    assert snapshot["automatic"] is True
    assert snapshot["actionable_review_items"] == ["submitted"]
    assert snapshot["review_now"] == ["replacement"]


def test_terminal_result_suppresses_unchanged_automatic_restart(
    tmp_path: Path, monkeypatch
):
    project = _project(tmp_path)
    monkeypatch.setattr(
        automation,
        "review_status",
        lambda _project: {
            "reviewer_action": {"code": "corrections_queued", "enabled": True}
        },
    )
    first = automation.automation_snapshot(project)
    (project / "production/automation-operation.json").write_text(
        json.dumps(
            {
                "state": "blocked",
                "reason": "automatic_repair_made_no_evidence_change",
                "input_identity": first["input_identity"],
            }
        ),
        encoding="utf-8",
    )
    snapshot = automation.automation_snapshot(project)
    assert snapshot["automatic"] is False
    assert snapshot["workflow_state"] == "repair_exhausted"

    configured = review_center.ReviewProject("book", project, "Book", True)
    monkeypatch.setattr(
        review_center.subprocess,
        "Popen",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("unchanged terminal work was restarted")
        ),
    )
    result = review_center.start_project_automation(configured)
    assert result["queued"] is False
    assert result["reason"] == "automatic_repair_made_no_evidence_change"


def test_new_evidence_reenables_automatic_work(tmp_path: Path, monkeypatch):
    project = _project(tmp_path)
    monkeypatch.setattr(
        automation,
        "review_status",
        lambda _project: {"reviewer_action": {"code": "corrections_queued"}},
    )
    first = automation.automation_snapshot(project)
    (project / "production/automation-operation.json").write_text(
        json.dumps(
            {
                "state": "blocked",
                "input_identity": first["input_identity"],
            }
        ),
        encoding="utf-8",
    )
    (project / "production/repair-plan.json").write_text(
        '{"new_evidence": true}', encoding="utf-8"
    )
    snapshot = automation.automation_snapshot(project)
    assert snapshot["automatic"] is True
    assert snapshot["workflow_state"] == "automatic_ready"
