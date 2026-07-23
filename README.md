# Audiobook Harness

A local-first, evidence-based audiobook production harness for coding agents.
It focuses on manuscript analysis, pronunciation control, contextual dialogue,
Kokoro TTS, independent speech verification, forced alignment, and reproducible
M4A/MP3 delivery.

It does **not** bundle manuscripts, cloned voices, music, SFX, synthetic sound
generation, or cloud APIs.

## Quick start

```bash
python scripts/setup.py --interactive
.venv/bin/audiobook-harness doctor
.venv/bin/audiobook-harness new-project projects/my-book
# place your licensed manuscript text at projects/my-book/source/chapter-01.txt
.venv/bin/audiobook-harness analyze projects/my-book
.venv/bin/audiobook-harness generate projects/my-book
.venv/bin/audiobook-harness verify projects/my-book
.venv/bin/audiobook-harness release projects/my-book
```

On Windows, use `.venv\\Scripts\\audiobook-harness.exe` instead.

See [docs/SETUP.md](docs/SETUP.md), [docs/QUALITY.md](docs/QUALITY.md), and the
agent [skill](skills/audiobook-harness/SKILL.md).
