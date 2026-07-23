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
7. Run `generate`, then `verify`.
8. If any take fails ASR, timing, pronunciation, clipping, or duration checks, revise the lexicon/context strategy and regenerate only that take. Do not publish a failed take.
9. Run `release` only after verification passes.

## Rules

- Work locally and offline after explicit setup.
- Never make cloud TTS, synthetic SFX, music, or video a hidden fallback.
- Never treat an ASR score alone as subjective proof; keep review evidence for accepted exceptions.
- Do not clone voices without explicit rights and user instruction.
