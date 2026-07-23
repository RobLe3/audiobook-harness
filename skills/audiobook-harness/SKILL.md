# Audiobook Harness Skill

Use this skill when an author wants a local, verified audiobook.

## Required workflow

1. Confirm the manuscript and voice rights.
2. Run `audiobook-harness doctor` and report missing local prerequisites.
3. Scaffold a project; place UTF-8 chapter `.txt` files in `source/`.
4. Run `analyze`; do not synthesize while lexicon candidates are unresolved.
5. Review and approve every pronunciation-sensitive lexicon entry.
6. Inspect `production/analysis.json`: terse quoted dialogue must use only
   `adjacent_manuscript_context`, never an invented context or isolated take.
7. Run `generate`, then `verify`; use `retry` only for failed units.
8. Treat a phrase-level ASR equivalence as valid only when reviewed IPA, source, exact phrase scope, and alignment evidence are present.
9. Run `stage`, monitor `status --watch`, and run `promote` only after verification passes. Never copy staged media manually.

## Rules

- Work locally and offline after explicit setup.
- Never make cloud TTS, synthetic SFX, music, or video a hidden fallback.
- Never treat an ASR score alone as subjective proof; keep review evidence for accepted exceptions.
- Do not clone voices without explicit rights and user instruction.
