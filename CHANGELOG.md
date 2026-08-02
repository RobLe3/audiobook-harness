# Changelog

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
