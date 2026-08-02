# Quality contract

This document describes Audiobook Harness **0.6.1**. Product versioning and artifact compatibility are defined in `docs/VERSIONING.md`.

## Transactional quality authority

Objective policy outcomes are versioned (`POLICY_VERSION = 2`) and have a
stable `policy_identity_sha256` in every result. The policy also owns the
acoustic thresholds used for clipping, duration, word-duration, frame, and
silence checks, so changing one changes cue-QA identity and invalidates its
downstream evidence. The harness ships a small CC0/original, model-free corpus
that repeats deterministic text and signal cases for these dispositions. They have fixed
meanings: `pass` means every required objective gate passed; `automatic_repair`
means bounded failed units have evidence for another strategy; `review_required`
means pronunciation or other evidence is incomplete or ambiguous; and `blocked`
means required alignment, encoded-deliverable, or explicitly non-repairable
acoustic evidence is invalid. These dispositions never convert subjective
listener decisions into an objective score.

Each production phase owns an explicit set of artifacts and JSON success
predicates. The harness writes the phase receipt only after every artifact is
present, every predicate is true, and the phase-specific input identity is
known. A rejected quality report remains available for diagnosis but is never
reusable as a successful phase. Implementation failures restore the preceding
committed artifacts and invalidate only the failed phase and its dependants.

Reviewed pronunciations are resolved occurrence by occurrence on phoneme-token
boundaries. Before synthesis, the harness tests each reviewed term in isolated
and sentence-context carriers. Contextual G2P variants may locate the generated
span; only the reviewed IPA may replace it.

Review authority is item-scoped. Rebuilding a review page does not invalidate
an unchanged decision: the item identity binds its text, source audio,
comparison audio, mastered context, and decision scope. Any changed component
creates a new item identity and requires a new decision.

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
complete phrase. Single terms may include documented decoder spellings.
Multi-token foreign phrases instead use `validation_policy:
reviewed_phrase_equivalence`; arbitrary phrase aliases are not substituted.

Phrase equivalence is accepted only when the reviewed phrase occurs exactly
once, its IPA was applied to the hash-bound candidate, both decoders preserve
all surrounding words exactly, and both phrase renderings meet the bounded
similarity check. Exact-ASR policies, ambiguous occurrences, context leakage,
ordinary-word differences, or missing pronunciation evidence remain blocking.

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
  "scope": "phrase",
  "validation_policy": "reviewed_phrase_equivalence",
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
The PCM assembly owns the authored chapter tail. Encoded AAC and MP3 checks
allow at most one codec frame of decoded timing variance and record the
tolerance, measured delta, and result. Missing measurements or larger drift
remain blocking and never conceal incomplete final speech.
For a custom stage, use `promote <project> --from <stage-directory>`. The legacy
direct `release` command is disabled. `status --watch` displays the
JSON lifecycle state and its readable Markdown progress view. The progress
contract carries its source timestamp and the PID of the production command.
If that command is gone, a previously `running` snapshot is marked interrupted;
it is never treated as proof of current work.

Dual-ASR verification also writes timestamped `production/asr-progress.json`.
It reports completed candidates, cache hits, the active checkpoint/file, and
`active`, `slow_but_active`, `stalled`, `failed`, or `complete` activity.
This process evidence is advisory and cannot satisfy a quality or publication
gate.

The harness intentionally does not ship sound effects, music, cloned voices,
cloud services, telemetry, synthetic scene audio, or automatic asset retrieval.

## Listener-derived defaults

Finalized review decisions are copied into
`production/listener-feedback-ledger.jsonl` with their review and audio
identities. A rejection or uncertain decision requires a defect category;
`other` also requires a note. The original evidence is append-only.
Finalization refreshes the feedback summary immediately. A current rejection or
uncertainty is reported as queued correction work; it does not ask the reviewer
to finalize the same waveform again and does not grant release approval.

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

### Evidence-fused repair diagnosis

Verification writes a complete candidate-evidence table before repair routing.
`repair-diagnosis.json` classifies each rejected unit from dual-ASR disagreement,
acoustic failure types, duration evidence, and the median pace of passing units
in the same project. `repair-plan.json` names the owning phase, evidence
requirements, bounded attempt count, and fallback for each strategy. A retry is
allowed only when its strategy changes a declared input or when cached evidence
can be reverified; an unchanged failed waveform is not a new repair.

Pinned local tools may precompute CTC alignment confidence, NISQA/UTMOS, or
speaker-similarity evidence under `production/advisory/`. The harness records
availability explicitly and uses these values only to rank candidates and
prioritize listening. Missing advisory models are a normal state, never a
reason to download a model during production, and no advisory score has release
authority. Listener decisions are stored as compact repair outcomes. Historical
success can reorder otherwise eligible strategies, but cannot relax WER,
alignment, pronunciation, acoustic, or perceptual-review gates.

`candidate-strategy-ledger.json` reserves coverage for every applicable repair
family. Repeating speed or punctuation variants cannot exhaust a cue while a
declared contextual, reviewed-pronunciation, spoken-form, or semantic family is
still untried. A family that cannot produce a distinct waveform records the
reason instead of silently consuming its slot.

`effective-cue-state.json` is the cue-local handoff authority. It records the
selected waveform as provisional until candidate verification and all
downstream pronunciation, duration, pause, energy, and expressive gates agree.
Review and continuation tooling consumes this reconciled state instead of
independently interpreting individual reports.

Mild duration corrections may be rendered as optional review candidates when
the affected word is MFA-bounded, explicitly eligible, not prominence
protected, and needs no more than 12 percent compression. The harness preserves
the surrounding audio, fingerprints the external offline tool, and retains
human perceptual review as the acceptance authority. Larger corrections use
contextual synthesis or semantic re-chunking.
