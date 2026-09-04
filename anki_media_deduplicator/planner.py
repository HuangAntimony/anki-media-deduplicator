from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from pathlib import Path

from .filename_inference import conflict_fallback, select_canonical
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
    *,
    progress: Callable[[int, int], None] | None = None,
) -> DeduplicationPlan:
    report = progress or (lambda value, maximum: None)
    maximum = (2 * len(notes)) + (2 * len(groups))
    completed = 0
    report(0, maximum)
    duplicate_names = {file.filename for group in groups for file in group.files}
    counts: Counter[str] = Counter()
    note_references: dict[int, list[str]] = {}
    for note in notes:
        references = [name for field in note.fields for name in extract_references(field)]
        matched = [name for name in references if name in duplicate_names]
        if matched:
            note_references[note.note_id] = matched
            counts.update(matched)
        completed += 1
        report(completed, maximum)

    proposed_choices = []
    for group in groups:
        group.reference_counts = {
            file.filename: counts[file.filename] for file in group.files if counts[file.filename]
        }
        choice = select_canonical(group, group.reference_counts, media_dir)
        proposed_choices.append((group, choice))
        completed += 1
        report(completed, maximum)

    new_target_counts = Counter(
        choice.filename for _, choice in proposed_choices if choice.existing is None
    )
    group_plans: list[GroupPlan] = []
    replacements: dict[str, str] = {}
    for group, choice in proposed_choices:
        if choice.existing is None and new_target_counts[choice.filename] > 1:
            choice = conflict_fallback(group, group.reference_counts)
        group.canonical = choice.existing
        old_names = tuple(
            file.filename for file in group.files if file.filename != choice.filename
        )
        # A newly restored target means every randomized member is old.
        if choice.existing is None:
            old_names = tuple(file.filename for file in group.files)
        group_plans.append(GroupPlan(group, choice, old_names))
        replacements.update({name: choice.filename for name in old_names})
        completed += 1
        report(completed, maximum)

    affected_ids: set[int] = set()
    reference_count = 0
    for note in notes:
        note_id = note.note_id
        names = note_references.get(note_id, ())
        matched_count = sum(name in replacements for name in names)
        if matched_count:
            affected_ids.add(note_id)
            reference_count += matched_count
        completed += 1
        report(completed, maximum)

    return DeduplicationPlan(
        group_plans,
        notes,
        index.media_file_count,
        index.total_size,
        index.protected_skipped,
        affected_ids,
        reference_count,
    )
