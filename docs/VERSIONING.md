# Versioning and legacy compatibility

Audiobook Harness **0.4.2** is the current product release. It adds
manifest-bound listener-feedback records, local draft persistence, conservative
default promotion, and listener-history preflight evidence. Product releases
use SemVer and are independent of report-schema integers, dependency versions,
and local model or asset revisions.

The NORDLICHT production work that informed this release previously called its narration method `8.3.3` and its soundscape extension `8.4`. Those labels are immutable legacy artifact-contract identifiers, not current Audiobook Harness versions. Current code and new reports identify the product as `0.4.2`; compatibility receipts retain the legacy labels only to prove which historical evidence may be reused.

Run `audiobook-harness compatibility-audit PROJECT` to inspect a receipt without writing it. Add `--apply` to store `production/version-compatibility-receipt.json`. The receipt hashes existing analysis, candidate, verification, and alignment evidence without rewriting those artifacts or their historical receipts. Missing or changed evidence is never silently accepted.

Versions of Python, Kokoro, Whisper, MFA, FFmpeg, dependencies, schemas, and model assets keep their own identifiers. They must never be mechanically replaced with the product version.
