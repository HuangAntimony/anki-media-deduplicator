import pytest

from anki_media_deduplicator.references import extract_references, rewrite_field


@pytest.mark.parametrize(
    ("field", "expected"),
    [
        ("[sound:foo.mp3]", ["foo.mp3"]),
        ('<img src="foo.jpg">', ["foo.jpg"]),
        ("<img src='foo.jpg'>", ["foo.jpg"]),
        ("<img src=foo.jpg>", ["foo.jpg"]),
        ('<audio controls src="foo.mp3">', ["foo.mp3"]),
        ('<source src="foo.mp3">', ["foo.mp3"]),
        ('<object data="foo.bin">', ["foo.bin"]),
        ('<img src="a&amp;b.jpg">', ["a&b.jpg"]),
        ('<img src="你好 file.jpg">', ["你好 file.jpg"]),
    ],
)
def test_extracts_supported_anki_media_references(field: str, expected: list[str]) -> None:
    assert extract_references(field) == expected


def test_rewrite_changes_only_reference_capture_and_counts_occurrences() -> None:
    field = "foo.mp3 [sound:foo.mp3] plain foo.mp3 <audio src='foo.mp3'>"

    result = rewrite_field(field, {"foo.mp3": "kept.mp3"})

    assert result.text == "foo.mp3 [sound:kept.mp3] plain foo.mp3 <audio src='kept.mp3'>"
    assert result.replacements == 2


def test_rewrite_preserves_entity_encoding_style() -> None:
    result = rewrite_field('<img src="old&amp;name.jpg">', {"old&name.jpg": "new&name.jpg"})

    assert result.text == '<img src="new&amp;name.jpg">'
    assert result.replacements == 1


def test_same_note_can_count_the_same_reference_more_than_once() -> None:
    result = rewrite_field("[sound:a.mp3][sound:a.mp3]", {"a.mp3": "b.mp3"})

    assert result.replacements == 2


def test_remote_and_unrelated_references_are_unchanged() -> None:
    field = '<img src="https://example.test/foo.jpg"><img src="bar.jpg">'

    result = rewrite_field(field, {"foo.jpg": "x.jpg"})

    assert result.text == field
    assert result.replacements == 0
