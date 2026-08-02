# Audiobook Harness agent contract

This document describes Audiobook Harness **0.5.8**. Product versioning and artifact compatibility are defined in `docs/VERSIONING.md`.

Use the local staged workflow only:

1. `audiobook-harness doctor`
2. `audiobook-harness new-project <directory>`
3. `audiobook-harness analyze <project>`
4. `audiobook-harness generate <project>`
5. `audiobook-harness verify <project>`
6. Listen to the staged media.
7. `audiobook-harness promote <project>`

For an unattended staged run, use `audiobook-harness produce <project>`. It
runs the same gates, permits at most one failed-unit candidate repair, and
never promotes automatically. Do not bypass its input-bound recovery ledger or
convert a quality rejection into a generic process retry.
Use `produce --resume --dry-run` before resuming. Its eight-phase plan is the
same plan execution consumes; a phase repair may preserve only predecessor
receipts backed by current objective evidence.

The legacy `release` command is intentionally disabled because direct publication
bypasses staged review. Never write generated media directly to `deliverables/`.

Do not publish audio directly from TTS. Generate bounded semantic takes, verify
with two local ASR passes and MFA, and reject or retry failures. Keep names,
acronyms, foreign terms, numbers, and dates in the pronunciation lexicon.

One-to-five-word quoted dialogue must be generated as one performance with its
real adjacent manuscript context. Contextual candidates are version-bound; a
stale context protocol requires regeneration and verification, never a silent
reuse. Run `scripts/test-harness.sh` before changing or publishing the harness.

The harness is local-first. `scripts/setup.py` is the only script allowed to
install dependencies or download model weights, and it requires explicit opt-in.
After setup, production uses `--offline` by default. Do not add telemetry, cloud
TTS, synthetic SFX generation, or automatic asset retrieval.
