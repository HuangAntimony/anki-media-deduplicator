from __future__ import annotations

import threading
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class CancelledError(RuntimeError):
    pass


class CancellationToken:
    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise CancelledError("operation cancelled")


@dataclass(frozen=True, slots=True)
class FileInfo:
    filename: str
    path: Path
    size: int
    extension: str
    mtime_ns: int


@dataclass(slots=True)
class IndexResult:
    files: list[FileInfo]
    total_entries: int
    total_size: int
    protected_skipped: int
    zero_byte_skipped: int
    invalid_skipped: int


@dataclass(slots=True)
class DuplicateGroup:
    files: list[FileInfo]
    size: int
    sha256: str
    canonical: FileInfo | None = None
    reclaimable_bytes: int = 0
    reference_counts: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.reclaimable_bytes:
            self.reclaimable_bytes = self.size * max(0, len(self.files) - 1)


class RestorationState(str, Enum):
    EXISTING_CLEAN = "existing_clean"
    UNIQUE_INFERENCE = "unique_inference"
    AMBIGUOUS = "ambiguous"
    NOT_ANKIDROID_PATTERN = "not_ankidroid_pattern"
    TARGET_CONFLICT = "target_conflict"


@dataclass(frozen=True, slots=True)
class CanonicalChoice:
    filename: str
    state: RestorationState
    existing: FileInfo | None

