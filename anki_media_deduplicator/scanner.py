from __future__ import annotations

import logging
import os
from collections.abc import Callable
from pathlib import Path

from .models import CancellationToken, FileInfo, IndexResult

logger = logging.getLogger(__name__)


def scan_directory(
    media_dir: Path,
    protected: set[str],
    cancellation: CancellationToken,
    *,
    progress: Callable[[int, int], None] | None = None,
) -> IndexResult:
    report = progress or (lambda value, maximum: None)
    with os.scandir(media_dir) as directory_entries:
        entries = list(directory_entries)
    expected_entries = len(entries)
    report(0, expected_entries)
    files: list[FileInfo] = []
    total_entries = total_size = protected_skipped = zero_byte_skipped = invalid_skipped = 0
    media_file_count = 0
    for entry in entries:
        cancellation.raise_if_cancelled()
        total_entries += 1
        try:
            if entry.is_symlink() or not entry.is_file(follow_symlinks=False):
                invalid_skipped += 1
                continue
            stat = entry.stat(follow_symlinks=False)
            media_file_count += 1
            total_size += stat.st_size
            name = entry.name
            if name.startswith("_") or name.startswith("latex-") or name in protected:
                protected_skipped += 1
                continue
            if stat.st_size == 0:
                zero_byte_skipped += 1
                continue
            path = Path(entry.path)
            info = FileInfo(name, path, stat.st_size, path.suffix, stat.st_mtime_ns)
            files.append(info)
        except OSError as error:
            logger.warning("media entry skipped: %s: %s", entry.name, error)
            invalid_skipped += 1
        finally:
            report(total_entries, expected_entries)
    files.sort(key=lambda item: item.filename)
    return IndexResult(
        files,
        total_entries,
        total_size,
        protected_skipped,
        zero_byte_skipped,
        invalid_skipped,
        media_file_count,
    )
