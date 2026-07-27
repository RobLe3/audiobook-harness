# Audiobook Harness

A local-first, evidence-based audiobook production harness for coding agents.
It focuses on manuscript analysis, pronunciation control, contextual dialogue,
Kokoro TTS, independent local speech verification, forced alignment, and reproducible
M4A/MP3 delivery with staged promotion.

Reviewed decoder-spelling equivalences are supported for protected names and
phrases, but only as local transcript-comparison evidence. They never change the
manuscript or spoken input; see the [quality contract](docs/QUALITY.md).

It does **not** bundle manuscripts, cloned voices, music, SFX, synthetic sound
generation, or cloud APIs.

![Animated local workflow](docs/assets/audiobook-harness-workflow.gif)

The animation is a local ASCII-style production walkthrough. It illustrates eight quality checkpoints. The command-line status view intentionally groups them into five clear milestones: analyse, generate, verify, stage and promote. It shows a release contract, not a benchmark: actual time depends on manuscript length, reviewed vocabulary, hardware and rejected takes. See the [production walkthrough](docs/PRODUCTION_WALKTHROUGH.md) for both a plain-language and expert view.

## Progress you can trust

Every production command writes `production/run-status.json` and the matching
human-readable `production/progress.md`. `status --watch` displays the same
file with a progress bar and current stage; it does not guess from output files.
The view records its own update timestamp and the PID of the command that wrote
the active state. If that command no longer exists, the harness labels the
snapshot **interrupted** rather than pretending work is still running. A failed
or completed run is explicitly labelled historical. This makes it safe to
monitor a long operation from a second terminal without confusing an old render
of the progress file for a live job.

`produce` runs analysis, candidate generation, dual-ASR and MFA verification,
one bounded failed-unit repair, and staging as one monitored command. It never
promotes files automatically. If the same failed units recur with the same
manuscript, lexicon, configuration and harness code, an input-bound recovery
ledger prevents the next run from spending the same retry again. Changed inputs
receive a new identity and can be tried normally.

## Quick start

```bash
python scripts/setup.py --interactive
.venv/bin/audiobook-harness doctor
.venv/bin/audiobook-harness performance --profile auto
.venv/bin/audiobook-harness new-project projects/my-book
# place your licensed manuscript text at projects/my-book/source/chapter-01.txt
.venv/bin/audiobook-harness produce projects/my-book --performance-profile auto
.venv/bin/audiobook-harness status projects/my-book --watch
# listen to the staged files and inspect production/verification.json
.venv/bin/audiobook-harness promote projects/my-book
```

On Windows, use `.venv\\Scripts\\audiobook-harness.exe` instead.

## Choose your depth

**First audiobook:** follow the plain-language [first-book guide](docs/GETTING_STARTED.md), then
read [setup](docs/SETUP.md), the [quality contract](docs/QUALITY.md),
[performance planning](docs/PERFORMANCE.md), [workflow architecture](docs/ARCHITECTURE.md), and the agent
[skill](skills/audiobook-harness/SKILL.md). A local, model-free Linux onboarding check is documented in
[Container smoke test](docs/SETUP.md#container-smoke-test).

`performance --profile auto` displays a conservative local CPU budget. Pass
`--performance-profile auto` to `verify` or `produce` to use it for forced alignment. If a
parallel alignment worker fails for a recognised transient runtime reason, the
same work restarts once in a clean serial runtime; dictionary, corpus, semantic
and quality failures remain blocking. It never weakens the quality contract or
turns GPU/NPU use into release evidence.

If you prefer explicit control, run `analyze`, `generate`, `verify`, `stage`,
and `promote` separately. `retry` adds bounded candidates only for units listed
as failed by the current verification report.

## Verify this checkout

Run the repository checks before starting a book:

```bash
scripts/test-harness.sh
```

It runs the unit tests and linting with the local virtual environment. If the
already-built local smoke image is present, it also runs its model-free offline
container check; it never pulls an image or downloads a model.
