# Audiobook Harness agent contract

Use the local staged workflow only:

1. `audiobook-harness doctor`
2. `audiobook-harness new-project <directory>`
3. `audiobook-harness analyze <project>`
4. `audiobook-harness generate <project>`
5. `audiobook-harness verify <project>`
6. `audiobook-harness release <project>`

Do not publish audio directly from TTS. Generate bounded semantic takes, verify
with two local ASR passes and MFA, and reject or retry failures. Keep names,
acronyms, foreign terms, numbers, and dates in the pronunciation lexicon.

The harness is local-first. `scripts/setup.py` is the only script allowed to
install dependencies or download model weights, and it requires explicit opt-in.
After setup, production uses `--offline` by default. Do not add telemetry, cloud
TTS, synthetic SFX generation, or automatic asset retrieval.
