# Filesystem and concurrency safety

Audiobook Harness supports one production writer for one project directory at a
time. The project lock covers direct commands and `produce`; a second writer
fails instead of attempting to coordinate phase, repair, stage, or promotion
work. A stale lock is recoverable only when its recorded process no longer
exists and the lock record has not changed.

## Supported storage contract

Use a direct path on a local filesystem whose directory creation and atomic
replacement operations are visible to the same host. The harness relies on
temporary sibling files plus `fsync` and `os.replace` for authoritative JSON,
then validates hashes before a receipt, stage, or promotion becomes reusable.

The following are intentionally unsupported for production authority:

- network, sync-folder, FUSE, or object-backed filesystems with uncertain lock
  or rename semantics;
- two writers, including a second terminal or external automation, targeting
  the same project;
- symbolic-link paths for staging, stage validation, or promotion;
- manual changes to `production/`, `staging/`, or `deliverables/` while a
  command owns the project.

Use a local direct path and stop the active command before moving a project.
The Review Center is read/review-only and never becomes a second production
writer.

## Failure behavior

If a write, validation, stage, or promotion operation fails, the harness keeps
the previous hash-valid state where possible, invalidates incomplete phase
receipts, and removes temporary replacement output. It never treats a partial
JSON file, incomplete receipt, changed staged media file, or unowned stage
directory as reusable.

Permission or storage failures are environment failures: repair the filesystem
condition, then resume with `produce --resume --dry-run` before executing a
bounded continuation. Do not copy media manually or remove a lock owned by a
live process.

## Filename and cleanup rules

Project source and generated files may use Unicode characters and spaces. Stage
manifest media paths must remain relative, must not contain parent traversal,
and must resolve below the direct stage root. Cleanup requires a regular
harness-owned marker bound to the same project; a missing, malformed, foreign,
or symbolic-link marker stops the operation before deletion.
