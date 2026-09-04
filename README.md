# Anki Media Deduplicator

An open-source Anki Desktop add-on that safely consolidates **byte-for-byte identical**
media files. It is intended primarily for collections affected by AnkiDroid's historical
temporary-file naming behavior, where repeated imports can produce names such as
`audio123456789.mp3` and `audio987654321.mp3` for identical content.

This add-on solves **duplicate media**, not unused media. Anki's built-in **Tools → Check
Media** remains the right tool for finding files that are not referenced by any note.

## Safety model

- A scan is always a read-only dry run.
- Files are first bucketed by size and case-insensitive extension.
- Files at most 256 KiB receive a full SHA-256 hash immediately.
- Larger candidates receive a first/last 64 KiB quick fingerprint before full SHA-256.
- SHA-256 matches are confirmed with a chunked byte-for-byte comparison.
- Different extensions are never merged.
- `_` files, `latex-` files, and media statically referenced by notetype templates or CSS
  are protected.
- Apply rechecks existence, size, modification time, and bytes.
- Canonical media is created before notes are changed.
- Notes are updated through Anki's Collection API before redundant media is trashed.
- Media is trashed only through Anki's MediaManager API, so media sync can record deletion.
- Any old filename still referenced after migration is retained.

If Apply is interrupted, the safe intermediate state is that some notes point to the
canonical filename while both canonical and duplicate files still exist. Duplicate media is
never intentionally trashed before reference migration completes.

## Canonical filename restoration

After content equality is proven, the add-on attempts to recover the basename that existed
before Android `File.createTempFile()` appended a non-negative random `long`. It intersects
all valid prefix candidates in a duplicate group instead of blindly stripping digits or using
the longest common prefix. Ambiguous groups still deduplicate, but retain a deterministic
existing filename selected by reference count, then filename length, then lexical order.

The add-on also understands Hoshi Reader Android's content-addressed export format introduced
by [PR #132](https://github.com/HuangAntimony/Hoshi-Reader-Android/pull/132):
`hoshi_audio_<sha1>`, `hoshi_dict_<sha1>`, `hoshi_cover_<sha1>`, and
`hoshi_sasayaki_<sha1>`, with the original extension. If AnkiDroid later appends a temporary
random suffix to one of these names, the add-on restores the 40-character SHA-1 name after
checking that the embedded SHA-1 matches the file bytes. This rule is only used after the
normal SHA-256 and byte-for-byte duplicate checks have succeeded.

## Complexity

Directory indexing uses `os.scandir()` and is O(N). Unique `(size, extension)` buckets are
never opened. Candidate hashing is O(total candidate media bytes), note fields are scanned
once, and memory use is O(N). The implementation never compares every media file with every
other file.

An optional cache at `user_files/hash_cache.sqlite3` stores hashes by exact
`(filename, size, mtime_ns)`. Cache failure or corruption disables the optimization without
changing deduplication correctness.

## Installation

### Development installation

1. Quit Anki.
2. Place or symlink this repository into Anki's `addons21` directory under a directory name
   such as `anki_media_deduplicator_dev`.
3. Start Anki.

On macOS the default location is:

```text
~/Library/Application Support/Anki2/addons21/
```

For a packaged release, import the `.ankiaddon` file through **Tools → Add-ons → Install
from file**.

## Usage

1. Open **Tools → Anki Media Deduplicator...**.
2. Click **Scan Media**.
3. Review the dry-run summary and duplicate groups table.
4. Click **Apply Deduplication** and review the final confirmation.
5. After completion, the dialog automatically rescans the collection.

The add-on does not run at startup and does not start synchronization.

## Known limitations

- Exact duplicates only; there is no perceptual hashing, transcoding, or recompression.
- Cross-extension duplicates are intentionally retained.
- Filename restoration is conservative and often falls back to an existing filename.
- Apply is intentionally not cancellable after confirmation.
- Note changes are not placed in normal Undo history because media trash and note undo cannot
  be made atomic through the public add-on API.

## Compatibility

- Primary target: Anki Desktop 26.08.1
- Supported compatibility floor: Anki Desktop 25.09.4
- Python 3.10+

Older deprecated Anki APIs are not supported.

## Development

```bash
python3 -m venv .venv
.venv/bin/python -m pip install pytest ruff
.venv/bin/python -m pytest tests benchmarks
.venv/bin/ruff check .
```

The core modules do not import Qt or Anki and can be tested with normal pytest.

## License

GNU Affero General Public License v3.0 or later.
