from __future__ import annotations

import shutil
import tempfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .hashing import files_equal
from .models import NoteSnapshot


class AnkiCollectionPort:
    """Small compatibility boundary around supported Collection/MediaManager APIs."""

    def __init__(self, collection: Any) -> None:
        self.collection = collection
        self.media_dir = Path(collection.media.dir())
        self.last_changes: Any = None

    def iter_notes(self) -> Iterable[NoteSnapshot]:
        for note_id in self.collection.find_notes(""):
            note = self.collection.get_note(note_id)
            yield NoteSnapshot(int(note.id), tuple(note.fields))

    def update_notes(self, notes: list[NoteSnapshot]) -> None:
        anki_notes = []
        for snapshot in notes:
            note = self.collection.get_note(snapshot.note_id)
            note.fields = list(snapshot.fields)
            anki_notes.append(note)
        self.last_changes = self.collection.update_notes(anki_notes, skip_undo_entry=True)

    def static_references(self) -> set[str]:
        references: set[str] = set()
        for notetype in self.collection.models.all_names_and_ids():
            references.update(self.collection.media.extract_static_media_files(notetype.id))
        return references

    def ensure_media_file(self, source: Path, target_name: str) -> bool:
        target = self.media_dir / target_name
        if target.exists():
            return target.is_file() and files_equal(source, target)
        with tempfile.TemporaryDirectory(prefix="anki-media-deduplicator-") as directory:
            staged = Path(directory) / target_name
            shutil.copy2(source, staged)
            actual_name = self.collection.media.add_file(str(staged))
        return actual_name == target_name and target.exists() and files_equal(source, target)

    def trash_files(self, names: list[str]) -> None:
        self.collection.media.trash_files(names)


def require_supported_apis(collection: Any) -> None:
    required = (
        (collection, "update_notes"),
        (collection, "find_notes"),
        (collection, "get_note"),
        (collection.media, "add_file"),
        (collection.media, "trash_files"),
        (collection.media, "extract_static_media_files"),
    )
    missing = [name for owner, name in required if not callable(getattr(owner, name, None))]
    if missing:
        raise RuntimeError(f"Unsupported Anki version; missing APIs: {', '.join(missing)}")

