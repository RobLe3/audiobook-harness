# Architecture

This document describes Audiobook Harness **0.4.2**. Product and legacy contract versioning is defined in `docs/VERSIONING.md`.

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

`produce --resume --dry-run` validates the input-bound receipt for each
completed phase and reports `REUSE` or `RUN` before loading a model or changing
media. `produce --resume` then starts at the first missing, changed, or
unverified phase. Earlier valid phases and input-addressed, waveform-hashed candidate audio
remain in place.

A receipt binds the production input identity and exact artifact hashes.
Changed manuscript, configuration, lexicon, model lock, harness code, or
artifact bytes invalidate the affected phase and its downstream evidence. An
interruption never triggers a clean project restart. Candidate repair still
regenerates only the failed unit IDs, and no quality threshold is relaxed.

Staging is the end of unattended authority. Promotion remains a separate
command so the listener can inspect the verification report and staged audio
before replacing deliverables.
