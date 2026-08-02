# Issue closure evidence

Each public issue closes only after its acceptance criteria, focused local
profile, and full release verification pass. Profiles do not download models,
contact cloud services, or publish media.

| Issue | Required profile | Close only when |
| --- | --- | --- |
| #2 transaction integrity | `integrity` | Injected failures preserve prior state; no partial receipt or promotion validates. |
| #4 quality corpus | `quality` | Every gate has original/CC0 positive and negative fixtures. |
| #5 quality policy | `quality` | Policy changes are versioned, evidence-bound, repeatable, and never approve listener judgement. |
| #6 supply chain | `supply-chain` | Lock, package, model, and binary provenance checks are deterministic. |
| #8 filesystem safety | `filesystem` | Concurrency and path/cleanup failure behavior is safe and documented. |
| #9 maintainability | `release` | Characterization and full compatibility checks pass after each extraction. |
| #10 operations/security | `operations` | Diagnostics and verified reporting instructions are tested and documented. |
| #11 external readiness | `supply-chain` | Fixture, compatibility, migration, and maturity documentation are complete. |

Run a focused profile with:

```bash
python scripts/verify-harness.py --profile integrity --report /tmp/integrity.json
```

Before tagging a release, run `--profile release`, `scripts/test-harness.sh`,
the wheel build, and `git diff --check`. Attach the resulting report and commit
to the issue comment. Do not close an issue based only on a code review or a
partial profile.
