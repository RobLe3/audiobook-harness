import json
from pathlib import Path

from audiobook_harness.analysis import analyze
from audiobook_harness.project import normalized_words, scaffold
from audiobook_harness.pronunciation import audit_lexicon


def test_normalized_words_handles_typographic_apostrophes():
    assert normalized_words("I’ve seen A.C./D.C.") == ["i've", "seen", "a", "c", "d", "c"]


def test_analysis_blocks_unreviewed_terms(tmp_path: Path):
    template = Path(__file__).parents[1] / "templates/project"
    project = tmp_path / "book"; scaffold(project, template)
    (project / "source/chapter-01.txt").write_text("Elias met AC/DC on 18/07/2026.")
    report = analyze(project)
    assert report["release_blocked"]
    assert "Elias" in report["unresolved_lexicon_candidates"]


def test_pronunciation_audit_requires_reviewed_phonemes(tmp_path: Path):
    template = Path(__file__).parents[1] / "templates/project"
    project = tmp_path / "book"; scaffold(project, template)
    analyze(project)
    lexicon = {"entries": [{"published": "This", "review_status": "reviewed"}]}
    (project / "lexicon.json").write_text(json.dumps(lexicon))
    report = audit_lexicon(project)
    assert not report["ok"]
    assert "This" in report["invalid"]
