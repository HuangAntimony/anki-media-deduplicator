import hashlib
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


def test_legacy_hoshi_audio_is_migrated_to_content_addressed_filename(
    tmp_path: Path,
) -> None:
    duplicate_group = group(
        tmp_path,
        "hoshi_audio_-1243218021_3234766960201471919.mp3",
        "hoshi_audio_-1243218021_3730691864949824170.mp3",
    )
    sha1 = hashlib.sha1(b"same").hexdigest()

    choice = select_canonical(duplicate_group, {}, tmp_path)

    assert choice.filename == f"hoshi_audio_{sha1}.mp3"
    assert choice.state is RestorationState.UNIQUE_INFERENCE


def test_ankidroid_separator_preserves_original_trailing_digits(tmp_path: Path) -> None:
    duplicate_group = group(
        tmp_path,
        "lesson1_1234567890123456789.mp3",
        "lesson1_987654321098765432.mp3",
    )

    choice = select_canonical(duplicate_group, {}, tmp_path)

    assert choice.filename == "lesson1.mp3"
    assert choice.state is RestorationState.UNIQUE_INFERENCE


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


def test_untransformed_short_prefix_is_not_treated_as_ankidroid_pattern(tmp_path: Path) -> None:
    duplicate_group = group(tmp_path, "a812736128736128736.mp3", "a192837465192837465.mp3")

    choice = select_canonical(duplicate_group, {}, tmp_path)

    assert choice.state is RestorationState.NOT_ANKIDROID_PATTERN


def test_hoshi_content_addressed_filename_is_preferred(tmp_path: Path) -> None:
    payload = b"same hoshi audio"
    sha1 = hashlib.sha1(payload).hexdigest()
    duplicate_group = group(
        tmp_path,
        f"hoshi_audio_{sha1}_1234567890123456789.mp3",
        f"hoshi_audio_{sha1}_9876543210987654321.mp3",
    )
    # The helper above writes its default payload, so replace it with the bytes
    # whose SHA-1 is encoded in the filenames.
    for file in duplicate_group.files:
        file.path.write_bytes(payload)
    duplicate_group.files = [
        make_file(tmp_path, file.filename, payload) for file in duplicate_group.files
    ]
    duplicate_group.size = len(payload)

    choice = select_canonical(duplicate_group, {}, tmp_path)

    assert choice.filename == f"hoshi_audio_{sha1}.mp3"
    assert choice.state is RestorationState.UNIQUE_INFERENCE
    assert choice.existing is None


def test_existing_hoshi_content_addressed_filename_wins(tmp_path: Path) -> None:
    payload = b"same dictionary media"
    sha1 = hashlib.sha1(payload).hexdigest()
    target = f"hoshi_dict_{sha1}.svg"
    duplicate_group = group(
        tmp_path,
        target,
        f"hoshi_dict_{sha1}_1234567890123456789.svg",
    )
    for file in duplicate_group.files:
        file.path.write_bytes(payload)
    duplicate_group.files = [
        make_file(tmp_path, file.filename, payload) for file in duplicate_group.files
    ]
    duplicate_group.size = len(payload)

    choice = select_canonical(duplicate_group, {}, tmp_path)

    assert choice.filename == target
    assert choice.state is RestorationState.EXISTING_CLEAN


def test_hoshi_filename_without_separator_before_random_suffix_is_supported(
    tmp_path: Path,
) -> None:
    payload = b"same audio without separator"
    sha1 = hashlib.sha1(payload).hexdigest()
    duplicate_group = group(
        tmp_path,
        f"hoshi_audio_{sha1}1234567890123456789.mp3",
        f"hoshi_audio_{sha1}9876543210987654321.mp3",
    )
    for file in duplicate_group.files:
        file.path.write_bytes(payload)
    duplicate_group.files = [
        make_file(tmp_path, file.filename, payload) for file in duplicate_group.files
    ]
    duplicate_group.size = len(payload)

    choice = select_canonical(duplicate_group, {}, tmp_path)

    assert choice.filename == f"hoshi_audio_{sha1}.mp3"
    assert choice.state is RestorationState.UNIQUE_INFERENCE


def test_hoshi_content_addressed_target_conflict_falls_back(tmp_path: Path) -> None:
    payload = b"same cover"
    sha1 = hashlib.sha1(payload).hexdigest()
    duplicate_group = group(
        tmp_path,
        f"hoshi_cover_{sha1}_1234567890123456789.jpg",
        f"hoshi_cover_{sha1}_9876543210987654321.jpg",
    )
    for file in duplicate_group.files:
        file.path.write_bytes(payload)
    duplicate_group.files = [
        make_file(tmp_path, file.filename, payload) for file in duplicate_group.files
    ]
    duplicate_group.size = len(payload)
    (tmp_path / f"hoshi_cover_{sha1}.jpg").write_bytes(b"different")

    choice = select_canonical(duplicate_group, {}, tmp_path)

    assert choice.state is RestorationState.TARGET_CONFLICT
    assert choice.filename in {file.filename for file in duplicate_group.files}


def test_legacy_hoshi_cover_is_migrated_to_content_addressed_filename(
    tmp_path: Path,
) -> None:
    payload = b"legacy cover bytes"
    sha1 = hashlib.sha1(payload).hexdigest()
    duplicate_group = group(
        tmp_path,
        "hoshi_cover_cover_1234567890123456789.jpg",
        "hoshi_cover_cover_987654321098765432.jpg",
    )
    duplicate_group.files = [
        make_file(tmp_path, file.filename, payload) for file in duplicate_group.files
    ]
    duplicate_group.size = len(payload)

    choice = select_canonical(duplicate_group, {}, tmp_path)

    assert choice.filename == f"hoshi_cover_{sha1}.jpg"
    assert choice.state is RestorationState.UNIQUE_INFERENCE
    assert choice.existing is None


def test_legacy_hoshi_target_conflict_uses_referenced_existing_fallback(
    tmp_path: Path,
) -> None:
    payload = b"legacy conflicting cover"
    sha1 = hashlib.sha1(payload).hexdigest()
    names = (
        "hoshi_cover_cover_1234567890123456789.jpg",
        "hoshi_cover_cover_9123456789012345678.jpg",
    )
    duplicate_group = group(tmp_path, *names)
    duplicate_group.files = [
        make_file(tmp_path, file.filename, payload) for file in duplicate_group.files
    ]
    duplicate_group.size = len(payload)
    (tmp_path / f"hoshi_cover_{sha1}.jpg").write_bytes(b"different")

    choice = select_canonical(duplicate_group, {names[1]: 7}, tmp_path)

    assert choice.filename == names[1]
    assert choice.state is RestorationState.TARGET_CONFLICT
    assert choice.existing is duplicate_group.files[1]


def test_invalid_hoshi_hash_is_not_used_for_restoration(tmp_path: Path) -> None:
    payload = b"not the claimed hash"
    duplicate_group = group(
        tmp_path,
        "hoshi_audio_0000000000000000000000000000000000000000_123.mp3",
        "hoshi_audio_0000000000000000000000000000000000000000_456.mp3",
    )
    for file in duplicate_group.files:
        file.path.write_bytes(payload)
    duplicate_group.files = [
        make_file(tmp_path, file.filename, payload) for file in duplicate_group.files
    ]
    duplicate_group.size = len(payload)

    choice = select_canonical(duplicate_group, {}, tmp_path)

    assert choice.state is RestorationState.NOT_ANKIDROID_PATTERN
