from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

from .cache import CacheEntry, NullHashCache
from .hashing import Opener, files_equal, full_sha256, quick_fingerprint
from .models import CancellationToken, DuplicateGroup, FileInfo

SMALL_FILE_LIMIT = 256 * 1024


def find_duplicates(
    files: list[FileInfo],
    cache: NullHashCache,
    cancellation: CancellationToken,
    *,
    opener: Opener = open,
    max_workers: int = 4,
) -> list[DuplicateGroup]:
    buckets: dict[tuple[int, str], list[FileInfo]] = defaultdict(list)
    for file in files:
        buckets[(file.size, file.extension.lower())].append(file)
    candidates = [bucket for bucket in buckets.values() if len(bucket) > 1]

    def quick(file: FileInfo) -> tuple[FileInfo, str]:
        cancellation.raise_if_cancelled()
        hit = cache.get(file)
        value = hit.quick if hit and hit.quick else quick_fingerprint(file.path, file.size, opener=opener)
        return file, value

    full_candidates: list[FileInfo] = []
    with ThreadPoolExecutor(max_workers=max(1, min(4, max_workers))) as pool:
        for bucket in candidates:
            cancellation.raise_if_cancelled()
            if bucket[0].size <= SMALL_FILE_LIMIT:
                full_candidates.extend(bucket)
                continue
            quick_groups: dict[str, list[FileInfo]] = defaultdict(list)
            for file, fingerprint in pool.map(quick, bucket):
                quick_groups[fingerprint].append(file)
                hit = cache.get(file)
                cache.put(
                    file,
                    sha256=hit.sha256 if hit else None,
                    quick=fingerprint,
                )
            for quick_group in quick_groups.values():
                if len(quick_group) > 1:
                    full_candidates.extend(quick_group)

        def full(file: FileInfo) -> tuple[FileInfo, str]:
            cancellation.raise_if_cancelled()
            hit = cache.get(file)
            value = hit.sha256 if hit and hit.sha256 else full_sha256(file.path, opener=opener)
            return file, value

        hashed = list(pool.map(full, full_candidates))

    hash_groups: dict[tuple[str, int, str], list[FileInfo]] = defaultdict(list)
    for file, digest in hashed:
        hit = cache.get(file)
        cache.put(file, sha256=digest, quick=hit.quick if hit else None)
        hash_groups[(file.extension.lower(), file.size, digest)].append(file)

    groups: list[DuplicateGroup] = []
    for (_, size, digest), hash_group in hash_groups.items():
        if len(hash_group) < 2:
            continue
        representative = hash_group[0]
        verified = [representative]
        for file in hash_group[1:]:
            cancellation.raise_if_cancelled()
            if files_equal(representative.path, file.path, opener=opener):
                verified.append(file)
        if len(verified) > 1:
            groups.append(DuplicateGroup(verified, size, digest))
    groups.sort(key=lambda group: [file.filename for file in group.files])
    return groups
