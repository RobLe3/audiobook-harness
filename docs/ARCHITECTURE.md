# Architecture

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
