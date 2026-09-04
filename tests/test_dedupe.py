import threading
from pathlib import Path

from anki_media_deduplicator.cache import HashCache, NullHashCache
from anki_media_deduplicator.dedupe import find_duplicates
from anki_media_deduplicator.models import CancellationToken
from anki_media_deduplicator.scanner import scan_directory


class CountingOpener:
    def __init__(self) -> None:
        self.names: list[str] = []

    def __call__(self, path: Path, mode: str):
        self.names.append(path.name)
        return path.open(mode)


def groups(tmp_path: Path, opener=None):
    files = scan_directory(tmp_path, set(), CancellationToken()).files
    return find_duplicates(
        files,
        NullHashCache(),
        CancellationToken(),
        opener=opener or open,
        max_workers=2,
    )


def test_unique_size_files_are_never_opened(tmp_path: Path) -> None:
    (tmp_path / "a.mp3").write_bytes(b"a")
    (tmp_path / "b.mp3").write_bytes(b"bb")
    opener = CountingOpener()

    assert groups(tmp_path, opener) == []
    assert opener.names == []


def test_same_extension_and_bytes_form_group(tmp_path: Path) -> None:
    (tmp_path / "one.mp3").write_bytes(b"same")
    (tmp_path / "two.mp3").write_bytes(b"same")

    result = groups(tmp_path)

    assert len(result) == 1
    assert {file.filename for file in result[0].files} == {"one.mp3", "two.mp3"}
    assert result[0].size == 4
    assert result[0].reclaimable_bytes == 4


def test_different_extensions_never_merge(tmp_path: Path) -> None:
    (tmp_path / "one.jpg").write_bytes(b"same")
    (tmp_path / "two.jpeg").write_bytes(b"same")

    assert groups(tmp_path) == []


def test_same_size_different_content_does_not_form_group(tmp_path: Path) -> None:
    (tmp_path / "one.mp3").write_bytes(b"aaaa")
    (tmp_path / "two.mp3").write_bytes(b"bbbb")

    assert groups(tmp_path) == []


def test_case_insensitive_extensions_can_merge(tmp_path: Path) -> None:
    (tmp_path / "one.MP3").write_bytes(b"same")
    (tmp_path / "two.mp3").write_bytes(b"same")

    assert len(groups(tmp_path)) == 1


def test_real_sqlite_cache_is_only_accessed_by_coordinator_thread(tmp_path: Path) -> None:
    payload = b"x" * (300 * 1024)
    (tmp_path / "one.mp3").write_bytes(payload)
    (tmp_path / "two.mp3").write_bytes(payload)
    files = scan_directory(tmp_path, set(), CancellationToken()).files
    cache = HashCache(tmp_path / "cache.sqlite3")

    try:
        result = find_duplicates(files, cache, CancellationToken(), max_workers=2)
    finally:
        cache.close()

    assert len(result) == 1


def test_hash_workers_never_access_cache(tmp_path: Path) -> None:
    payload = b"x" * (300 * 1024)
    (tmp_path / "one.mp3").write_bytes(payload)
    (tmp_path / "two.mp3").write_bytes(payload)
    files = scan_directory(tmp_path, set(), CancellationToken()).files
    owner = threading.get_ident()

    class ThreadBoundCache(NullHashCache):
        def get(self, file):
            assert threading.get_ident() == owner
            return None

        def put(self, file, *, sha256, quick):
            assert threading.get_ident() == owner

    assert len(find_duplicates(files, ThreadBoundCache(), CancellationToken(), max_workers=2)) == 1
