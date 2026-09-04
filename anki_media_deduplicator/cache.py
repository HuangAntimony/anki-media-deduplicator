from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .models import FileInfo


@dataclass(frozen=True, slots=True)
class CacheEntry:
    sha256: str | None
    quick: str | None


class NullHashCache:
    enabled = False

    def get(self, file: FileInfo) -> CacheEntry | None:
        return None

    def put(self, file: FileInfo, *, sha256: str | None, quick: str | None) -> None:
        return None


class HashCache(NullHashCache):
    def __init__(self, path: Path) -> None:
        self.path = path
        self.connection: sqlite3.Connection | None = None
        self.enabled = False
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(path)
            connection.execute("pragma quick_check").fetchone()
            connection.execute(
                """create table if not exists hashes (
                filename text primary key,
                size integer not null,
                mtime_ns integer not null,
                sha256 text,
                quick text
                )"""
            )
            self.connection = connection
            self.enabled = True
        except sqlite3.Error:
            if self.connection:
                self.connection.close()
            self.connection = None

    def get(self, file: FileInfo) -> CacheEntry | None:
        if not self.connection:
            return None
        try:
            row = self.connection.execute(
                "select sha256, quick from hashes where filename=? and size=? and mtime_ns=?",
                (file.filename, file.size, file.mtime_ns),
            ).fetchone()
            return CacheEntry(*row) if row else None
        except sqlite3.Error:
            self.enabled = False
            return None

    def put(self, file: FileInfo, *, sha256: str | None, quick: str | None) -> None:
        if not self.connection:
            return
        try:
            self.connection.execute(
                """insert into hashes(filename,size,mtime_ns,sha256,quick) values(?,?,?,?,?)
                on conflict(filename) do update set size=excluded.size,
                mtime_ns=excluded.mtime_ns,sha256=excluded.sha256,quick=excluded.quick""",
                (file.filename, file.size, file.mtime_ns, sha256, quick),
            )
            self.connection.commit()
        except sqlite3.Error:
            self.enabled = False

    def prune_missing(self, media_dir: Path, existing_names: set[str]) -> None:
        del media_dir
        if not self.connection:
            return
        rows = self.connection.execute("select filename from hashes").fetchall()
        stale = [(name,) for (name,) in rows if name not in existing_names]
        if stale:
            self.connection.executemany("delete from hashes where filename=?", stale)
            self.connection.commit()

    def close(self) -> None:
        if self.connection:
            self.connection.close()
            self.connection = None

