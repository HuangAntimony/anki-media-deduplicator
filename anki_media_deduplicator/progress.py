from __future__ import annotations

import threading
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProgressSnapshot:
    label: str
    value: int = 0
    maximum: int = 0


class ProgressState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._snapshot = ProgressSnapshot("Preparing...")

    def update(self, label: str, value: int = 0, maximum: int = 0) -> None:
        with self._lock:
            self._snapshot = ProgressSnapshot(label, value, maximum)

    def snapshot(self) -> ProgressSnapshot:
        with self._lock:
            return self._snapshot

