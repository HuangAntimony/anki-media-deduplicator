from __future__ import annotations

import html
import re
from dataclasses import dataclass

SOUND_PATTERN = r"(?i)(\[sound:(?P<fname>[^]]+)\])"
HTML_PATTERNS = (
    r"(?i)(<(?:img|audio|source)\b[^>]* src=(?P<str>[\"'])(?P<fname>[^>]+?)(?P=str)[^>]*>)",
    r"(?i)(<(?:img|audio|source)\b[^>]* src=(?!['\"])(?P<fname>[^ >]+)[^>]*?>)",
    r"(?i)(<object\b[^>]* data=(?P<str>[\"'])(?P<fname>[^>]+?)(?P=str)[^>]*>)",
    r"(?i)(<object\b[^>]* data=(?!['\"])(?P<fname>[^ >]+)[^>]*?>)",
)
PATTERNS = (SOUND_PATTERN, *HTML_PATTERNS)
REMOTE_PATTERN = re.compile(r"(?i)^(?:https?|ftp)://")


@dataclass(frozen=True, slots=True)
class RewriteResult:
    text: str
    replacements: int


def extract_references(text: str) -> list[str]:
    references: list[str] = []
    for pattern in PATTERNS:
        for match in re.finditer(pattern, text):
            decoded = html.unescape(match.group("fname"))
            if not REMOTE_PATTERN.match(decoded):
                references.append(decoded)
    return references


def rewrite_field(text: str, replacements: dict[str, str]) -> RewriteResult:
    count = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal count
        raw_name = match.group("fname")
        decoded = html.unescape(raw_name)
        if REMOTE_PATTERN.match(decoded) or decoded not in replacements:
            return match.group(0)
        new_name = replacements[decoded]
        if decoded != raw_name:
            new_name = html.escape(new_name, quote=False)
        count += 1
        start, end = match.span("fname")
        whole_start = match.start(0)
        relative_start = start - whole_start
        relative_end = end - whole_start
        whole = match.group(0)
        return whole[:relative_start] + new_name + whole[relative_end:]

    result = text
    for pattern in PATTERNS:
        result = re.sub(pattern, replace, result)
    return RewriteResult(result, count)
