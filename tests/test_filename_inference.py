from pathlib import Path

from anki_media_deduplicator.filename_inference import select_canonical
from anki_media_deduplicator.models import DuplicateGroup, FileInfo, RestorationState


def make_file(directory: Path, name: str, data: bytes = b"same") -> FileInfo:
    path = directory / name
    path.write_bytes(data)
    stat = path.stat()
    return FileInfo(name, path, stat.st_size, path.suffix, stat.st_mtime_ns)


def group(directory: Path, *names: str) -> DuplicateGroup:
    files = [make_file(directory, name) for name in names]
    return DuplicateGroup(files, len(b"same"), "hash")


def test_existing_clean_filename_wins(tmp_path: Path) -> None:
    duplicate_group = group(tmp_path, "cat.mp3", "cat812736128736128736.mp3")

    choice = select_canonical(duplicate_group, {"cat812736128736128736.mp3": 10}, tmp_path)

    assert choice.filename == "cat.mp3"
    assert choice.state is RestorationState.EXISTING_CLEAN


def test_unique_common_prefix_is_restored(tmp_path: Path) -> None:
    duplicate_group = group(
        tmp_path,
        "cat812736128736128736.mp3",
        "cat192837465192837465.mp3",
        "cat712938475612938475.mp3",
    )

    choice = select_canonical(duplicate_group, {}, tmp_path)

    assert choice.filename == "cat.mp3"
    assert choice.state is RestorationState.UNIQUE_INFERENCE
    assert choice.existing is None


def test_numeric_original_is_not_blindly_stripped(tmp_path: Path) -> None:
    duplicate_group = group(
        tmp_path,
        "lesson1123456789012345678.mp3",
        "lesson1129876543210987654.mp3",
    )

    choice = select_canonical(duplicate_group, {}, tmp_path)

    assert choice.state is RestorationState.AMBIGUOUS
    assert choice.filename in {file.filename for file in duplicate_group.files}


def test_non_android_names_use_deterministic_existing_fallback(tmp_path: Path) -> None:
    duplicate_group = group(tmp_path, "longer.mp3", "a.mp3", "b.mp3")

    choice = select_canonical(duplicate_group, {"longer.mp3": 2, "b.mp3": 2}, tmp_path)

    assert choice.filename == "b.mp3"
    assert choice.state is RestorationState.NOT_ANKIDROID_PATTERN


def test_short_name_transformation_is_reversed_exactly(tmp_path: Path) -> None:
    duplicate_group = group(
        tmp_path,
        "a-name812736128736128736.mp3",
        "a-name192837465192837465.mp3",
    )

    choice = select_canonical(duplicate_group, {}, tmp_path)

    assert choice.filename == "a.mp3"
    assert choice.state is RestorationState.UNIQUE_INFERENCE


def test_different_existing_target_causes_conflict(tmp_path: Path) -> None:
    duplicate_group = group(
        tmp_path,
        "cat812736128736128736.mp3",
        "cat192837465192837465.mp3",
    )
    make_file(tmp_path, "cat.mp3", b"different")

    choice = select_canonical(duplicate_group, {}, tmp_path)

    assert choice.state is RestorationState.TARGET_CONFLICT
    assert choice.filename in {file.filename for file in duplicate_group.files}


def test_matching_existing_target_is_used_even_if_not_indexed_in_group(tmp_path: Path) -> None:
    duplicate_group = group(
        tmp_path,
        "cat812736128736128736.mp3",
        "cat192837465192837465.mp3",
    )
    make_file(tmp_path, "cat.mp3")

    choice = select_canonical(duplicate_group, {}, tmp_path)

    assert choice.filename == "cat.mp3"
    assert choice.state is RestorationState.EXISTING_CLEAN

