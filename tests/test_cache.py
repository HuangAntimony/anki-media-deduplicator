from pathlib import Path

from anki_media_deduplicator.cache import HashCache
from anki_media_deduplicator.models import FileInfo


def info(path: Path, *, size: int = 3, mtime: int = 4) -> FileInfo:
    return FileInfo(path.name, path, size, path.suffix, mtime)


def test_cache_only_reuses_exact_filename_size_and_mtime(tmp_path: Path) -> None:
    cache = HashCache(tmp_path / "cache.sqlite3")
    file = info(tmp_path / "a.mp3")
    cache.put(file, sha256="full", quick="quick")

    assert cache.get(file).sha256 == "full"
    assert cache.get(info(file.path, size=5)) is None
    assert cache.get(info(file.path, mtime=6)) is None
    cache.close()


def test_corrupt_cache_falls_back_without_affecting_correctness(tmp_path: Path) -> None:
    path = tmp_path / "cache.sqlite3"
    path.write_bytes(b"not sqlite")

    cache = HashCache(path)

    assert not cache.enabled
    assert cache.get(info(tmp_path / "a.mp3")) is None
    cache.put(info(tmp_path / "a.mp3"), sha256="x", quick=None)
    cache.close()


def test_cache_prunes_missing_files_lazily(tmp_path: Path) -> None:
    cache = HashCache(tmp_path / "cache.sqlite3")
    file = info(tmp_path / "gone.mp3")
    cache.put(file, sha256="x", quick=None)
    cache.prune_missing(tmp_path, {"present.mp3"})

    assert cache.get(file) is None
    cache.close()

