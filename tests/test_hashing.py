from pathlib import Path

from anki_media_deduplicator.hashing import files_equal, full_sha256, quick_fingerprint


class CountingOpener:
    def __init__(self) -> None:
        self.paths: list[Path] = []

    def __call__(self, path: Path, mode: str):
        self.paths.append(path)
        return path.open(mode)


def test_quick_fingerprint_detects_equal_edges_with_different_middle(tmp_path: Path) -> None:
    edge = b"e" * (64 * 1024)
    first = tmp_path / "first.bin"
    second = tmp_path / "second.bin"
    first.write_bytes(edge + b"a" * 100 + edge)
    second.write_bytes(edge + b"b" * 100 + edge)

    assert quick_fingerprint(first, first.stat().st_size) == quick_fingerprint(
        second, second.stat().st_size
    )
    assert full_sha256(first) != full_sha256(second)
    assert not files_equal(first, second)


def test_chunked_comparison_reads_equal_files(tmp_path: Path) -> None:
    payload = b"01234567" * 300_000
    first = tmp_path / "a"
    second = tmp_path / "b"
    first.write_bytes(payload)
    second.write_bytes(payload)
    opener = CountingOpener()

    assert files_equal(first, second, opener=opener, chunk_size=1024 * 1024)
    assert opener.paths == [first, second]

