"""Small, dependency-free translation layer for the add-on UI.

Anki's own translation catalogues do not contain add-on strings. Keeping our
messages here means translators can work on the add-on without changing Anki's
installation or relying on deprecated gettext helpers.
"""

from __future__ import annotations

from typing import Any

_MESSAGES: dict[str, dict[str, str]] = {
    "en": {
        "window_title": "Anki Media Deduplicator",
        "menu_item": "Anki Media Deduplicator...",
        "initial_summary": "Click Scan Media to perform a read-only dry run.",
        "scan_media": "Scan Media",
        "apply_deduplication": "Apply Deduplication",
        "close": "Close",
        "keep": "Keep",
        "duplicates": "Duplicates",
        "size_each": "Size Each",
        "copies": "Copies",
        "space_saved": "Space Saved",
        "references": "References",
        "preparing": "Preparing...",
        "indexing_media": "Indexing media...",
        "hashing_media": "Hashing candidate media...",
        "scanning_references": "Scanning note references...",
        "building_plan": "Building dry-run plan...",
        "verifying_media": "Verifying media...",
        "updating_notes": "Updating notes...",
        "trashing_media": "Trashing duplicate media...",
        "scan_cancelled": "Scan cancelled. No changes were made.",
        "media_entries_scanned": "Media entries scanned: {count:,}",
        "total_media_size": "Total media size: {size}",
        "duplicate_groups": "Duplicate groups: {count:,}",
        "duplicate_files": "Duplicate files: {count:,}",
        "files_to_trash": "Files to trash: {count:,}",
        "affected_notes": "Affected notes: {count:,}",
        "references_to_rewrite": "References to rewrite: {count:,}",
        "protected_files_skipped": "Protected files skipped: {count:,}",
        "reclaimable_space": "Reclaimable space: {size}",
        "apply_confirmation": (
            "This will modify {notes:,} notes, trash {files:,} duplicate media files, "
            "and may reclaim {space}.\n\nContinue?"
        ),
        "apply_result": (
            "Updated notes: {updated:,}\n"
            "Rewritten references: {rewritten:,}\n"
            "Trashed media files: {trashed:,}\n"
            "Skipped stale/conflicting groups: {skipped:,}"
        ),
    },
    "zh_CN": {
        "window_title": "Anki 媒体去重",
        "menu_item": "Anki 媒体去重...",
        "initial_summary": "点击“扫描媒体”执行只读的 Dry Run。",
        "scan_media": "扫描媒体",
        "apply_deduplication": "应用去重",
        "close": "关闭",
        "keep": "保留",
        "duplicates": "重复文件",
        "size_each": "单个大小",
        "copies": "副本数",
        "space_saved": "可释放空间",
        "references": "引用数",
        "preparing": "正在准备...",
        "indexing_media": "正在索引媒体...",
        "hashing_media": "正在计算候选媒体哈希...",
        "scanning_references": "正在扫描笔记引用...",
        "building_plan": "正在生成 Dry Run 计划...",
        "verifying_media": "正在验证媒体...",
        "updating_notes": "正在更新笔记...",
        "trashing_media": "正在将重复媒体移入回收站...",
        "scan_cancelled": "扫描已取消，未修改任何数据。",
        "media_entries_scanned": "已扫描媒体条目：{count:,}",
        "total_media_size": "媒体总大小：{size}",
        "duplicate_groups": "重复组：{count:,}",
        "duplicate_files": "重复文件：{count:,}",
        "files_to_trash": "将移入回收站：{count:,}",
        "affected_notes": "受影响的笔记：{count:,}",
        "references_to_rewrite": "将改写的引用：{count:,}",
        "protected_files_skipped": "跳过的受保护文件：{count:,}",
        "reclaimable_space": "可释放空间：{size}",
        "apply_confirmation": (
            "这将修改 {notes:,} 个笔记，将 {files:,} 个重复媒体文件移入回收站，"
            "预计释放 {space}。\n\n确定继续吗？"
        ),
        "apply_result": (
            "已更新笔记：{updated:,}\n"
            "已改写引用：{rewritten:,}\n"
            "已移入回收站的媒体文件：{trashed:,}\n"
            "因过期或冲突而跳过的重复组：{skipped:,}"
        ),
    },
}


def _normalize_locale(locale: str | None) -> str:
    normalized = (locale or "").replace("-", "_").lower()
    if normalized in {"zh", "zh_cn"}:
        return "zh_CN"
    return "en"


def current_locale() -> str:
    """Return the add-on locale supported by the current Anki UI language."""
    try:
        from anki.lang import current_lang
    except Exception:
        return "en"
    return _normalize_locale(current_lang)


def tr(key: str, *, lang: str | None = None, **values: Any) -> str:
    """Translate *key* and format its named values.

    Unknown locales fall back to English; unknown keys return the key itself so
    a translation mistake cannot prevent the add-on from loading.
    """
    locale = _normalize_locale(lang) if lang is not None else current_locale()
    message = _MESSAGES.get(locale, _MESSAGES["en"]).get(
        key, _MESSAGES["en"].get(key, key)
    )
    try:
        return message.format(**values)
    except (KeyError, IndexError, ValueError):
        return message
