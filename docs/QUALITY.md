# Quality contract

The public baseline uses: manuscript analysis, reviewed pronunciation mapping,
semantic performance units, deterministic Kokoro takes, two local Whisper passes,
word-level comparison, acoustic duration/peak checks, MFA alignment, and
hash-bound release manifests.

## Terse dialogue guard

A one-to-five-word quoted reply is not synthesized in isolation. The analysis
stage binds it to an immediately adjacent sentence from the supplied manuscript
and records the source-sentence indexes and `adjacent_manuscript_context`
strategy in `production/analysis.json`. This prevents a common TTS artefact:
exaggerated terminal vowels or question contours caused by a tiny standalone
request. The public harness does **not** invent character voices, splice
phonemes, or fabricate a surrounding context. It uses only the real adjacent
manuscript text, in order, in one verified take.

If a final quoted reply has no adjacent sentence, analysis records it as a
review case. Add a real neighbouring sentence where editorially appropriate or
handle it as a deliberately reviewed exception; do not pad it with invented
text.

Professional releases must pass all automated gates. A failed or ambiguous take
is not released: correct the source map, create a controlled replacement, and
re-run verification. Names, numbers, dates, acronyms, foreign terms, negations,
and units require exact treatment; do not waive them through approximate ASR
similarity.

The harness intentionally does not ship sound effects. Optional user-provided
real-world recordings belong in a future sound-design integration and must carry
license, provenance, placement, gain, and speech-clearance metadata.

## Forced alignment

Professional verification runs local MFA alignment after both independent local
Whisper transcriptions. Each generated take is converted to an isolated WAV/LAB
pair and must produce a matching JSON alignment record. MFA is an evidence gate,
not a model downloader: the starter profile uses locally installed English MFA
models. A non-English project must explicitly name already installed local
`mfa.dictionary` and `mfa.acoustic_model` values in `project.yaml`.
