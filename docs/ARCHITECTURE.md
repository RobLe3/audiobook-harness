# Architecture

This document describes Audiobook Harness **0.4.9**. Product versioning and artifact compatibility are defined in `docs/VERSIONING.md`.

## Performance and render lineage

Version 0.4.9 treats the clean performed speech as the immutable take. Channel,
codec, mastering, and presentation renders are derived identities whose hashes
name their parent take and processor contract. Listener decisions can therefore
remain attached to unchanged performances while a derived render is rebuilt.
Legacy processed audio may acquire a clean parent only through a recorded,
threshold-bound deterministic replay; similarity alone is never publication
authority.

Quality gates use typed dispositions. Evidence and review blockers stop only
their owning chapter, while independent chapters continue. Only an unsafe tool
or infrastructure failure stops the complete series runner.

A phase commits its receipt only after all declared outputs exist. A bounded
repair is represented by an input-bound ticket naming its owning phase,
affected units, required input delta, and remaining attempt budget. Listener
defect findings may survive a changed waveform, but approval never does.

The harness owns one eight-phase graph: analysis, synthesis, candidate
realization, cue QA, pre-mix gating, assembly, post-mix QA, and packaging.
Projects supply source, reviewed vocabulary, performance policy, and optional
extensions. They do not fork the harness identity.

`feature-parity.json` is the conformance index. Core narration and review
capabilities are required. Communication processing, soundscapes, music,
battle audio, and videobook output use the same receipt contract but remain
optional project-profile capabilities.

The harness keeps source analysis, candidate generation, verification, staging,
and publication separate. Each UTF-8 chapter becomes source-preserving semantic
performance units. Reviewed lexicon entries apply IPA only to matching model
phoneme spans.

`generate` creates bounded deterministic candidates. `verify` uses two local
ASR passes, phrase-scoped reviewed equivalences, acoustic checks, source hashes,
and local MFA alignment to select one candidate per unit. `stage` packages only
selected takes into a hash-bound batch. `promote` checks that the verification
manifest is still current before replacing deliverables.

Lifecycle state is stored under `production/run-status.json`; `status --watch`
renders a portable `production/progress.md`. Production remains local and offline
after explicit setup.

## Unattended production

`produce` is the single-process supervisor for a staged chapter set. It records
five visible phases:

1. manuscript and pronunciation analysis;
2. bounded deterministic candidate generation;
3. dual-ASR, acoustic and forced-alignment verification;
4. one failed-unit candidate repair when evidence permits it; and
5. hash-bound staging.

The repair phase regenerates only unit IDs rejected by the current verification
report. It does not retry dictionary, corpus, missing-model, implementation or
other prerequisite failures. It does not alter WER, acoustic, alignment or
pronunciation acceptance limits.

The recovery signature includes the failed unit IDs and an input identity
derived from source text, project configuration, the reviewed lexicon, model
lock and harness code. A terminal signature is stored in
`production/recovery-ledger.jsonl`. Repeating `produce` with unchanged inputs
will not repeat a repair that has already ended with the same rejection. A real
input or harness change produces a different identity.

## Interruption-safe phase reuse

`produce --resume --dry-run` and `produce --resume` use the same eight-phase
planner. Each phase reports `REUSE` or `RUN` and a reason before a model loads
or media changes. A hash-bound `phase-repair-receipt.json` may retain phases
before one objectively repaired owning phase; that phase and every dependent
phase still rerun.

A receipt binds the production input identity and exact artifact hashes.
Changed manuscript, configuration, lexicon, model lock, harness code, or
artifact bytes invalidate the affected phase and its downstream evidence. An
interruption never triggers a clean project restart. Candidate repair still
regenerates only the failed unit IDs, and no quality threshold is relaxed.
Repair evidence must be current, machine-readable, explicitly passing, and
bound to the changed dependency bytes. It is never human approval.

Staging is the end of unattended authority. Promotion remains a separate
command so the listener can inspect the verification report and staged audio
before replacing deliverables.
