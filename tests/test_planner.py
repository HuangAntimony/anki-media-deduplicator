from pathlib import Path

from anki_media_deduplicator.cache import NullHashCache
from anki_media_deduplicator.dedupe import find_duplicates
from anki_media_deduplicator.models import (
    CancellationToken,
    DuplicateGroup,
    FileInfo,
    IndexResult,
    NoteSnapshot,
    RestorationState,
)
from anki_media_deduplicator.planner import build_plan


def test_build_plan_scans_notes_once_and_counts_notes_and_occurrences(tmp_path: Path) -> None:
    for name in ("cat812736128736128736.mp3", "cat192837465192837465.mp3"):
        (tmp_path / name).write_bytes(b"same")
    files = []
    for path in tmp_path.iterdir():
        stat = path.stat()
        files.append(FileInfo(path.name, path, stat.st_size, path.suffix, stat.st_mtime_ns))
    groups = find_duplicates(files, NullHashCache(), CancellationToken())
    index = IndexResult(files, 2, 8, 0, 0, 0, 2)
    notes = [
        NoteSnapshot(
            1,
            (
                "[sound:cat812736128736128736.mp3] twice "
                "[sound:cat812736128736128736.mp3]",
            ),
        ),
        NoteSnapshot(2, ('<audio src="cat192837465192837465.mp3">',)),
        NoteSnapshot(3, ("unrelated",)),
    ]

    plan = build_plan(index, groups, notes, tmp_path)

    assert plan.affected_note_ids == {1, 2}
    assert plan.references_to_rewrite == 3
    assert plan.duplicate_files == 1
    assert plan.files_to_trash == 2
    assert plan.reclaimable_bytes == 4
    assert plan.groups[0].choice.filename == "cat.mp3"
    assert plan.groups[0].group.reference_counts == {
        "cat812736128736128736.mp3": 2,
        "cat192837465192837465.mp3": 1,
    }


def test_build_plan_falls_back_when_different_groups_claim_same_new_target(
    tmp_path: Path,
) -> None:
    groups = []
    files = []
    for index, payload in enumerate((b"first", b"second")):
        group_files = []
        for random_suffix in (123456789012345678, 987654321098765432):
            path = tmp_path / f"shared_{random_suffix + index}.jpg"
            path.write_bytes(payload)
            stat = path.stat()
            info = FileInfo(path.name, path, stat.st_size, path.suffix, stat.st_mtime_ns)
            files.append(info)
            group_files.append(info)
        groups.append(DuplicateGroup(group_files, len(payload), f"hash-{index}"))
    index = IndexResult(files, 4, sum(file.size for file in files), 0, 0, 0, 4)

    plan = build_plan(index, groups, [], tmp_path)

    assert [group.choice.state for group in plan.groups] == [
        RestorationState.TARGET_CONFLICT,
        RestorationState.TARGET_CONFLICT,
    ]
    assert len({group.choice.filename for group in plan.groups}) == 2
    assert all(group.choice.existing is not None for group in plan.groups)
    assert plan.files_to_trash == 2


def test_build_plan_reports_monotonic_progress_to_completion(tmp_path: Path) -> None:
    index = IndexResult([], 0, 0, 0, 0, 0, 0)
    notes = [NoteSnapshot(1, ("one",)), NoteSnapshot(2, ("two",))]
    events: list[tuple[int, int]] = []

    build_plan(
        index,
        [],
        notes,
        tmp_path,
        progress=lambda value, maximum: events.append((value, maximum)),
    )

    assert events[0][0] == 0
    assert events[-1][0] == events[-1][1]
    assert events[-1][1] > 0
    assert [value for value, _ in events] == sorted(value for value, _ in events)
