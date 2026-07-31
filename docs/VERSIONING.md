# Versioning and legacy compatibility

Audiobook Harness **0.4.10** is the current product release. It adds an
eight-phase transactional executor, phase-specific dependency identities,
semantic success receipts, typed tool outcomes, and contextual pronunciation
preflight. Immutable take/render lineage, item-scoped decisions, codec-aware
tail validation, phase-scoped continuation, and strict hash-bound verification
remain mandatory.
Product releases use SemVer and are independent of report-schema integers,
dependency versions, and local model or asset revisions.

Project-specific audiobook names and historic build labels are not harness product releases.
Historical pre-SemVer project artifacts remain immutable and reusable through
their hashes, but their former project-local labels are not exposed as current
product versions. New reports identify the product as `0.4.10` and bind the
project configuration through `project_profile_sha256`.

Run `audiobook-harness compatibility-audit PROJECT` to inspect a receipt without writing it. Add `--apply` to store `production/version-compatibility-receipt.json`. The receipt hashes existing analysis, candidate, verification, and alignment evidence without rewriting those artifacts or their historical receipts. Missing or changed evidence is never silently accepted.

Versions of Python, Kokoro, Whisper, MFA, FFmpeg, dependencies, schemas, and
model assets keep their own technical identifiers. They are not harness product
versions.
