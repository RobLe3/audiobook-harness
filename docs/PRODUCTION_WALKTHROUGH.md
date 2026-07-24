# Production walkthrough

The harness is designed for a simple outcome: produce audio locally, keep only
verified takes, and promote a release only after its evidence is complete.

## Simple view: eight quality checkpoints

1. **Read the chapter** — identify names, terms, numbers, abbreviations and
   short dialogue that need special care.
2. **Plan pronunciation and context** — record reviewed spellings and preserve
   real neighbouring manuscript text for terse replies.
3. **Generate bounded alternatives** — Kokoro creates small, reproducible takes
   instead of one long, unreviewable request.
4. **Compare the spoken words** — two independent local speech-to-text passes
   compare the audio with the approved text.
5. **Check the recording** — reject clipping, abnormal duration and unexpected
   silence before a take can be selected.
6. **Align the words** — local forced alignment confirms that each selected take
   has timing evidence. An optional conservative worker profile retries only a
   recognised host-worker failure once in a clean serial runtime.
7. **Stage the release** — assemble only selected takes, re-check the selection
   record, and package an M4A audiobook and MP3 audiobook with a manifest.
8. **Promote deliberately** — replace the canonical release atomically only
   after staging has passed.

The command-line lifecycle intentionally groups these checkpoints into five
plain commands: `analyze`, `generate`, `verify`, `stage`, and `promote`.
`status --watch` shows those five user-facing milestones; the eight checkpoints
explain what the milestones protect.

## Expert view: evidence and decision points

| Checkpoint | Main evidence | Blocking decision |
| --- | --- | --- |
| Read and plan | `production/analysis.json`, reviewed pronunciation data | Unknown terms or unsafe terse dialogue require review. |
| Generate | `production/candidates.json`, content-addressed FLAC takes | Only bounded candidates enter verification. |
| Compare words | `production/asr-evidence-cache.json`, `verification.json` | Both local ASR passes must meet the configured text-fidelity limit. |
| Check recording | per-candidate acoustic results in `verification.json` | Clipping, abnormal duration or unexpected silence rejects a take. |
| Align | `production/forced-alignment.json`, `production/mfa/aligned/` | Every selected take needs local alignment evidence. |
| Select | `production/verification.json` and selection-integrity audit | Ambiguous replacements retain a hash-verified predecessor rather than guessing. |
| Stage | staged M4A, MP3 and hash manifest | The staged files and evidence hashes must agree. |
| Promote | promotion receipt and canonical manifest | Promotion is atomic; a partial staged directory is not a release. |

## Useful commands

```bash
# Default: compatibility-first, serial forced alignment
.venv/bin/audiobook-harness verify projects/my-book

# Optional: inspect and use a bounded CPU profile. This does not relax quality gates.
.venv/bin/audiobook-harness performance --profile auto
.venv/bin/audiobook-harness verify projects/my-book --performance-profile auto

# Watch the five command-level milestones while a chapter is processed
.venv/bin/audiobook-harness status projects/my-book --watch
```

The workflow GIF is a readable local illustration of this contract. It is not a
time estimate or a promise that every take will pass first time.
