from __future__ import annotations

import os
from pathlib import Path

from .models import CancellationToken, FileInfo, IndexResult


def scan_directory(
    media_dir: Path, protected: set[str], cancellation: CancellationToken
) -> IndexResult:
    files: list[FileInfo] = []
    total_entries = total_size = protected_skipped = zero_byte_skipped = invalid_skipped = 0
    with os.scandir(media_dir) as entries:
        for entry in entries:
            cancellation.raise_if_cancelled()
            total_entries += 1
            try:
                if entry.is_symlink() or not entry.is_file(follow_symlinks=False):
                    invalid_skipped += 1
                    continue
                name = entry.name
                if name.startswith("_") or name.startswith("latex-") or name in protected:
                    protected_skipped += 1
                    continue
                stat = entry.stat(follow_symlinks=False)
                if stat.st_size == 0:
                    zero_byte_skipped += 1
                    continue
                path = Path(entry.path)
                info = FileInfo(name, path, stat.st_size, path.suffix, stat.st_mtime_ns)
                files.append(info)
                total_size += stat.st_size
            except OSError:
                invalid_skipped += 1
    files.sort(key=lambda item: item.filename)
    return IndexResult(
        files,
        total_entries,
        total_size,
        protected_skipped,
        zero_byte_skipped,
        invalid_skipped,
    )

