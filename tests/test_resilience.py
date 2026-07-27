from pathlib import Path

from audiobook_harness.resilience import (
    append_terminal_failure,
    candidate_failure_signature,
    decide_candidate_retry,
    production_input_identity,
    terminal_signatures,
)


def test_input_identity_changes_with_manuscript(tmp_path: Path):
    repo = Path(__file__).parents[1]
    project = tmp_path / "book"
    (project / "source").mkdir(parents=True)
    (project / "project.yaml").write_text("title: Test\n", encoding="utf-8")
    (project / "lexicon.json").write_text('{"terms":[]}\n', encoding="utf-8")
    source = project / "source/chapter-01.txt"
    source.write_text("First text.", encoding="utf-8")
    first = production_input_identity(project, repo)
    source.write_text("Changed text.", encoding="utf-8")
    assert production_input_identity(project, repo) != first


def test_identical_terminal_failure_is_not_retried():
    signature = candidate_failure_signature(["chapter-01-u001"], "inputs-a")
    decision = decide_candidate_retry(
        ["chapter-01-u001"],
        input_identity="inputs-a",
        previous_signatures={signature},
        remaining_budget=1,
    )
    assert not decision["retry"]
    assert decision["reason"] == "identical_failure_already_terminal_for_same_inputs"


def test_changed_inputs_allow_a_fresh_bounded_retry():
    old = candidate_failure_signature(["chapter-01-u001"], "inputs-a")
    decision = decide_candidate_retry(
        ["chapter-01-u001"],
        input_identity="inputs-b",
        previous_signatures={old},
        remaining_budget=1,
    )
    assert decision["retry"]


def test_terminal_ledger_contains_no_manuscript_or_paths(tmp_path: Path):
    path = tmp_path / "recovery-ledger.jsonl"
    append_terminal_failure(
        path,
        signature="signature-a",
        input_identity="inputs-a",
        failures=["chapter-01-u001"],
        reason="retry_budget_exhausted",
    )
    assert terminal_signatures(path) == {"signature-a"}
    text = path.read_text(encoding="utf-8")
    assert "manuscript" not in text
    assert str(tmp_path) not in text
