"""Conservative local CPU scheduling helpers.

Profiles describe resource budgets only. They never relax synthesis, transcript
verification, forced-alignment, pronunciation, or staging requirements.
"""

from __future__ import annotations

import os
import platform
import subprocess
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class PerformanceProfile:
    mode: str
    logical_cpus: int
    memory_bytes: int | None
    reserved_cpus: int
    cpu_budget: int
    alignment_jobs: int
    alignment_multiprocessing: bool
    alignment_serial_fallback: bool
    asr_model_workers: int
    asr_threads_per_worker: int
    synthesis_workers: int

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _memory_bytes() -> int | None:
    if platform.system() == "Darwin":
        result = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, check=False)
        if result.returncode == 0:
            try:
                return int(result.stdout.strip())
            except ValueError:
                pass
    try:
        return int(os.sysconf("SC_PHYS_PAGES")) * int(os.sysconf("SC_PAGE_SIZE"))
    except (AttributeError, OSError, ValueError):
        return None


def resolve_profile(
    mode: str = "legacy", *, logical_cpus: int | None = None, memory_bytes: int | None = None
) -> PerformanceProfile:
    """Return serial compatibility settings or a bounded auto-sized profile."""
    if mode not in {"legacy", "auto"}:
        raise ValueError("mode must be 'legacy' or 'auto'")
    cpus = max(1, int(logical_cpus if logical_cpus is not None else os.cpu_count() or 1))
    memory = _memory_bytes() if memory_bytes is None else memory_bytes
    if mode == "legacy":
        return PerformanceProfile(mode, cpus, memory, 0, 1, 1, False, False, 1, 0, 1)
    reserved = min(max(2, (cpus + 3) // 4), max(0, cpus - 1))
    budget = max(1, cpus - reserved)
    asr_workers = 2 if cpus >= 8 and (memory is None or memory >= 32 * 1024**3) else 1
    return PerformanceProfile(
        mode, cpus, memory, reserved, budget, min(6, budget), budget > 1, True,
        asr_workers, max(1, budget // asr_workers), min(4, max(1, budget // 3)),
    )
