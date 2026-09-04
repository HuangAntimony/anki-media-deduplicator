from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from .cache import HashCache
from .compatibility import AnkiCollectionPort, require_supported_apis
from .dedupe import find_duplicates
from .i18n import tr
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
    protected = port.static_references()
    index = scan_directory(
        port.media_dir,
        protected,
        cancellation,
        progress=lambda value, maximum: progress(tr("indexing_media"), value, maximum),
    )
    cache = HashCache(cache_path)
    try:
        groups = find_duplicates(
            index.files,
            cache,
            cancellation,
            max_workers=4,
            progress=lambda stage, value, maximum: progress(tr(stage), value, maximum),
        )
        cache.prune_missing(port.media_dir, {file.filename for file in index.files})
    finally:
        cache.close()
    cancellation.raise_if_cancelled()
    notes = list(
        port.iter_notes(
            lambda value, maximum: progress(tr("scanning_references"), value, maximum)
        )
    )
    cancellation.raise_if_cancelled()
    return build_plan(
        index,
        groups,
        notes,
        port.media_dir,
        progress=lambda value, maximum: progress(tr("building_plan"), value, maximum),
    )
