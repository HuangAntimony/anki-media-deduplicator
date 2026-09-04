from pathlib import Path

from anki_media_deduplicator.cache import NullHashCache
from anki_media_deduplicator.dedupe import find_duplicates
from anki_media_deduplicator.models import (
    CancellationToken,
    FileInfo,
    IndexResult,
    NoteSnapshot,
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
    assert plan.duplicate_files == 2
    assert plan.reclaimable_bytes == 8
    assert plan.groups[0].choice.filename == "cat.mp3"
    assert plan.groups[0].group.reference_counts == {
        "cat812736128736128736.mp3": 2,
        "cat192837465192837465.mp3": 1,
    }
