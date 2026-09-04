from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from .cache import NullHashCache
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
    progress: Callable[[str, int, int], None] | None = None,
) -> list[DuplicateGroup]:
    report = progress or (lambda stage, value, maximum: None)
    buckets: dict[tuple[int, str], list[FileInfo]] = defaultdict(list)
    report("finding_candidates", 0, len(files))
    for index, file in enumerate(files, 1):
        buckets[(file.size, file.extension.lower())].append(file)
        report("finding_candidates", index, len(files))
    candidates = [bucket for bucket in buckets.values() if len(bucket) > 1]

    def quick(file: FileInfo) -> tuple[FileInfo, str]:
        cancellation.raise_if_cancelled()
        return file, quick_fingerprint(file.path, file.size, opener=opener)

    full_candidates: list[FileInfo] = []
    with ThreadPoolExecutor(max_workers=max(1, min(4, max_workers))) as pool:
        quick_total = sum(len(bucket) for bucket in candidates if bucket[0].size > SMALL_FILE_LIMIT)
        quick_completed = 0
        report("quick_fingerprinting", 0, quick_total)

        def record_quick_result(
            file: FileInfo,
            fingerprint: str,
            groups: dict[str, list[FileInfo]],
        ) -> None:
            nonlocal quick_completed
            groups[fingerprint].append(file)
            hit = cache.get(file)
            cache.put(
                file,
                sha256=hit.sha256 if hit else None,
                quick=fingerprint,
            )
            quick_completed += 1
            report("quick_fingerprinting", quick_completed, quick_total)

        for bucket in candidates:
            cancellation.raise_if_cancelled()
            if bucket[0].size <= SMALL_FILE_LIMIT:
                full_candidates.extend(bucket)
                continue
            quick_groups: dict[str, list[FileInfo]] = defaultdict(list)
            cached_quick: list[tuple[FileInfo, str]] = []
            uncached_quick: list[FileInfo] = []
            for file in bucket:
                hit = cache.get(file)
                if hit and hit.quick:
                    cached_quick.append((file, hit.quick))
                else:
                    uncached_quick.append(file)
            for file, fingerprint in cached_quick:
                record_quick_result(file, fingerprint, quick_groups)
            for file, fingerprint in pool.map(quick, uncached_quick):
                record_quick_result(file, fingerprint, quick_groups)
            for quick_group in quick_groups.values():
                if len(quick_group) > 1:
                    full_candidates.extend(quick_group)

        def full(file: FileInfo) -> tuple[FileInfo, str]:
            cancellation.raise_if_cancelled()
            return file, full_sha256(file.path, opener=opener)

        hashed: list[tuple[FileInfo, str]] = []
        uncached_full: list[FileInfo] = []
        for file in full_candidates:
            hit = cache.get(file)
            if hit and hit.sha256:
                hashed.append((file, hit.sha256))
            else:
                uncached_full.append(file)
        full_total = len(full_candidates)
        full_completed = 0
        report("hashing_media", 0, full_total)
        cached_count = len(hashed)
        if cached_count:
            full_completed = cached_count
            report("hashing_media", full_completed, full_total)
        for result in pool.map(full, uncached_full):
            hashed.append(result)
            full_completed += 1
            report("hashing_media", full_completed, full_total)

    hash_groups: dict[tuple[str, int, str], list[FileInfo]] = defaultdict(list)
    for file, digest in hashed:
        hit = cache.get(file)
        cache.put(file, sha256=digest, quick=hit.quick if hit else None)
        hash_groups[(file.extension.lower(), file.size, digest)].append(file)

    groups: list[DuplicateGroup] = []
    verification_total = sum(max(0, len(group) - 1) for group in hash_groups.values())
    verification_completed = 0
    report("verifying_duplicates", 0, verification_total)
    for (_, size, digest), hash_group in hash_groups.items():
        if len(hash_group) < 2:
            continue
        representative = hash_group[0]
        verified = [representative]
        for file in hash_group[1:]:
            cancellation.raise_if_cancelled()
            if files_equal(representative.path, file.path, opener=opener):
                verified.append(file)
            verification_completed += 1
            report("verifying_duplicates", verification_completed, verification_total)
        if len(verified) > 1:
            groups.append(DuplicateGroup(verified, size, digest))
    groups.sort(key=lambda group: [file.filename for file in group.files])
    return groups
