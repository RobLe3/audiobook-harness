# Audiobook Harness Skill

This document describes Audiobook Harness **0.4.15**. Product versioning and artifact compatibility are defined in `docs/VERSIONING.md`.

Use this skill when an author wants a local, verified audiobook.

## Required workflow

1. Confirm the manuscript and voice rights.
2. Run `audiobook-harness doctor` and report missing local prerequisites.
3. Scaffold a project; place UTF-8 chapter `.txt` files in `source/`.
4. Run `analyze`; do not synthesize while lexicon candidates are unresolved.
5. Review and approve every pronunciation-sensitive lexicon entry.
6. Inspect `production/analysis.json`: terse quoted dialogue must use only
   `adjacent_manuscript_context`, never an invented context or isolated take.
7. Prefer `produce` for a monitored staged run. It may repair failed units once
   and must keep every verification threshold unchanged. For manual operation,
   run `generate`, then `verify`; use `retry` only for failed units.
8. Keep single-term decoder spellings narrow. For a multi-token foreign phrase,
   require reviewed IPA, language, `reviewed_phrase_equivalence`, exact
   surrounding words in both ASR passes, and current candidate/alignment
   evidence; never add cue-specific phrase aliases.
9. Monitor `status --watch`, inspect staged audio and verification evidence,
   and save review decisions through the loopback review panel. Rejections and
   uncertain decisions require a defect category; `other` also needs a note.
10. Run `compile-feedback` after finalization. Apply only promoted rules from
    `listener-derived-defaults.json` during the next analysis.
11. Run `pipeline-audit`, `quality-measurements`, and `feature-parity`. Treat
    missing evidence as a block, not as an inherited project capability.
12. Run `promote` only after verification and the current manifest-bound
    listening review pass. Never copy staged media manually.

## Rules

- Work locally and offline after explicit setup.
- Never make cloud TTS, synthetic SFX, music, or video a hidden fallback.
- Never delete or bypass the input-bound recovery ledger to force another
  identical automatic retry.
- Never treat an ASR score alone as subjective proof; keep review evidence for accepted exceptions.
- Never promote listener feedback without a verified correction, follow-up
  listener approval, and a clean regression result. Three occurrences, two
  episodes, or explicit editorial authority are additionally required.
- Preserve the original note, audio hash, correction identity, and follow-up
  result in the append-only feedback ledger.
- Refer to the product only by its 0.4.x SemVer. A book title, project profile,
  schema revision, or historical receipt is not another harness version.
- Do not clone voices without explicit rights and user instruction.
