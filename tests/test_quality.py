from audiobook_harness.quality import (
    _alignment_complete,
    _cached_transcripts,
    _finalize_verification_integrity,
    _mfa_profile,
)


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
    assert missing == ["one", "two"]


def test_alignment_evidence_requires_matching_plausible_word_intervals(tmp_path):
    (tmp_path / "one.json").write_text(
        '{"tiers":{"words":{"entries":[[0.0,0.3,"Hello"],[0.4,0.8,"world"]]}}}'
    )
    take = {"id": "one", "text": "Hello world.", "duration_seconds": 1.0}
    assert _alignment_complete(tmp_path, [take]) == (True, [])
    (tmp_path / "one.json").write_text(
        '{"tiers":{"words":{"entries":[[0.0,2.0,"Wrong"]]}}}'
    )
    assert _alignment_complete(tmp_path, [take]) == (False, ["one"])


def test_selection_integrity_failure_changes_top_level_verification(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "audiobook_harness.quality.audit_candidate_selection",
        lambda project, report: {"ok": False, "errors": [{"rule": "changed"}]},
    )
    report = _finalize_verification_integrity(tmp_path, {"ok": True})
    assert report["ok"] is False


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


def test_asr_activity_keeps_slow_live_worker_distinct_from_stall():
    from audiobook_harness.status import classify_asr_activity

    assert (
        classify_asr_activity(
            state="running", worker_active=True, evidence_age_seconds=420
        )
        == "slow_but_active"
    )
    assert (
        classify_asr_activity(
            state="running", worker_active=False, evidence_age_seconds=901
        )
        == "stalled"
    )


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
        audio_sha256="audio",
        model_sha256="model",
        decode={"beam_size": 5},
        device="cpu",
    )
    assert base != evidence_key(
        audio_sha256="other",
        model_sha256="model",
        decode={"beam_size": 5},
        device="cpu",
    )
    assert base != evidence_key(
        audio_sha256="audio",
        model_sha256="other",
        decode={"beam_size": 5},
        device="cpu",
    )
    assert base != evidence_key(
        audio_sha256="audio",
        model_sha256="model",
        decode={"beam_size": 1},
        device="cpu",
    )
    assert base != evidence_key(
        audio_sha256="audio",
        model_sha256="model",
        decode={"beam_size": 5},
        device="mps",
    )


def test_asr_progress_callback_reports_completed_decode(tmp_path):
    class Model:
        def transcribe(self, path, **decode):
            return {"text": f"decoded {path}"}

    class Whisper:
        @staticmethod
        def load_model(path, device):
            return Model()

    (tmp_path / "production").mkdir()
    (tmp_path / "take.flac").write_bytes(b"audio")
    checkpoint = tmp_path / "model.pt"
    checkpoint.write_bytes(b"model")
    events = []
    texts, hits, misses = _cached_transcripts(
        Whisper(),
        project=tmp_path,
        candidates=[{"file": "take.flac"}],
        checkpoint=checkpoint,
        decode={"fp16": False},
        cache={"version": 1, "entries": {}},
        model_label="primary",
        progress=lambda model, relative, cached: events.append(
            (model, relative, cached)
        ),
    )
    assert texts["take.flac"].startswith("decoded")
    assert (hits, misses) == (0, 1)
    assert events == [("primary", "take.flac", False)]


def test_only_worker_runtime_failures_qualify_for_serial_fallback():
    from audiobook_harness.quality import _transient_alignment_failure

    assert _transient_alignment_failure("resource_tracker leaked semaphore objects")
    assert _transient_alignment_failure("Broken pipe while worker process started")
    assert not _transient_alignment_failure(
        "dictionary contains an out-of-vocabulary word"
    )
    assert not _transient_alignment_failure("alignment output is incomplete")
