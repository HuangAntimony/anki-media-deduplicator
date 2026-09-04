from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path
from typing import BinaryIO

Opener = Callable[[Path, str], BinaryIO]
CHUNK_SIZE = 1024 * 1024
QUICK_SAMPLE_SIZE = 64 * 1024


def full_sha256(path: Path, *, opener: Opener = open, chunk_size: int = CHUNK_SIZE) -> str:
    digest = hashlib.sha256()
    with opener(path, "rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def quick_fingerprint(
    path: Path,
    size: int,
    *,
    opener: Opener = open,
    sample_size: int = QUICK_SAMPLE_SIZE,
) -> str:
    digest = hashlib.blake2b(digest_size=16)
    digest.update(size.to_bytes(8, "big", signed=False))
    with opener(path, "rb") as handle:
        digest.update(handle.read(sample_size))
        handle.seek(max(0, size - sample_size))
        digest.update(handle.read(sample_size))
    return digest.hexdigest()


def files_equal(
    first: Path,
    second: Path,
    *,
    opener: Opener = open,
    chunk_size: int = CHUNK_SIZE,
) -> bool:
    with opener(first, "rb") as left, opener(second, "rb") as right:
        while True:
            left_chunk = left.read(chunk_size)
            right_chunk = right.read(chunk_size)
            if left_chunk != right_chunk:
                return False
            if not left_chunk:
                return True

