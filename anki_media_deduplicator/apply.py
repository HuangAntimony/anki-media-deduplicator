from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Protocol

from .hashing import files_equal
from .models import ApplyResult, DeduplicationPlan, GroupPlan, NoteSnapshot
from .references import extract_references, rewrite_field


class CollectionPort(Protocol):
    media_dir: Path

    def ensure_media_file(self, source: Path, target_name: str) -> bool: ...

    def iter_notes(self) -> Iterable[NoteSnapshot]: ...

    def update_notes(self, notes: list[NoteSnapshot]) -> None: ...

    def static_references(self) -> set[str]: ...

    def trash_files(self, names: list[str]) -> None: ...


class ApplyExecutor:
    """Apply a plan while preserving references-before-trash crash safety."""

    def __init__(self, *, batch_size: int = 500) -> None:
        self.batch_size = batch_size

    def _is_fresh(self, group_plan: GroupPlan) -> bool:
        files = group_plan.group.files
        for file in files:
            try:
                stat = file.path.stat()
            except OSError:
                return False
            if stat.st_size != file.size or stat.st_mtime_ns != file.mtime_ns:
                return False
        representative = files[0]
        return all(files_equal(representative.path, file.path) for file in files[1:])

    def execute(self, plan: DeduplicationPlan, port: CollectionPort) -> ApplyResult:
        active: list[GroupPlan] = []
        skipped = 0
        for group_plan in plan.groups:
            if not self._is_fresh(group_plan):
                skipped += 1
                continue
            choice = group_plan.choice
            if choice.existing is None:
                if not port.ensure_media_file(group_plan.group.files[0].path, choice.filename):
                    skipped += 1
                    continue
            target = port.media_dir / choice.filename
            if not target.exists() or not files_equal(target, group_plan.group.files[0].path):
                skipped += 1
                continue
            active.append(group_plan)

        replacements = {
            old: group_plan.choice.filename
            for group_plan in active
            for old in group_plan.old_filenames
        }
        changed_notes: list[NoteSnapshot] = []
        replacement_count = 0
        for note in port.iter_notes():
            fields: list[str] = []
            changed = False
            for field in note.fields:
                result = rewrite_field(field, replacements)
                fields.append(result.text)
                replacement_count += result.replacements
                changed |= bool(result.replacements)
            if changed:
                changed_notes.append(NoteSnapshot(note.note_id, tuple(fields)))

        for start in range(0, len(changed_notes), self.batch_size):
            port.update_notes(changed_notes[start : start + self.batch_size])

        remaining = {
            name
            for note in port.iter_notes()
            for field in note.fields
            for name in extract_references(field)
            if name in replacements
        }
        remaining.update(port.static_references().intersection(replacements))
        trash = sorted(name for name in replacements if name not in remaining)
        if trash:
            port.trash_files(trash)
        return ApplyResult(
            len(changed_notes), replacement_count, tuple(trash), skipped
        )
