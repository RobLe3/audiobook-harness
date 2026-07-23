# Architecture

`analyze` produces a source-preserving analysis manifest and blocks unresolved
pronunciation-sensitive vocabulary. `generate` creates one Kokoro take per
semantic sentence unit and records file hashes. `verify` runs primary and
secondary local Whisper decoding, lexical comparison, peak/duration checks, and
MFA availability validation. `release` only joins verified takes and packages
lossless FLAC, M4A, and MP3.

The public v0.1 baseline deliberately avoids unproven emotional DSP, synthetic
breaths, SFX generation, opaque model selection, and cloud fallback. Future
quality modules must add a schema, evidence, deterministic test fixture, and a
blocking release rule before becoming defaults.
