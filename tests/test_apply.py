from pathlib import Path

import pytest

from anki_media_deduplicator.apply import ApplyExecutor
from anki_media_deduplicator.models import (
    CanonicalChoice,
    DeduplicationPlan,
    DuplicateGroup,
    FileInfo,
    GroupPlan,
    NoteSnapshot,
    RestorationState,
)


def file_info(path: Path) -> FileInfo:
    stat = path.stat()
    return FileInfo(path.name, path, stat.st_size, path.suffix, stat.st_mtime_ns)


def make_plan(tmp_path: Path) -> DeduplicationPlan:
    names = ("cat812736128736128736.mp3", "cat192837465192837465.mp3")
    for name in names:
        (tmp_path / name).write_bytes(b"same")
    files = [file_info(tmp_path / name) for name in names]
    group = DuplicateGroup(files, 4, "hash")
    choice = CanonicalChoice("cat.mp3", RestorationState.UNIQUE_INFERENCE, None)
    group_plan = GroupPlan(group, choice, names)
    notes = [NoteSnapshot(1, (f"[sound:{names[0]}]",)), NoteSnapshot(2, (f"[sound:{names[1]}]",))]
    return DeduplicationPlan([group_plan], notes, 2, 8, 0, {1, 2}, 2)


class FakePort:
    def __init__(self, tmp_path: Path, notes: list[NoteSnapshot]) -> None:
        self.media_dir = tmp_path
        self.notes = {note.note_id: list(note.fields) for note in notes}
        self.events: list[str] = []
        self.trashed: list[str] = []
        self.static: set[str] = set()
        self.fail_updates = False
        self.ignored_note_ids: set[int] = set()

    def ensure_media_file(self, source: Path, target_name: str) -> bool:
        self.events.append("ensure")
        (self.media_dir / target_name).write_bytes(source.read_bytes())
        return True

    def iter_notes(self, progress=None):
        snapshots = [NoteSnapshot(note_id, tuple(fields)) for note_id, fields in self.notes.items()]
        if progress:
            progress(0, len(snapshots))
            for index in range(1, len(snapshots) + 1):
                progress(index, len(snapshots))
        return snapshots

    def update_notes(self, notes: list[NoteSnapshot]) -> None:
        self.events.append("update")
        if self.fail_updates:
            raise RuntimeError("update failed")
        for note in notes:
            if note.note_id not in self.ignored_note_ids:
                self.notes[note.note_id] = list(note.fields)

    def static_references(self) -> set[str]:
        return self.static

    def register_media_files(self, names: list[str]) -> list[str]:
        self.events.append("register")
        return names

    def trash_files(self, names: list[str]) -> None:
        self.events.append("trash")
        self.trashed.extend(names)


class SyncAwareFakePort(FakePort):
    """Model Anki's rule that only registered media gets deletion tombstones."""

    def __init__(self, tmp_path: Path, notes: list[NoteSnapshot]) -> None:
        super().__init__(tmp_path, notes)
        self.registered_media: set[str] = set()
        self.remote_media: set[str] = set()
        self.deletion_tombstones: set[str] = set()

    def register_media_files(self, names: list[str]) -> list[str]:
        self.events.append("register")
        registered = [name for name in names if (self.media_dir / name).is_file()]
        self.registered_media.update(registered)
        return registered

    def trash_files(self, names: list[str]) -> None:
        super().trash_files(names)
        self.deletion_tombstones.update(self.registered_media.intersection(names))

    def media_downloads_on_sync(self) -> set[str]:
        return self.remote_media - self.deletion_tombstones


def test_apply_creates_target_updates_all_references_then_trashes(tmp_path: Path) -> None:
    plan = make_plan(tmp_path)
    port = FakePort(tmp_path, plan.notes)

    result = ApplyExecutor(batch_size=1).execute(plan, port)

    assert port.events == ["ensure", "update", "update", "register", "trash"]
    assert port.notes[1] == ["[sound:cat.mp3]"]
    assert port.notes[2] == ["[sound:cat.mp3]"]
    assert set(port.trashed) == {"cat812736128736128736.mp3", "cat192837465192837465.mp3"}
    assert result.updated_notes == 2
    assert result.rewritten_references == 2


def test_apply_registers_untracked_media_before_trash_so_sync_does_not_restore_it(
    tmp_path: Path,
) -> None:
    plan = make_plan(tmp_path)
    port = SyncAwareFakePort(tmp_path, plan.notes)
    port.remote_media.update(plan.groups[0].old_filenames)

    ApplyExecutor().execute(plan, port)

    assert port.media_downloads_on_sync() == set()
    assert port.events[-2:] == ["register", "trash"]


def test_note_failure_happens_before_any_trash(tmp_path: Path) -> None:
    plan = make_plan(tmp_path)
    port = FakePort(tmp_path, plan.notes)
    port.fail_updates = True

    with pytest.raises(RuntimeError, match="update failed"):
        ApplyExecutor().execute(plan, port)

    assert "trash" not in port.events


def test_stale_file_skips_entire_group(tmp_path: Path) -> None:
    plan = make_plan(tmp_path)
    port = FakePort(tmp_path, plan.notes)
    (tmp_path / plan.groups[0].old_filenames[0]).write_bytes(b"changed")

    result = ApplyExecutor().execute(plan, port)

    assert result.skipped_groups == 1
    assert not port.events


def test_deleted_file_skips_entire_group(tmp_path: Path) -> None:
    plan = make_plan(tmp_path)
    port = FakePort(tmp_path, plan.notes)
    (tmp_path / plan.groups[0].old_filenames[0]).unlink()

    result = ApplyExecutor().execute(plan, port)

    assert result.skipped_groups == 1
    assert not port.events


def test_residual_note_reference_prevents_trash(tmp_path: Path) -> None:
    plan = make_plan(tmp_path)
    port = FakePort(tmp_path, plan.notes)
    old = plan.groups[0].old_filenames[0]
    port.notes[99] = [f"[sound:{old}] unchanged by snapshot"]
    port.ignored_note_ids.add(99)

    result = ApplyExecutor().execute(plan, port)

    assert old not in port.trashed
    assert plan.groups[0].old_filenames[1] in port.trashed
    assert result.trashed_files == (plan.groups[0].old_filenames[1],)


def test_static_reference_prevents_trash(tmp_path: Path) -> None:
    plan = make_plan(tmp_path)
    port = FakePort(tmp_path, plan.notes)
    old = plan.groups[0].old_filenames[0]
    port.static.add(old)

    ApplyExecutor().execute(plan, port)

    assert old not in port.trashed


def test_apply_reports_all_long_running_stages_to_completion(tmp_path: Path) -> None:
    plan = make_plan(tmp_path)
    port = FakePort(tmp_path, plan.notes)
    events: list[tuple[str, int, int]] = []

    executor = ApplyExecutor(
        progress=lambda label, value, maximum: events.append((label, value, maximum))
    )
    executor.execute(plan, port)

    expected_labels = (
        "Verifying media...",
        "Scanning notes for updates...",
        "Updating notes...",
        "Verifying migrated references...",
        "Registering media deletions for sync...",
        "Trashing duplicate media...",
    )
    for label in expected_labels:
        stage_events = [
            (value, maximum)
            for event_label, value, maximum in events
            if event_label == label
        ]
        assert stage_events, label
        assert stage_events[-1][0] == stage_events[-1][1]
        assert [value for value, _ in stage_events] == sorted(value for value, _ in stage_events)


def test_stale_group_still_advances_verification_progress(tmp_path: Path) -> None:
    plan = make_plan(tmp_path)
    port = FakePort(tmp_path, plan.notes)
    (tmp_path / plan.groups[0].old_filenames[0]).unlink()
    events: list[tuple[str, int, int]] = []

    executor = ApplyExecutor(
        progress=lambda label, value, maximum: events.append((label, value, maximum))
    )
    executor.execute(plan, port)

    verification = [
        (value, maximum)
        for label, value, maximum in events
        if label == "Verifying media..."
    ]
    assert verification[-1] == (1, 1)


def test_media_registration_and_trash_report_batch_progress(tmp_path: Path) -> None:
    plan = make_plan(tmp_path)
    port = FakePort(tmp_path, plan.notes)
    events: list[tuple[str, int, int]] = []
    executor = ApplyExecutor(
        media_batch_size=1,
        progress=lambda label, value, maximum: events.append((label, value, maximum)),
    )

    executor.execute(plan, port)

    registering = [
        value
        for label, value, _ in events
        if label == "Registering media deletions for sync..."
    ]
    trashing = [
        value for label, value, _ in events if label == "Trashing duplicate media..."
    ]
    assert registering == [0, 1, 2]
    assert trashing == [0, 1, 2]
    assert port.events.index("update") < port.events.index("trash")
