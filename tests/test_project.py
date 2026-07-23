import json
from pathlib import Path

from audiobook_harness.analysis import analyze
from audiobook_harness.project import (
    normalized_words,
    performance_units,
    scaffold,
    sentence_units,
)
from audiobook_harness.pronunciation import audit_lexicon


def test_normalized_words_handles_typographic_apostrophes():
    assert normalized_words("I’ve seen A.C./D.C.") == [
        "i've",
        "seen",
        "a",
        "c",
        "d",
        "c",
    ]


def test_analysis_blocks_unreviewed_terms(tmp_path: Path):
    template = Path(__file__).parents[1] / "templates/project"
    project = tmp_path / "book"
    scaffold(project, template)
    (project / "source/chapter-01.txt").write_text("Elias met AC/DC on 18/07/2026.")
    report = analyze(project)
    assert report["release_blocked"]
    assert "Elias" in report["unresolved_lexicon_candidates"]


def test_pronunciation_audit_requires_reviewed_phonemes(tmp_path: Path):
    template = Path(__file__).parents[1] / "templates/project"
    project = tmp_path / "book"
    scaffold(project, template)
    analyze(project)
    lexicon = {"entries": [{"published": "This", "review_status": "reviewed"}]}
    (project / "lexicon.json").write_text(json.dumps(lexicon))
    report = audit_lexicon(project)
    assert not report["ok"]
    assert "This" in report["invalid"]


def test_sentence_units_keep_closing_typographic_quote():
    assert sentence_units("“Yes.” The door closed.") == ["“Yes.”", "The door closed."]


def test_terse_adjacent_dialogue_is_one_contextual_performance_unit():
    units = performance_units(
        "“Are you hurt?” “I am okay.” “Can you fight?” “I can fight.”"
    )
    assert [unit["text"] for unit in units] == [
        "“Are you hurt?” “I am okay.”",
        "“Can you fight?” “I can fight.”",
    ]
    assert all(
        unit["context_strategy"] == "adjacent_manuscript_context" for unit in units
    )
    assert all(unit["contains_terse_dialogue"] for unit in units)


def test_uncontextualised_final_terse_quote_requires_review():
    unit = performance_units("“Yes.”")[0]
    assert unit["requires_context_review"] is True
