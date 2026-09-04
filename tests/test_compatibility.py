from pathlib import Path

from anki_media_deduplicator.compatibility import AnkiCollectionPort
from anki_media_deduplicator.models import NoteSnapshot


class FakeNote:
    def __init__(self, note_id: int, fields: list[str]) -> None:
        self.id = note_id
        self.fields = fields


class FakeModels:
    def all_names_and_ids(self):
        return [type("Notetype", (), {"id": 10})(), type("Notetype", (), {"id": 11})()]


class FakeMedia:
    def __init__(self, directory: Path) -> None:
        self._directory = directory
        self.trashed: list[str] = []

    def dir(self) -> str:
        return str(self._directory)

    def extract_static_media_files(self, notetype_id: int):
        return [f"static-{notetype_id}.css"]

    def add_file(self, path: str) -> str:
        source = Path(path)
        (self._directory / source.name).write_bytes(source.read_bytes())
        return source.name

    def trash_files(self, names: list[str]) -> None:
        self.trashed.extend(names)


class FakeCollection:
    def __init__(self, directory: Path) -> None:
        self.media = FakeMedia(directory)
        self.models = FakeModels()
        self.notes = {1: FakeNote(1, ["old"]), 2: FakeNote(2, ["other"])}
        self.update_calls: list[tuple[list[int], bool]] = []

    def find_notes(self, query: str):
        assert query == ""
        return list(self.notes)

    def get_note(self, note_id: int):
        return self.notes[note_id]

    def update_notes(self, notes, skip_undo_entry: bool = False):
        self.update_calls.append(([note.id for note in notes], skip_undo_entry))
        return type("Changes", (), {})()


def test_anki_port_uses_public_note_and_media_apis(tmp_path: Path) -> None:
    collection = FakeCollection(tmp_path)
    port = AnkiCollectionPort(collection)

    assert list(port.iter_notes()) == [NoteSnapshot(1, ("old",)), NoteSnapshot(2, ("other",))]
    port.update_notes([NoteSnapshot(1, ("new",))])
    assert collection.notes[1].fields == ["new"]
    assert collection.update_calls == [([1], True)]
    assert port.static_references() == {"static-10.css", "static-11.css"}
    port.trash_files(["old.mp3"])
    assert collection.media.trashed == ["old.mp3"]


def test_anki_port_reports_note_loading_progress(tmp_path: Path) -> None:
    collection = FakeCollection(tmp_path)
    events: list[tuple[int, int]] = []

    notes = list(
        AnkiCollectionPort(collection).iter_notes(
            lambda value, maximum: events.append((value, maximum))
        )
    )

    assert len(notes) == 2
    assert events == [(0, 2), (1, 2), (2, 2)]


def test_ensure_media_file_requires_backend_to_return_exact_target(tmp_path: Path) -> None:
    collection = FakeCollection(tmp_path)
    source = tmp_path / "random.mp3"
    source.write_bytes(b"data")
    port = AnkiCollectionPort(collection)

    assert port.ensure_media_file(source, "clean.mp3")
    assert (tmp_path / "clean.mp3").read_bytes() == b"data"

    (tmp_path / "clean.mp3").unlink()
    collection.media.add_file = lambda path: "clean-1.mp3"
    assert not port.ensure_media_file(source, "clean.mp3")
