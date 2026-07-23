# Quality contract

The public baseline uses: manuscript analysis, reviewed pronunciation mapping,
semantic sentence units, deterministic Kokoro takes, two local Whisper passes,
word-level comparison, acoustic duration/peak checks, MFA availability, and
hash-bound release manifests.

Professional releases must pass all automated gates. A failed or ambiguous take
is not released: correct the source map, create a controlled replacement, and
re-run verification. Names, numbers, dates, acronyms, foreign terms, negations,
and units require exact treatment; do not waive them through approximate ASR
similarity.

The harness intentionally does not ship sound effects. Optional user-provided
real-world recordings belong in a future sound-design integration and must carry
license, provenance, placement, gain, and speech-clearance metadata.
