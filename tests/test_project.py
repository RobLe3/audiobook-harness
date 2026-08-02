import json
from pathlib import Path

from audiobook_harness.analysis import analyze
from audiobook_harness.project import (
    normalized_words,
    performance_units,
    scaffold,
    sentence_units,
    write_json,
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


def test_write_json_replaces_atomically_and_leaves_valid_json(tmp_path: Path):
    path = tmp_path / "production" / "state.json"

    write_json(path, {"state": "running", "step": 1})
    assert json.loads(path.read_text()) == {"state": "running", "step": 1}

    write_json(path, {"state": "complete", "step": 8})
    assert json.loads(path.read_text()) == {"state": "complete", "step": 8}
    assert list(path.parent.glob(f".{path.name}.*.tmp")) == []


def test_normalized_words_treats_hyphenated_compounds_as_closed_words():
    assert normalized_words("start-up start‑up startup") == [
        "startup",
        "startup",
        "startup",
    ]


def test_normalized_words_treats_en_and_em_dashes_as_boundaries():
    assert normalized_words("alpha—beta gamma–delta") == [
        "alpha",
        "beta",
        "gamma",
        "delta",
    ]


def test_analysis_blocks_unreviewed_terms(tmp_path: Path):
    template = Path(__file__).parents[1] / "templates/project"
    project = tmp_path / "book"
    scaffold(project, template)
    (project / "source/chapter-01.txt").write_text("Elias met AC/DC on 18/07/2026.")
    report = analyze(project)
    assert report["release_blocked"]
    assert "Elias" in report["unresolved_lexicon_candidates"]


def test_analysis_ignores_only_ordinary_sentence_starters(tmp_path: Path):
    template = Path(__file__).parents[1] / "templates/project"
    project = tmp_path / "book"
    scaffold(project, template)
    (project / "source/chapter-01.txt").write_text(
        "The door opened. After midnight, Elias arrived."
    )
    report = analyze(project)
    unresolved = report["unresolved_lexicon_candidates"]
    assert "The" not in unresolved
    assert "After" not in unresolved
    assert "Elias" in unresolved


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
        ("Example Naim", "Example Name", "term"),
    ]


def test_reviewed_phrase_equivalence_is_bounded_to_one_foreign_phrase():
    from audiobook_harness.pronunciation import reviewed_phrase_equivalence

    candidate = {
        "sha256": "audio",
        "phonemes": "before f o n e m after",
        "pronunciation_occurrences": [{"published": "Nom Étranger"}],
    }
    lexicon = {
        "Nom Étranger": {
            "review_status": "reviewed",
            "scope": "phrase",
            "language": "fr",
            "validation_policy": "reviewed_phrase_equivalence",
            "spoken": "nom etranger",
            "phoneme_override": "f o n e m",
            "source": "reviewed source",
        }
    }
    result = reviewed_phrase_equivalence(
        expected=["before", "nom", "etranger", "after"],
        primary=["before", "nometrajer", "after"],
        secondary=["before", "nom", "etrajer", "after"],
        lexicon=lexicon,
        candidate=candidate,
    )
    assert result is not None
    assert result["outside_phrase_exact"]
    assert (
        reviewed_phrase_equivalence(
            expected=["before", "nom", "etranger", "after"],
            primary=["wrong", "nometrajer", "after"],
            secondary=["before", "nom", "etrajer", "after"],
            lexicon=lexicon,
            candidate=candidate,
        )
        is None
    )


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


def test_pronunciation_override_applies_to_every_reviewed_occurrence():
    from audiobook_harness.pronunciation import apply_to_phonemes_with_evidence

    resolved, evidence = apply_to_phonemes_with_evidence(
        "Renaud met RENAUD.",
        "default met default.",
        {
            "Renaud": {
                "review_status": "reviewed",
                "phoneme_override": "override",
            }
        },
        lambda _value: "default",
    )
    assert resolved == "override met override."
    assert [row["source_span"] for row in evidence] == [[0, 6], [11, 17]]


def test_initialism_override_locates_context_reduced_final_a():
    from audiobook_harness.pronunciation import apply_to_phonemes_with_evidence

    resolved, evidence = apply_to_phonemes_with_evidence(
        "The CIA officer.",
        "ðə sˈiː aɪ ɐ ˈɒfɪsə",
        {
            "CIA": {
                "review_status": "reviewed",
                "category": "initialism",
                "phoneme_override": "sˈiː ˈaɪ ˈeɪ",
            }
        },
        lambda _value: "sˈiː aɪ ˈeɪ",
    )
    assert resolved == "ðə sˈiː ˈaɪ ˈeɪ ˈɒfɪsə"
    assert evidence[0]["default_phonemes"] == "sˈiː aɪ ɐ"


def test_pronunciation_locator_does_not_replace_inside_another_token():
    from audiobook_harness.pronunciation import apply_to_phonemes_with_evidence

    resolved, _ = apply_to_phonemes_with_evidence(
        "Ann.",
        "joanne an.",
        {"Ann": {"review_status": "reviewed", "phoneme_override": "reviewed"}},
        lambda _value: "an",
    )
    assert resolved == "joanne reviewed."


def test_pronunciation_context_preflight_reports_each_reviewed_term():
    from audiobook_harness.pronunciation import pronunciation_context_preflight

    report = pronunciation_context_preflight(
        {
            "CIA": {
                "review_status": "reviewed",
                "category": "initialism",
                "phoneme_override": "sˈiː ˈaɪ ˈeɪ",
            }
        },
        lambda text: "sˈiː aɪ ɐ" if "CIA" in text else text,
    )
    assert report["ok"]
    assert report["terms"][0]["contexts"] == 3


def test_analysis_assigns_contiguous_immutable_unit_order(tmp_path: Path):
    template = Path(__file__).parents[1] / "templates/project"
    project = tmp_path / "book"
    scaffold(project, template)
    (project / "source/chapter-01.txt").write_text("One sentence. Two sentences.")
    report = analyze(project)
    units = report["chapters"][0]["units"]
    assert [row["unit_index"] for row in units] == [1, 2]
    assert [row["global_sequence"] for row in units] == [1, 2]
    assert all(row["source_span"][0] >= 0 for row in units)


def test_retry_variants_extend_the_initial_bounded_set():
    from audiobook_harness.tts import RETRY_VARIANTS, VARIANTS

    assert set(VARIANTS).issubset(set(RETRY_VARIANTS))
    assert {name for name, _ in RETRY_VARIANTS}.issuperset(
        {"retry_slower", "retry_faster"}
    )


def test_candidate_identity_changes_with_model_and_voice_assets():
    from audiobook_harness.tts import _candidate_identity

    values = {
        "name": "baseline",
        "phonemes": "test",
        "source_hash": "source",
        "context_protocol": {"version": 1},
        "voice": "voice",
        "speed": 0.95,
        "engine_identity": {
            "model_sha256": "model-a",
            "voices_sha256": "voices-a",
            "kokoro_onnx_version": "1",
            "synthesis_contract_version": 2,
        },
    }
    baseline = _candidate_identity(**values)
    changed = {
        **values,
        "engine_identity": {**values["engine_identity"], "model_sha256": "model-b"},
    }
    assert baseline != _candidate_identity(**changed)


def test_reviewed_phoneme_replacement_is_idempotent_and_conflict_aware():
    from audiobook_harness.pronunciation import resolve_reviewed_phoneme_replacement

    status, value = resolve_reviewed_phoneme_replacement(
        "x old y", before="old", after="new"
    )
    assert (status, value) == ("change_required", "x new y")
    assert resolve_reviewed_phoneme_replacement(value, before="old", after="new") == (
        "already_applied",
        "x new y",
    )
    assert resolve_reviewed_phoneme_replacement(
        "x third y", before="old", after="new"
    ) == ("source_authority_conflict", "x third y")
