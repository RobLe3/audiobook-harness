# Planning time and performance

## Read this first

These are **planning bands**, not benchmarks or product claims. The harness is
quality-first: two local ASR passes and MFA alignment can take longer than
Kokoro synthesis. Chip labels alone are not enough to promise a duration:
memory size, thermal state, the installed Whisper/MFA versions, the number of
pronunciation repairs, and chapter language all matter.

Measure the first 1,000-word chapter on the exact Mac you will use, then use
that measured rate for the rest of the book. Never lower quality gates merely to
make a planning estimate look faster.

## First-run versus chapter-run time

| Activity | First project | Later chapter |
| --- | ---: | ---: |
| Review setup and download pinned local models | 15–60 min plus network time | — |
| Create project and analyse a 5,000-word chapter | 5–15 min including lexicon review | 1–5 min if vocabulary is already reviewed |
| Generate, dual-ASR verify, MFA-align and package 1,000 words | hardware-dependent; see bands below | same |
| Human spot review of a verified chapter | 5–15 min | 5–15 min |

The first chapter usually takes longer because it establishes the pronunciation
lexicon. A 10-chapter book should be planned as a **measured pilot chapter +
batch run**, not ten independent first runs.

## Conservative Apple-silicon planning bands

The bands below assume one local, English, 1,000-word chapter; CPU-oriented
Kokoro, two local Whisper checks, local MFA, and no parallel chapters. They are
intentionally broad and should be replaced by the first measured chapter.

| Mac family | Plan for one 1,000-word quality-assured chapter | 10 × 1,000-word chapters, sequential |
| --- | ---: | ---: |
| M1 | 15–35 min | 2.5–6 h |
| M2 | 12–28 min | 2–5 h |
| M3 | 10–24 min | 1.75–4.5 h |
| M4 | 8–20 min | 1.5–3.75 h |
| M5 | 7–18 min | 1.25–3.5 h |
| Pro / Max configuration | often 10–30% quicker for this CPU-heavy workflow, not a linear core-count gain | use a measured pilot |

M1 and M2 base chips use 8-core CPUs; base M4 and M5 are up to 10 cores.
Apple’s M5 Pro/Max products add substantially different CPU/GPU configurations,
but this workflow is not a GPU rendering benchmark. More cores may help
concurrent file preparation and encoding; local Whisper/MFA/TTS throughput must
still be measured on the real configuration. See Apple’s published chip
background for [M1](https://www.apple.com/newsroom/2020/11/apple-unleashes-m1/),
[M2](https://www.apple.com/newsroom/2022/06/apple-unveils-all-new-macbook-air-supercharged-by-the-new-m2-chip/),
[M4](https://www.apple.com/newsroom/2024/05/apple-introduces-m4-chip/), and
[M5](https://www.apple.com/newsroom/2026/03/apple-introduces-the-new-macbook-air-with-m5/).

## How to make your own schedule

1. Start with a representative, reviewed 1,000-word chapter.
2. Record separate wall-clock times for `analyze`, `generate`, `verify`, and
   `release` in your project notes.
3. Multiply the **verify** time too; it is not optional overhead.
4. Add 15–25% for chapters with new names, numbers, languages, or dialogue.
5. Run sequentially for the first full-book batch. Parallel generation is an
   advanced decision: it may compete for RAM/CPU and makes diagnosis harder.

The M-series generation is a useful purchase hint, not a quality setting. A
complete verified output on a slower Mac is preferable to a fast but unverified
release.
