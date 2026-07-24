from audiobook_harness.quality import _alignment_complete, _mfa_profile


def test_mfa_profile_defaults_to_explicit_english_models():
    assert _mfa_profile({"language": "en-gb"}) == ("english_us_arpa", "english_us_arpa")


def test_non_english_requires_explicit_local_profile():
    try:
        _mfa_profile({"language": "de-de"})
    except ValueError as exc:
        assert "requires" in str(exc)
    else:
        raise AssertionError("non-English profile should not be guessed")


def test_alignment_evidence_requires_every_take(tmp_path):
    (tmp_path / "one.json").write_text("{}")
    ok, missing = _alignment_complete(tmp_path, [{"id": "one"}, {"id": "two"}])
    assert not ok
    assert missing == ["two"]


def test_term_equivalence_is_applied_with_audit_evidence():
    from audiobook_harness.quality import _normalized_asr_with_evidence

    words, applied = _normalized_asr_with_evidence(
        "Example Frase is ready",
        [
            {
                "observed": "Example Frase",
                "expected": "Example Phrase",
                "published": "Example Phrase",
                "scope": "term",
                "source": "test",
            }
        ],
    )
    assert words == ["example", "phrase", "is", "ready"]
    assert applied == [
        {
            "observed": "Example Frase",
            "expected": "Example Phrase",
            "published": "Example Phrase",
            "scope": "term",
            "source": "test",
        }
    ]


def test_acoustic_checks_reject_long_silence_and_clipping():
    import numpy as np
    from audiobook_harness.quality import _acoustic_checks

    audio = np.zeros(24_000 * 3, dtype=np.float32)
    audio[0] = 1.0
    failures = _acoustic_checks(audio, 24_000, 4)
    assert "clipping" in failures
    assert "unexpected_silence" in failures


def test_asr_cache_key_changes_with_every_evidence_input():
    from audiobook_harness.asr_cache import evidence_key

    base = evidence_key(
        audio_sha256="audio", model_sha256="model", decode={"beam_size": 5}, device="cpu"
    )
    assert base != evidence_key(
        audio_sha256="other", model_sha256="model", decode={"beam_size": 5}, device="cpu"
    )
    assert base != evidence_key(
        audio_sha256="audio", model_sha256="other", decode={"beam_size": 5}, device="cpu"
    )
    assert base != evidence_key(
        audio_sha256="audio", model_sha256="model", decode={"beam_size": 1}, device="cpu"
    )
    assert base != evidence_key(
        audio_sha256="audio", model_sha256="model", decode={"beam_size": 5}, device="mps"
    )


def test_only_worker_runtime_failures_qualify_for_serial_fallback():
    from audiobook_harness.quality import _transient_alignment_failure

    assert _transient_alignment_failure("resource_tracker leaked semaphore objects")
    assert _transient_alignment_failure("Broken pipe while worker process started")
    assert not _transient_alignment_failure("dictionary contains an out-of-vocabulary word")
    assert not _transient_alignment_failure("alignment output is incomplete")
