# First audiobook in one sitting

This document describes Audiobook Harness **0.7.4**. Product versioning and artifact compatibility are defined in `docs/VERSIONING.md`.

This guide assumes you have the right to make an audiobook from the manuscript
and to use the chosen voice. It uses no cloud TTS, telemetry, or hidden
fallbacks.

## What you will need

- macOS, Linux, or Windows; Python 3.12.
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
   source. A single term may carry a documented decoder spelling. A reviewed
   multi-token foreign phrase must instead declare `scope: phrase`, its
   language, and `validation_policy: reviewed_phrase_equivalence`; do not add
   cue-specific phrase aliases.
8. Run `produce`. It generates bounded deterministic candidates, verifies them
   with two local Whisper decoders, acoustic checks and per-take local MFA
   alignment, then iterates through evidence-bounded repairs for failed units.
   The loop records each iteration and stops for focused listener review when
   the next strategy is subjective or the evidence fingerprint plateaus.
9. Monitor `status --watch`, listen to the staged result, inspect
   `production/verification.json`, then run `promote`. Promotion is blocked
   until the staged manifest still matches successful verification.

## The normal command sequence

The shortest command sequence is:

```bash
.venv/bin/audiobook-harness produce projects/my-book --performance-profile auto
.venv/bin/audiobook-harness status projects/my-book --watch
.venv/bin/audiobook-harness promote projects/my-book
```

For manual control, use:

```bash
.venv/bin/audiobook-harness analyze projects/my-book
# review lexicon.json until production/pronunciation-audit.json is OK
.venv/bin/audiobook-harness generate projects/my-book
.venv/bin/audiobook-harness verify projects/my-book
.venv/bin/audiobook-harness stage projects/my-book
.venv/bin/audiobook-harness status projects/my-book --watch
.venv/bin/audiobook-harness promote projects/my-book
```

## What “blocked” means

CLI failures use stable categories: `2` input, `3` environment, `4` quality,
`5` integrity, `6` review required, `7` processing, and `8` invariant failure.
Failures also emit a compact JSON diagnostic on stderr with the error type,
message, and exit code; manuscript text and audio bytes are not included.

A block is a safety feature, not an invitation to bypass a check.

| Block | Meaning | Correct action |
| --- | --- | --- |
| `doctor` is not OK | A local prerequisite or pinned model is absent. | Run explicit setup or install the named prerequisite. |
| Unresolved lexicon term | The harness cannot safely guess the pronunciation. | Review `lexicon.json`, then re-run `analyze`. |
| ASR, acoustic, alignment, or contextual-protocol failure | No candidate is proven against the expected text and current release method. | Correct the lexicon or manuscript context, run `retry`, then verify again. |
| Automatic repair already terminal | The same failed units already exhausted the bounded repair with identical inputs. | Inspect `production/verification.json`; change the source, reviewed lexicon, configuration, or harness only when the evidence supports it. |
| Staging or promotion block | The batch is incomplete or its verification evidence changed. | Re-run verification and stage a complete batch; do not copy files manually. |
| Non-English MFA profile missing | MFA would have to guess/download a model. | Install a local model deliberately and name it in `project.yaml`. |

## Keep the project portable

Keep `source/`, `project.yaml`, `lexicon.json`, and `production/*.json` under
version control. Treat `assets/generated/` and `deliverables/` as derived,
rebuildable outputs unless your release process requires retaining them.
