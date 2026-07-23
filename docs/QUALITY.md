# Quality contract

The local production contract is: analyse, review pronunciation-sensitive terms,
generate bounded deterministic candidates, verify every candidate, stage a
complete verified batch, then promote it. A failed or ambiguous take is never
published directly.

## Candidate selection

Each semantic performance unit receives a small fixed set of pace variants. Two
independent local Whisper passes, acoustic checks, and local MFA alignment decide
whether a candidate may be selected. The selected file, source-unit hash, audio
hash, transcripts, and checks are recorded in `production/verification.json`.

The checks reject clipping, empty audio, abnormal duration, unexpected silence,
and unusually prolonged word timing. If a replacement is ambiguous but the
manuscript unit is unchanged, the harness can retain the hash-verified previously
accepted take. A changed source unit always requires a newly verified take.

## Terse dialogue

A one-to-five-word quoted reply is performed with real adjacent manuscript
context, never as an isolated request or invented text. A final terse reply with
no available context remains blocked for editorial review.

## Reviewed foreign phrases

A lexicon entry can represent a reviewed phrase rather than one word. Phrase
entries require a language, IPA override, source, and `review_status: reviewed`.
They can include `asr_equivalents` only for documented local-ASR spelling forms.
Those forms are used solely to compare a specific phrase after synthesis; they do
not change the spoken text or bypass exact checks on surrounding words.

```json
{
  "published": "Example foreign phrase",
  "spoken": "Example foreign phrase",
  "phoneme_override": "...",
  "language": "example-language",
  "scope": "phrase",
  "asr_equivalents": ["documented decoder spelling"],
  "source": "Reliable pronunciation source",
  "review_status": "reviewed"
}
```

## Staging and promotion

`stage` writes all verified deliverables and a hash-bound manifest beneath the
project staging directory. `promote` checks that verification has not changed and
then replaces the project deliverables atomically. `status --watch` refreshes both
JSON lifecycle state and a readable Markdown progress view.

The harness intentionally does not ship sound effects, music, cloned voices,
cloud services, telemetry, synthetic scene audio, or automatic asset retrieval.
