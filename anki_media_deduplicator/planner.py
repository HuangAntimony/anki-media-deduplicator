from __future__ import annotations

from collections import Counter
from pathlib import Path

from .filename_inference import select_canonical
from .models import (
    DeduplicationPlan,
    DuplicateGroup,
    GroupPlan,
    IndexResult,
    NoteSnapshot,
)
from .references import extract_references


def build_plan(
    index: IndexResult,
    groups: list[DuplicateGroup],
    notes: list[NoteSnapshot],
    media_dir: Path,
) -> DeduplicationPlan:
    duplicate_names = {file.filename for group in groups for file in group.files}
    counts: Counter[str] = Counter()
    note_references: dict[int, list[str]] = {}
    for note in notes:
        references = [name for field in note.fields for name in extract_references(field)]
        matched = [name for name in references if name in duplicate_names]
        if matched:
            note_references[note.note_id] = matched
            counts.update(matched)

    group_plans: list[GroupPlan] = []
    replacements: dict[str, str] = {}
    for group in groups:
        group.reference_counts = {
            file.filename: counts[file.filename] for file in group.files if counts[file.filename]
        }
        choice = select_canonical(group, group.reference_counts, media_dir)
        group.canonical = choice.existing
        old_names = tuple(
            file.filename for file in group.files if file.filename != choice.filename
        )
        # A newly restored target means every randomized member is old.
        if choice.existing is None:
            old_names = tuple(file.filename for file in group.files)
        group_plans.append(GroupPlan(group, choice, old_names))
        replacements.update({name: choice.filename for name in old_names})

    affected_ids: set[int] = set()
    reference_count = 0
    for note_id, names in note_references.items():
        matched_count = sum(name in replacements for name in names)
        if matched_count:
            affected_ids.add(note_id)
            reference_count += matched_count

    return DeduplicationPlan(
        group_plans,
        notes,
        index.media_file_count,
        index.total_size,
        index.protected_skipped,
        affected_ids,
        reference_count,
    )
