# Architecture

`analyze` produces a source-preserving analysis manifest, blocks unresolved
pronunciation-sensitive vocabulary, and converts sentences into semantic
performance units. Terse one-to-five-word quoted turns are grouped with real
adjacent manuscript context before synthesis; their source sentence indexes are
retained in the manifest. `generate` creates one deterministic Kokoro take per
performance unit and records text, phonemes, strategy, and file hashes.
`verify` runs primary and secondary local Whisper decoding, lexical comparison,
peak/duration checks, and per-take local MFA alignment. `release` only joins
verified takes and packages lossless FLAC, M4A, and MP3.

The public v0.1 baseline deliberately avoids unproven emotional DSP, synthetic
breaths, SFX generation, opaque model selection, and cloud fallback. Future
quality modules must add a schema, evidence, deterministic test fixture, and a
blocking release rule before becoming defaults.
