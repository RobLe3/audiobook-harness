# Operations and diagnostics

Audiobook Harness is single-writer and local-first. It does not contact cloud
services or download models during production.

| Exit code | Meaning | Operator action |
| --- | --- | --- |
| 0 | completed | inspect staged evidence before promotion |
| 2 | invalid input | correct command, project, or decision input |
| 3 | environment | install or explicitly configure the missing local dependency |
| 4 | objective quality rejection | use the bounded repair/review evidence; do not retry unchanged work |
| 5 | integrity failure | preserve evidence and reconcile hashes before retrying |
| 6 | listener review required | use the hash-bound Review Center and finalize a decision |
| 7 | processing failure | inspect the phase result and retry only the failed phase when allowed |
| 8 | invariant violation | stop production and file a private security/bug report with redacted evidence |

Structured CLI errors contain a type, message, and stable exit code. Logs and
reports must not include manuscripts, media bytes, secrets, or private voice
assets. Supported production is one writer on a direct local filesystem with
atomic rename support; see `FILESYSTEM_SAFETY.md`.
