import sys
import types

from anki_media_deduplicator.i18n import current_locale, tr


def test_simplified_chinese_translation_and_formatting() -> None:
    assert tr("window_title", lang="zh_CN") == "Anki 媒体去重"
    assert tr("media_entries_scanned", lang="zh_CN", count=1234) == "已扫描媒体条目：1,234"


def test_unknown_locale_falls_back_to_english() -> None:
    assert tr("scan_media", lang="fr_FR") == "Scan Media"


def test_missing_key_is_safe() -> None:
    assert tr("missing_message", lang="zh_CN") == "missing_message"


def test_current_locale_reads_anki_language(monkeypatch) -> None:
    fake_anki = types.ModuleType("anki")
    fake_lang = types.ModuleType("anki.lang")
    fake_lang.current_lang = "zh_CN"
    fake_anki.lang = fake_lang
    monkeypatch.setitem(sys.modules, "anki", fake_anki)
    monkeypatch.setitem(sys.modules, "anki.lang", fake_lang)

    assert current_locale() == "zh_CN"
