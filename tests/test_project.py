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


def test_normalized_words_treats_hyphenated_compounds_as_closed_words():
    assert normalized_words("start-up start‑up startup") == [
        "startup",
        "startup",
        "startup",
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


def test_reviewed_term_and_phrase_asr_equivalences_require_evidence():
    from audiobook_harness.pronunciation import asr_equivalences

    lexicon = {
        "Example Phrase": {
            "review_status": "reviewed",
            "scope": "phrase",
            "spoken": "Example Phrase",
            "phoneme_override": "e",
            "source": "test source",
            "asr_equivalents": ["Example Frase"],
        },
        "ExampleName": {
            "review_status": "reviewed",
            "scope": "term",
            "spoken": "Example Name",
            "phoneme_override": "e",
            "source": "test source",
            "asr_equivalents": ["Example Naim"],
        },
        "Not Scoped": {"review_status": "reviewed", "asr_equivalents": ["Ignored"]},
    }
    pairs = asr_equivalences(lexicon)
    assert [(row["observed"], row["expected"], row["scope"]) for row in pairs] == [
        ("Example Frase", "Example Phrase", "phrase"),
        ("Example Naim", "Example Name", "term"),
    ]


def test_asr_equivalences_without_pronunciation_evidence_are_rejected(tmp_path: Path):
    template = Path(__file__).parents[1] / "templates/project"
    project = tmp_path / "book"
    scaffold(project, template)
    (project / "source/chapter-01.txt").write_text("ExampleName arrived.")
    analyze(project)
    (project / "lexicon.json").write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "published": "ExampleName",
                        "spoken": "Example Name",
                        "phoneme_override": "e",
                        "review_status": "reviewed",
                        "scope": "term",
                        "asr_equivalents": ["Example Naim"],
                    }
                ]
            }
        )
    )
    report = audit_lexicon(project)
    assert not report["ok"]
    assert report["invalid_asr_equivalences"] == ["ExampleName"]


def test_retry_variants_extend_the_initial_bounded_set():
    from audiobook_harness.tts import RETRY_VARIANTS, VARIANTS

    assert set(VARIANTS).issubset(set(RETRY_VARIANTS))
    assert {name for name, _ in RETRY_VARIANTS}.issuperset(
        {"retry_slower", "retry_faster"}
    )
