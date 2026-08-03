# Changelog

## 0.7.3

- Distinguish finalized listener feedback from a genuinely new replacement that needs review.
- Expose item-level decision, remediation, listener-complete, correction-complete, and publication-eligibility states in the Review Center API.
- Prevent a finalized rejection or uncertainty from being presented as an unfinished review of the same audio identity.

## 0.7.2

- Add a fail-visible Review Center page/API schema handshake with one automatic cache-busting reload.
- Distinguish automation execution state, convergence outcome, and whether an audio repair actually ran.
- Keep listener summaries exhaustive and show the complete review queue without silently hiding later chapters.

## 0.7.1

- Stop the Review Center automation monitor from relaunching a terminal repair
  when its evidence identity has not changed.
- Report execution state, production outcome, and repair exhaustion separately
  so a successful controller command cannot imply that an audio repair passed.

## 0.7.0

- Add an opt-in, project-scoped convergence worker that starts with Review Center, resumes only evidence-bounded work, and stops for review, a no-progress identity, or its configured iteration budget.
- Keep status requests read-only while exposing a built-in `converge` command and bounded Review Center automation settings.

## 0.6.1

- Add a read-only issue-hygiene audit and a bounded hardening issue template to
  keep future maintenance work reproducible and closure-oriented.

## 0.6.0

- Complete the public hardening evidence set: offline provenance audit,
  redistributable fixture, documented diagnostics and private security process.
- Extend the quality corpus coverage contract and local issue-scoped verifier.

## 0.5.8

- Add an HTTP regression test proving the Review Center rejects a review-draft
  write with HTTP 409 while production owns the project writer lock.

## 0.5.7

- Place all review-state mutations behind the project single-writer lock,
  including direct feedback commands and both Review Center server variants.
- Return a clear conflict response when a live production writer owns the
  project, preserving the existing review data for a later retry.

## 0.5.6

- Move acoustic quality thresholds into the versioned, hash-bound quality
  policy contract.
- Expand the CC0/original model-free quality corpus with deterministic signal
  references for clipping, duration, silence, long-word timing, and noise.

## 0.5.5

- Add process-level regressions proving direct stage and promotion commands
  cannot race a live project writer.
- Bind the versioned quality-policy implementation into cue-QA phase identity,
  so a policy change invalidates its receipt and downstream evidence.

## 0.5.4

- Extend transaction fault-injection coverage to status/event persistence,
  storage exhaustion, permission failures, and symbolic-link ownership metadata.
- Make a phase-start event failure fail closed through the typed transactional
  path instead of escaping before rollback handling.
- Document the supported single-writer and direct-local-filesystem contract.

## 0.5.3

- Add issue-scoped, offline verification profiles and a public closure-evidence
  map so maintenance work is reproducible without a hosted workflow.
- Preserve receipt-last phase commits when operational status persistence fails;
  a failed status write cannot leave a reusable success receipt behind.
- Exercise atomic JSON replacement under a simulated interruption and reject
  staging or promotion through any symbolic-link path component.

## 0.5.2

- Redirect the loopback Review Center root to its project-agnostic chooser so
  opening the local server never produces a generic 404 page.
- Make stage-receipt creation fail closed for missing, duplicate, or mixed
  directory media inputs; retain validation of receipt reuse as a second gate.
- Bind every quality disposition to a stable policy-contract identity and
  strengthen writer-lock teardown so a process cannot remove a replaced lease.

## 0.5.1

- Align the public package, reports, agent contract, README, and compatibility
  documentation on the 0.5.1 product identity.
- Clarify that review-iteration receipts and the local Review Center remain
  review-only and never replace staged publication authority.
- Keep the existing bounded repair and phase-resume behavior unchanged; the
  project-specific autonomous convergence controller remains outside this
  public package until its implementation is ported and tested here.

## 0.4.7

- Treat the PCM assembly tail as authoritative while allowing at most one
  codec frame of AAC or MP3 timing variance in encoded-deliverable QA.
- Compile hash-bound listener feedback immediately after review finalization.
- Report finalized rejected or uncertain items as queued correction work rather
  than asking the reviewer to finalize the same audio again.
- Preserve phase-scoped continuation and keep generation separate from final
  publication approval.

## 0.4.6

- Add an evidence-led candidate strategy ledger and retain hash-valid candidates
  while bounded retries add only untried, unique alternatives.
- Prevent duplicate or already-generated retry variants from consuming the
  per-unit candidate budget.
- Unify production resume reporting on the public eight-phase contract.
- Add objective, hash-bound phase-scoped repair receipts that preserve valid
  predecessor phases without waiving quality gates.
- Add evidence-bound multi-token foreign-phrase ASR segmentation handling.
- Serve identity-safe review actions, media, drafts, finalization, and advisory
  ASR activity from one loopback-only review process.

## 0.4.3

- Establish Audiobook Harness 0.4.x as the sole current harness identity.
- Add the eight-phase pipeline, feature-parity, and quality-vector contracts.
- Add discourse-prosody, speaker-energy, emotion, and candidate-plan analysis.
- Add deliberate pause assembly, ending protection, encoded QA, and the
  mastered-context review schema.

## 0.4.2

- Save local review drafts and finalized decisions without requiring downloads.
- Record categorized listener feedback in an append-only, hash-bound ledger.
- Compile feedback summaries and gate listener-derived default promotion.
- Add listener-history preflight evidence to manuscript analysis.

## 0.4.0

- Adds source-preserving manuscript, spoken-form, dialogue, prosody, risk and performance-unit contracts.
- Adds hash-bound mandatory local review before promotion.
- Adds an explicit, inventory-bound v0.3 project upgrade command.
- Preserves the local-only, staged, evidence-bound release model; no hosted workflow or cloud service is added.

## 0.4.1

- Establishes one authoritative product version across package metadata, CLI output, reports, and documentation.
- Separates current SemVer from immutable pre-SemVer project artifacts.
- Adds a hash-bound, non-destructive compatibility audit for reusable historical evidence.
- Rejects stale local Docker smoke images as current-checkout verification.
