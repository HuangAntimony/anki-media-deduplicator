from __future__ import annotations

from pathlib import Path

from .hashing import files_equal
from .models import CanonicalChoice, DuplicateGroup, FileInfo, RestorationState

ANDROID_LONG_MAX = 9_223_372_036_854_775_807
ANDROID_SUFFIX_MAX_DIGITS = 19


def _valid_android_prefix(prefix: str) -> bool:
    return len(prefix) >= 3


def _prefix_candidates(stem: str) -> set[str]:
    candidates: set[str] = set()
    max_length = min(ANDROID_SUFFIX_MAX_DIGITS, len(stem))
    for length in range(1, max_length + 1):
        suffix = stem[-length:]
        prefix = stem[:-length]
        if not prefix or not suffix.isdecimal():
            continue
        if int(suffix) <= ANDROID_LONG_MAX and _valid_android_prefix(prefix):
            candidates.add(prefix)
    return candidates


def _fallback(group: DuplicateGroup, references: dict[str, int]) -> FileInfo:
    return min(
        group.files,
        key=lambda file: (-references.get(file.filename, 0), len(file.filename), file.filename),
    )


def _external_info(path: Path) -> FileInfo:
    stat = path.stat()
    return FileInfo(path.name, path, stat.st_size, path.suffix, stat.st_mtime_ns)


def select_canonical(
    group: DuplicateGroup, reference_counts: dict[str, int], media_dir: Path
) -> CanonicalChoice:
    fallback = _fallback(group, reference_counts)
    extension = group.files[0].extension
    group_names = {file.filename: file for file in group.files}

    # A clean member is one whose stem is a valid original prefix for every other member.
    for clean in sorted(group.files, key=lambda file: (len(file.filename), file.filename)):
        if all(
            other is clean or clean.path.stem in _prefix_candidates(other.path.stem)
            for other in group.files
        ):
            return CanonicalChoice(clean.filename, RestorationState.EXISTING_CLEAN, clean)

    candidate_sets = [_prefix_candidates(file.path.stem) for file in group.files]
    if not candidate_sets or any(not candidates for candidates in candidate_sets):
        return CanonicalChoice(fallback.filename, RestorationState.NOT_ANKIDROID_PATTERN, fallback)
    common = set.intersection(*candidate_sets)
    if len(common) != 1:
        state = RestorationState.AMBIGUOUS if common else RestorationState.NOT_ANKIDROID_PATTERN
        return CanonicalChoice(fallback.filename, state, fallback)

    inferred = next(iter(common))
    if inferred.endswith("-name") and len(inferred.removesuffix("-name")) < 3:
        inferred = inferred.removesuffix("-name")
    target_name = f"{inferred}{extension}"
    target_path = media_dir / target_name
    if not target_path.exists():
        return CanonicalChoice(target_name, RestorationState.UNIQUE_INFERENCE, None)

    target = group_names.get(target_name) or _external_info(target_path)
    if target.size == group.size and files_equal(target.path, group.files[0].path):
        return CanonicalChoice(target_name, RestorationState.EXISTING_CLEAN, target)
    return CanonicalChoice(fallback.filename, RestorationState.TARGET_CONFLICT, fallback)
