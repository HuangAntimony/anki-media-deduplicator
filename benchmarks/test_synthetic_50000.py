from pathlib import Path

from anki_media_deduplicator.cache import NullHashCache
from anki_media_deduplicator.dedupe import find_duplicates
from anki_media_deduplicator.models import CancellationToken, FileInfo


def test_50000_unique_buckets_do_not_open_files() -> None:
    files = [FileInfo(f"{i}.bin", Path(f"/{i}.bin"), i + 1, ".bin", 1) for i in range(50_000)]
    opened = 0

    def forbidden_opener(path: Path, mode: str):
        nonlocal opened
        opened += 1
        raise AssertionError(f"unique bucket opened: {path}")

    result = find_duplicates(
        files, NullHashCache(), CancellationToken(), opener=forbidden_opener, max_workers=4
    )

    assert result == []
    assert opened == 0
