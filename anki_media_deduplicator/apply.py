from __future__ import annotations

import logging
from collections.abc import Iterable
from pathlib import Path
from typing import Protocol

from .hashing import files_equal
from .i18n import tr
from .models import ApplyResult, DeduplicationPlan, GroupPlan, NoteSnapshot
from .references import extract_references, rewrite_field

logger = logging.getLogger(__name__)


class CollectionPort(Protocol):
    media_dir: Path

    def ensure_media_file(self, source: Path, target_name: str) -> bool: ...

    def iter_notes(self) -> Iterable[NoteSnapshot]: ...

    def update_notes(self, notes: list[NoteSnapshot]) -> None: ...

    def static_references(self) -> set[str]: ...

    def register_media_files(self, names: list[str]) -> list[str]: ...

    def trash_files(self, names: list[str]) -> None: ...


class ApplyExecutor:
    """Apply a plan while preserving references-before-trash crash safety."""

    def __init__(self, *, batch_size: int = 500, progress=None) -> None:
        self.batch_size = batch_size
        self.progress = progress or (lambda label, value=0, maximum=0: None)

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
        self.progress(tr("verifying_media"), 0, len(plan.groups))
        active: list[GroupPlan] = []
        skipped = 0
        for index, group_plan in enumerate(plan.groups, 1):
            if not self._is_fresh(group_plan):
                logger.warning("stale group skipped: %s", group_plan.group.sha256[:12])
                skipped += 1
                continue
            choice = group_plan.choice
            if choice.existing is None and not port.ensure_media_file(
                group_plan.group.files[0].path, choice.filename
            ):
                skipped += 1
                continue
            target = port.media_dir / choice.filename
            if not target.exists() or not files_equal(target, group_plan.group.files[0].path):
                skipped += 1
                continue
            active.append(group_plan)
            self.progress(tr("verifying_media"), index, len(plan.groups))

        replacements = {
            old: group_plan.choice.filename
            for group_plan in active
            for old in group_plan.old_filenames
        }
        changed_notes: list[NoteSnapshot] = []
        replacement_count = 0
        self.progress(tr("updating_notes"), 0, len(plan.affected_note_ids))
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
            self.progress(
                tr("updating_notes"),
                min(start + self.batch_size, len(changed_notes)),
                len(changed_notes),
            )

        remaining = {
            name
            for note in port.iter_notes()
            for field in note.fields
            for name in extract_references(field)
            if name in replacements
        }
        remaining.update(port.static_references().intersection(replacements))
        trash = sorted(name for name in replacements if name not in remaining)
        for name in sorted(remaining):
            logger.warning("referenced duplicate retained: %s", name)
        if trash:
            self.progress(tr("registering_media"), 0, len(trash))
            registered = set(port.register_media_files(trash))
            for name in trash:
                if name not in registered:
                    logger.warning("unregistered duplicate retained: %s", name)
            trash = sorted(registered.intersection(trash))
        if trash:
            self.progress(tr("trashing_media"), 0, len(trash))
            port.trash_files(trash)
            self.progress(tr("trashing_media"), len(trash), len(trash))
        return ApplyResult(
            len(changed_notes), replacement_count, tuple(trash), skipped
        )
