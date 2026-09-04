from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from .cache import HashCache
from .compatibility import AnkiCollectionPort, require_supported_apis
from .dedupe import find_duplicates
from .models import CancellationToken, DeduplicationPlan
from .planner import build_plan
from .scanner import scan_directory

ProgressCallback = Callable[[str, int, int], None]


def scan_collection(
    collection: Any,
    cache_path: Path,
    cancellation: CancellationToken,
    progress: ProgressCallback,
) -> DeduplicationPlan:
    require_supported_apis(collection)
    port = AnkiCollectionPort(collection)
    progress("Indexing media...", 0, 0)
    protected = port.static_references()
    index = scan_directory(port.media_dir, protected, cancellation)
    progress("Hashing candidate media...", 0, len(index.files))
    cache = HashCache(cache_path)
    try:
        groups = find_duplicates(index.files, cache, cancellation, max_workers=4)
        cache.prune_missing(port.media_dir, {file.filename for file in index.files})
    finally:
        cache.close()
    cancellation.raise_if_cancelled()
    progress("Scanning note references...", 0, 0)
    notes = list(port.iter_notes())
    cancellation.raise_if_cancelled()
    progress("Building dry-run plan...", 0, len(groups))
    return build_plan(index, groups, notes, port.media_dir)

