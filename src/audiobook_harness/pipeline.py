from __future__ import annotations

import ast
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from . import __version__
from .project import write_json
from .run_journal import phase_receipt_is_valid, valid_phase_repair_receipt


class PhaseIdentityError(ValueError):
    """A phase declared an invalid implementation dependency boundary."""


@dataclass(frozen=True)
class Phase:
    number: int
    name: str
    depends_on: tuple[int, ...]
    required_artifacts: tuple[str, ...]
    success_predicates: tuple[tuple[str, str], ...] = ()
    implementation_dependencies: tuple[str, ...] = ()
    maximum_attempts: int = 1


PHASES = (
    Phase(
        1,
        "analysis",
        (),
        (
            "analysis.json",
            "manuscript-structure.json",
            "spoken-forms.json",
            "dialogue-speaker-map.json",
            "discourse-prosody-map.json",
            "speaker-energy-map.json",
            "tts-risk-map.json",
            "performance-units.json",
            "candidate-plan.json",
        ),
        (),
        ("analysis.py", "project.py", "candidate_scheduler.py", "context_protocol.py"),
    ),
    Phase(
        2,
        "synthesis",
        (1,),
        ("candidates.json", "pronunciation-context-preflight.json"),
        (("pronunciation-context-preflight.json", "ok"),),
        (
            "tts.py#generate,model_paths,_candidate_identity,_source_hash",
            "pronunciation.py",
            "candidate_scheduler.py",
        ),
        2,
    ),
    Phase(
        3,
        "candidate_realization",
        (2,),
        ("generation.json",),
        (("generation.json", "ok"),),
        ("tts.py#realize_generation_manifest",),
    ),
    Phase(
        4,
        "cue_qa",
        (3,),
        (
            "verification.json",
            "forced-alignment.json",
            "candidate-selection-integrity.json",
            "candidate-strategy-ledger.json",
            "pronunciation-audit.json",
            "phoneme-duration-audit.json",
            "pause-economy-lint.json",
            "energy-lint.json",
            "expressive-realization.json",
            "repair-diagnosis.json",
            "repair-plan.json",
            "effective-cue-state.json",
            "advisory-quality.json",
        ),
        (
            ("verification.json", "ok"),
            ("candidate-selection-integrity.json", "ok"),
            ("pronunciation-audit.json", "ok"),
            ("phoneme-duration-audit.json", "ok"),
            ("pause-economy-lint.json", "ok"),
            ("energy-lint.json", "ok"),
            ("expressive-realization.json", "ok"),
        ),
        (
            "quality.py",
            "quality_policy.py",
            "selection_integrity.py",
            "asr_cache.py",
            "repair_analysis.py",
            "advisory_quality.py",
        ),
        2,
    ),
    Phase(
        5,
        "pre_mix_gate",
        (4,),
        ("release-contract.json",),
        (("release-contract.json", "ok"),),
        ("tts.py#prepare_release_contract", "selection_integrity.py"),
    ),
    Phase(
        6,
        "assembly",
        (5,),
        ("assembly-manifest.json",),
        (("assembly-manifest.json", "ok"),),
        (
            "tts.py#assemble_selected,_package,_validated_ordered_takes",
            "boundary_repair.py",
        ),
    ),
    Phase(
        7,
        "post_mix_qa",
        (6,),
        ("full-file-fidelity.json", "chapter-ending-audit.json"),
        (
            ("full-file-fidelity.json", "ok"),
            ("chapter-ending-audit.json", "ok"),
        ),
        ("tts.py#post_mix_quality,_validated_ordered_takes", "measurements.py"),
    ),
    Phase(
        8,
        "package",
        (7,),
        (
            "encoded-deliverable-quality.json",
            "stage-manifest.json",
            "review-manifest.json",
            "quality-measurements.json",
            "encoded-full-file-fidelity.json",
            "perceptual-regression.json",
        ),
        (("encoded-deliverable-quality.json", "ok"),),
        (
            "tts.py#stage,_stage_into,encode_assembled,_prepare_stage_directory,_probe_audio",
            "encoded_quality.py",
            "tts.py#promote",
            "review.py",
        ),
    ),
)


def execution_start_phase(phase: int | None) -> int | None:
    """Every declared phase is now an independently replayable transaction."""
    return phase


def pipeline_contract() -> dict[str, Any]:
    payload: dict[str, Any] = {
        "version": 1,
        "audiobook_harness_version": __version__,
        "phases": [asdict(phase) for phase in PHASES],
    }
    payload["identity_sha256"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return payload


def validate_phase_implementation_dependencies(
    repo: Path, phases: tuple[Phase, ...] = PHASES
) -> None:
    """Fail closed when a declared phase implementation dependency is invalid."""

    package = (repo / "src/audiobook_harness").resolve()
    for phase in phases:
        seen: set[str] = set()
        artifact_names: set[str] = set()
        for artifact in phase.required_artifacts:
            artifact_path = Path(artifact)
            if (
                not artifact
                or artifact_path.is_absolute()
                or ".." in artifact_path.parts
                or artifact in artifact_names
            ):
                raise PhaseIdentityError(
                    f"phase {phase.number} declares invalid or duplicate artifact: {artifact!r}"
                )
            artifact_names.add(artifact)
        predicate_names: set[str] = set()
        for artifact, _field in phase.success_predicates:
            if artifact not in artifact_names or artifact in predicate_names:
                raise PhaseIdentityError(
                    f"phase {phase.number} declares invalid or duplicate success predicate: {artifact!r}"
                )
            predicate_names.add(artifact)
        for dependency in phase.implementation_dependencies:
            filename, separator, selectors_text = dependency.partition("#")
            if dependency in seen:
                raise PhaseIdentityError(
                    f"phase {phase.number} declares duplicate implementation dependency: {dependency}"
                )
            seen.add(dependency)
            relative = Path(filename)
            if ".." in relative.parts:
                raise PhaseIdentityError(
                    f"phase {phase.number} implementation dependency escapes package: {dependency}"
                )
            if (
                not filename
                or relative.is_absolute()
                or (separator and not selectors_text)
            ):
                raise PhaseIdentityError(
                    f"phase {phase.number} implementation dependency is not a safe package-relative path: {dependency}"
                )
            path = package / relative
            if path.is_symlink():
                raise PhaseIdentityError(
                    f"phase {phase.number} implementation dependency must not be a symlink: {dependency}"
                )
            path = path.resolve()
            if not path.is_relative_to(package):
                raise PhaseIdentityError(
                    f"phase {phase.number} implementation dependency escapes package: {dependency}"
                )
            if not path.is_file():
                raise PhaseIdentityError(
                    f"phase {phase.number} implementation dependency does not exist: {dependency}"
                )
            if selectors_text:
                selectors = tuple(
                    selector.strip() for selector in selectors_text.split(",")
                )
                if any(not selector for selector in selectors) or len(
                    set(selectors)
                ) != len(selectors):
                    raise PhaseIdentityError(
                        f"phase {phase.number} implementation selectors are not unique: {dependency}"
                    )
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
                available = {
                    node.name
                    for node in tree.body
                    if isinstance(
                        node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
                    )
                }
                missing = [
                    selector for selector in selectors if selector not in available
                ]
                if missing:
                    raise PhaseIdentityError(
                        f"phase {phase.number} implementation selector is missing: {dependency} ({', '.join(missing)})"
                    )


def phase_input_identity(project: Path, repo: Path, phase: Phase) -> str:
    """Hash only authored inputs, predecessor receipts, and phase-owned code."""
    paths = [
        project / "project.yaml",
        project / "lexicon.json",
        repo / "models.lock.json",
    ]
    paths.extend(sorted((project / "source").glob("*.txt")))
    package = repo / "src/audiobook_harness"
    validate_phase_implementation_dependencies(repo, phases=(phase,))
    implementation: list[tuple[str, Path, tuple[str, ...]]] = []
    for dependency in sorted(phase.implementation_dependencies):
        filename, _, selectors = dependency.partition("#")
        implementation.append(
            (
                dependency,
                package / filename,
                tuple(value for value in selectors.split(",") if value),
            )
        )
    for dependency in phase.depends_on:
        paths.append(project / "production/phase-receipts" / f"step-{dependency}.json")
    rows = []
    for path in paths:
        if path.is_file():
            try:
                logical_path = path.resolve().relative_to(project.resolve()).as_posix()
            except ValueError:
                try:
                    logical_path = path.resolve().relative_to(repo.resolve()).as_posix()
                except ValueError as error:
                    raise PhaseIdentityError(
                        f"phase {phase.number} input is outside project/repository: {path}"
                    ) from error
            rows.append(
                {
                    "path": logical_path,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "bytes": path.stat().st_size,
                }
            )
    for label, path, selectors in implementation:
        if not path.is_file():
            raise PhaseIdentityError(
                f"phase {phase.number} implementation dependency does not exist: {label}"
            )
        content = path.read_text(encoding="utf-8")
        selected = content
        if selectors:
            tree = ast.parse(content)
            chunks = []
            for node in tree.body:
                if (
                    isinstance(
                        node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
                    )
                    and node.name in selectors
                ):
                    segment = ast.get_source_segment(content, node)
                    if segment is not None:
                        chunks.append(segment)
            if len(chunks) != len(selectors):
                raise PhaseIdentityError(
                    f"phase {phase.number} implementation selector is missing: {label}"
                )
            selected = "\n\n".join(chunks)
        encoded = selected.encode("utf-8")
        rows.append(
            {
                "path": f"implementation/{label}",
                "sha256": hashlib.sha256(encoded).hexdigest(),
                "bytes": len(encoded),
            }
        )
    phase_contract = asdict(phase)
    phase_contract["implementation_dependencies"] = tuple(
        sorted(phase.implementation_dependencies)
    )
    value = {
        "phase_contract": phase_contract,
        "phase": phase.number,
        "inputs": rows,
    }
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def audit_pipeline(project: Path) -> dict[str, Any]:
    production = project / "production"
    phases = []
    contiguous = True
    for phase in PHASES:
        missing = [
            name
            for name in phase.required_artifacts
            if not (production / name).is_file()
        ]
        failed_predicates = []
        for artifact, field in phase.success_predicates:
            try:
                value = json.loads((production / artifact).read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                value = None
            if not isinstance(value, dict) or value.get(field) is not True:
                failed_predicates.append(f"{artifact}.{field}")
        complete = contiguous and not missing and not failed_predicates
        contiguous = complete
        phases.append(
            {
                "number": phase.number,
                "name": phase.name,
                "complete": complete,
                "missing": missing,
                "failed_predicates": failed_predicates,
            }
        )
    report = {
        **pipeline_contract(),
        "phase_status": phases,
        "resume_from_phase": next(
            (row["number"] for row in phases if not row["complete"]), None
        ),
        "ok": all(row["complete"] for row in phases),
    }
    write_json(production / "pipeline-audit.json", report)
    return report


def resume_plan(
    project: Path, *, input_identity: str, repo: Path | None = None
) -> dict[str, Any]:
    """Plan one eight-phase resume using receipts and an optional repair scope."""

    repair = valid_phase_repair_receipt(project, current_input_identity=input_identity)
    owner = int(repair["owner_phase"]) if repair else None
    base_identity = str(repair["base_input_identity"]) if repair else input_identity
    rows = []
    phase_identities: dict[str, str] = {}
    blocked = False
    for phase in PHASES:
        identity = (
            phase_input_identity(project, repo, phase)
            if repo is not None
            else base_identity
            if owner is not None and phase.number < owner
            else input_identity
        )
        phase_identities[str(phase.number)] = identity
        reusable = (
            not blocked
            and (owner is None or phase.number < owner)
            and phase_receipt_is_valid(
                project, step=phase.number, input_identity=identity
            )
        )
        if not reusable:
            blocked = True
        rows.append(
            {
                "phase": phase.number,
                "name": phase.name,
                "action": "REUSE" if reusable else "RUN",
                "reason": (
                    "hash-bound phase receipt is current"
                    if reusable
                    else "phase-scoped repair owns this phase"
                    if owner == phase.number
                    else "first incomplete or dependent phase"
                ),
            }
        )
    start = next((row["phase"] for row in rows if row["action"] == "RUN"), None)
    effective_start = execution_start_phase(start)
    if effective_start is not None and effective_start != start:
        for row in rows:
            if effective_start <= int(row["phase"]) < int(start):
                row["action"] = "RUN"
                row["reason"] = "atomic production action also owns this phase"
    return {
        "version": 1,
        "input_identity": input_identity,
        "phase_input_identities": phase_identities,
        "repair": repair,
        "phases": rows,
        "start_phase": effective_start,
    }
