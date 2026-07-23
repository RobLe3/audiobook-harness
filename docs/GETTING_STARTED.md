# First audiobook in one sitting

This guide assumes you have the right to make an audiobook from the manuscript
and to use the chosen voice. It uses no cloud TTS, telemetry, or hidden
fallbacks.

## What you will need

- macOS, Linux, or Windows; Python 3.11 or 3.12.
- FFmpeg/FFprobe and eSpeak NG.
- A local disk with roughly 8–12 GB free for the first English setup (Kokoro,
  two Whisper models, MFA, temporary WAVs, and your outputs).
- Internet **only during the explicit setup/download step**. Production itself
  runs offline.

## The shortest successful route

1. Clone the repository and read `README.md`, `SECURITY.md`, and `NOTICE`.
2. Run `python scripts/setup.py --interactive`. Read each prompt. Decline a
   component you do not want installed; no production command downloads it
   later.
3. Confirm prerequisites with `.venv/bin/audiobook-harness doctor` (on Windows:
   `.venv\Scripts\audiobook-harness.exe doctor`). All checks must be `true`.
4. Create a working project:

   ```bash
   .venv/bin/audiobook-harness new-project projects/my-book
   ```

5. Replace the sample file with your UTF-8 chapter text in `source/`. Keep one
   `.txt` file per chapter.
6. Run `analyze`. It creates `production/analysis.json` and intentionally
   blocks production when it finds names, acronyms, numbers, or foreign terms
   that need a pronunciation decision.
7. Review `lexicon.json`. For each identified sensitive term, add a
   `phoneme_override` and set `review_status` to `reviewed`. Do **not** guess a
   phonetic spelling: listen to a small test or use a reliable pronunciation
   source.
8. Run `generate`, then `verify`. Verification requires two local Whisper
   decoders and per-take local MFA alignment. A failed take is not releasable.
9. Run `release`. It writes hash-recorded FLAC, M4A, and MP3 files beneath the
   project’s `deliverables/` directory.

## The normal command sequence

```bash
.venv/bin/audiobook-harness analyze projects/my-book
# review lexicon.json until production/pronunciation-audit.json is OK
.venv/bin/audiobook-harness generate projects/my-book
.venv/bin/audiobook-harness verify projects/my-book
.venv/bin/audiobook-harness release projects/my-book
```

## What “blocked” means

A block is a safety feature, not an invitation to bypass a check.

| Block | Meaning | Correct action |
| --- | --- | --- |
| `doctor` is not OK | A local prerequisite or pinned model is absent. | Run explicit setup or install the named prerequisite. |
| Unresolved lexicon term | The harness cannot safely guess the pronunciation. | Review `lexicon.json`, then re-run `analyze`. |
| ASR, acoustic, or alignment failure | The generated take is not proven against the expected text. | Correct text/punctuation/lexicon and regenerate; do not release it. |
| Non-English MFA profile missing | MFA would have to guess/download a model. | Install a local model deliberately and name it in `project.yaml`. |

## Keep the project portable

Keep `source/`, `project.yaml`, `lexicon.json`, and `production/*.json` under
version control. Treat `assets/generated/` and `deliverables/` as derived,
rebuildable outputs unless your release process requires retaining them.
