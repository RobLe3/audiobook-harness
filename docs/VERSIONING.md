# Versioning and legacy compatibility

Audiobook Harness **0.5.6** is the current product release. It adds
policy-owned acoustic thresholds and deterministic CC0/original signal corpus
coverage. The existing direct-packaging lock coverage, cue-QA policy identity,
fault-injection coverage, direct-local-filesystem and single-writer contract,
issue-scoped verification profiles, receipt-last persistence, symbolic-link
rejection, strategy-coverage candidate scheduling, reconciled cue-evidence
state, bounded optional span-duration repair, context-stratified
listener-outcome learning, and series-wide outstanding-work reconciler remain
in force. The
eight-phase transactional executor, immutable take/render lineage,
item-scoped decisions, codec-aware tail validation, phase-scoped continuation,
and strict hash-bound verification remain mandatory.
Product releases use SemVer and are independent of report-schema integers,
dependency versions, and local model or asset revisions.

The supported maturity claim for 0.5.6 is controlled maintainer-operated local
production. Unattended production, multi-user coordination, stable public API
compatibility, and third-party operational support remain future goals rather
than promises of this release.

Project-specific audiobook names and historic build labels are not harness product releases.
Historical pre-SemVer project artifacts remain immutable and reusable through
their hashes, but their former project-local labels are not exposed as current
product versions. New reports identify the product as `0.5.6` and bind the
project configuration through `project_profile_sha256`.

Run `audiobook-harness compatibility-audit PROJECT` to inspect a receipt without writing it. Add `--apply` to store `production/version-compatibility-receipt.json`. The receipt hashes existing analysis, candidate, verification, and alignment evidence without rewriting those artifacts or their historical receipts. Missing or changed evidence is never silently accepted.

Versions of Python, Kokoro, Whisper, MFA, FFmpeg, dependencies, schemas, and
model assets keep their own technical identifiers. They are not harness product
versions.
