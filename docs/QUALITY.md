# Quality contract

This document describes Audiobook Harness **0.4.3**. Product versioning and artifact compatibility are defined in `docs/VERSIONING.md`.

The local production contract is: analyse, review pronunciation-sensitive terms,
generate bounded deterministic candidates, verify every candidate, stage a
complete verified batch, then promote it. A failed or ambiguous take is never
published directly.

## Candidate selection

Each semantic performance unit receives a small fixed set of pace variants. Two
local Whisper checkpoints, acoustic checks, and local MFA alignment decide
whether a candidate may be selected. The selected file, source-unit hash, audio
hash, transcripts, and checks are recorded in `production/verification.json`.
Selection is also bound to the hash of `production/candidates.json`; before
packaging, the harness confirms that the selected audio still has the recorded
bytes and still corresponds to a current candidate-manifest entry. Candidate
files use input-addressed names bound to the model, voices asset, engine version,
synthesis contract, source and performance settings. The completed waveform hash
is the authoritative byte identity, so a later retry cannot silently replace a
waveform that was already verified.

ASR evidence is cached locally only when the complete evidence identity matches:
audio hash, Whisper checkpoint hash, decode settings and CPU device. The cache
does not accept a take by itself; it only avoids repeating an identical local
decode. Any changed waveform, model or decode setting receives a fresh pair of
unprompted ASR checks. Candidate verification deliberately disables word
timestamps because this text-comparison stage does not consume them; timestamp
and forced-alignment gates remain separate release checks.

The checks reject clipping, empty audio, abnormal duration, unexpected silence,
and unusually prolonged word timing. If a replacement is ambiguous but the
manuscript unit is unchanged, the harness can retain the hash-verified previously
accepted take. A changed source unit always requires a newly verified take. A
retained predecessor is permitted only when its audio hash is intact and the
current manifest proves that its source unit is unchanged.

## Terse dialogue

A one-to-five-word quoted reply is performed with real adjacent manuscript
context, never as an isolated request or invented text. The candidate records a
versioned contextual-performance protocol together with its source-unit hash.
If the protocol changes, the take is automatically regenerated and verified;
stale contextual evidence cannot be silently retained. A final terse reply with
no available context remains blocked for editorial review.

The final release decision revalidates the selected take against the current
contextual-performance evidence. It does not rely on an earlier lint annotation:
if later candidate selection or repair resolution changes a take, the final
contract checks the current source hash, selected audio hash, pace, and protocol
again. This preserves strict quality controls while preventing an otherwise
valid release from failing because an informational lint report was created
before the final verified selection existed.

## Reviewed pronunciation equivalences

A reviewed lexicon entry can represent either a single protected term or a
complete phrase. It may include `asr_equivalents` only for documented spellings
emitted by the local ASR decoders. Every such entry requires an IPA override, a
source, and `review_status: reviewed`.

Equivalences are used solely after synthesis for transcript comparison. They do
not change manuscript text, TTS input, IPA, forced alignment, acoustic checks,
or exact checks on surrounding words. The verification record identifies which
equivalence each ASR decoder used. A familiar-looking ASR spelling is never
sufficient reason to add an alias: first confirm the intended pronunciation and
both decoder outputs.

Unicode dashes and closed/hyphenated compounds compare as the same word (for
example, `start-up` and `startup`). A separated phrase such as `start up` is not
merged automatically. Names, foreign terms, and multiword resegmentations must
remain explicit project-local lexicon entries.

```json
{
  "published": "ExampleName",
  "spoken": "Example Name",
  "phoneme_override": "...",
  "language": "example-language",
  "scope": "term",
  "asr_equivalents": ["documented decoder spelling"],
  "source": "Reliable pronunciation source",
  "review_status": "reviewed"
}
```

## Staging and promotion

`stage` writes all verified deliverables and a hash-bound manifest beneath the
project staging directory. It replaces only an empty directory or a directory
carrying an ownership marker for the same project; dangerous and unrelated
directories are rejected. `promote` recalculates the exact staged file set,
hashes, byte counts, verification evidence, and candidate-selection integrity,
then verifies the copied bytes before replacing project deliverables atomically.
For a custom stage, use `promote <project> --from <stage-directory>`. The legacy
direct `release` command is disabled. `status --watch` displays the
JSON lifecycle state and its readable Markdown progress view. The progress
contract carries its source timestamp and the PID of the production command.
If that command is gone, a previously `running` snapshot is marked interrupted;
it is never treated as proof of current work.

The harness intentionally does not ship sound effects, music, cloned voices,
cloud services, telemetry, synthetic scene audio, or automatic asset retrieval.

## Listener-derived defaults

Finalized review decisions are copied into
`production/listener-feedback-ledger.jsonl` with their review and audio
identities. A rejection or uncertain decision requires a defect category;
`other` also requires a note. The original evidence is append-only.

`compile-feedback` validates and summarizes the ledger. A rule in
`listener-derived-defaults.json` can be promoted only after its replacement
passes objective verification, receives follow-up listener approval, and passes
regression checks. It additionally needs explicit editorial authority, three
distinct occurrences, or evidence from two episodes. Project evidence never
silently changes package-wide defaults.

Analysis records the defaults revision, hash, and every matching rule in
`listener-defaults-preflight.json`. A defaults change therefore invalidates
only work whose bound analysis inputs changed; it does not authorize deletion
of unrelated candidates, ASR entries, alignments, or receipts.

## Durable runs

The production runner is a single writer for visible run status. Child work
emits append-only events; it does not rewrite the shared progress snapshot. A
chapter becomes complete only when a receipt binds its quality report and every
staged media file to exact hashes. On resume, receipts—not a stale display
phase, a dead owner PID, or output filenames—determine which chapters may be
skipped.

`produce` may add one bounded set of pace candidates for unit IDs rejected by
the current verification report. It then repeats the complete dual-ASR,
acoustic, selection-integrity and MFA decision. It does not retry a missing
model, invalid dictionary, unresolved pronunciation, implementation exception,
or alignment-quality failure as though it were a candidate problem.

If the repaired candidates still fail, the harness records only the failed unit
IDs and an input-bound signature in `production/recovery-ledger.jsonl`. The
ledger contains no manuscript or audio. The same terminal failure is not given
another automatic retry until the source, configuration, lexicon, model lock or
harness code changes. This prevents repeated work without converting a failure
into a pass.
