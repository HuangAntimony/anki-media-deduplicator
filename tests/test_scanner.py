from pathlib import Path

import pytest

from anki_media_deduplicator.models import CancelledError, CancellationToken
from anki_media_deduplicator.scanner import scan_directory


def test_scan_filters_nonfiles_zero_symlinks_and_protected(tmp_path: Path) -> None:
    (tmp_path / "ok.mp3").write_bytes(b"abc")
    (tmp_path / "zero.mp3").touch()
    (tmp_path / "folder").mkdir()
    (tmp_path / "_static.css").write_bytes(b"x")
    (tmp_path / "latex-a.png").write_bytes(b"x")
    (tmp_path / "template.jpg").write_bytes(b"x")
    (tmp_path / "link.mp3").symlink_to(tmp_path / "ok.mp3")

    result = scan_directory(tmp_path, {"template.jpg"}, CancellationToken())

    assert [file.filename for file in result.files] == ["ok.mp3"]
    assert result.total_entries == 7
    assert result.protected_skipped == 3
    assert result.zero_byte_skipped == 1
    assert result.invalid_skipped == 2
    assert result.total_size == 3


def test_scan_preserves_unicode_spaces_extension_and_mtime(tmp_path: Path) -> None:
    path = tmp_path / "你好 file.MP3"
    path.write_bytes(b"1234")

    info = scan_directory(tmp_path, set(), CancellationToken()).files[0]

    assert info.filename == "你好 file.MP3"
    assert info.path == path
    assert info.size == 4
    assert info.extension == ".MP3"
    assert info.mtime_ns == path.stat().st_mtime_ns


def test_scan_honors_cancellation(tmp_path: Path) -> None:
    (tmp_path / "a.mp3").write_bytes(b"a")
    token = CancellationToken()
    token.cancel()

    with pytest.raises(CancelledError):
        scan_directory(tmp_path, set(), token)

