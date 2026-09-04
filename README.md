# Anki Media Deduplicator

An Anki Desktop add-on that safely removes media files whose contents are exactly identical.

It is especially useful for collections affected by AnkiDroid imports that saved the same
audio or image repeatedly under different filenames.

> This add-on removes **duplicate media**. It does not replace Anki's **Check Media** tool,
> which finds unused or missing files.

## Features

- Read-only scan and Dry Run before anything is changed.
- Only merges files that are byte-for-byte identical and have the same extension.
- Shows affected notes, references to rewrite, and reclaimable space before applying.
- Updates note references before moving redundant files to Anki's trash.
- Protects static template/CSS media, `_` files, and `latex-` files.
- Uses Anki's official collection and media APIs so changes sync correctly.
- English and Simplified Chinese interface.

## Installation

### AnkiWeb (recommended)

1. In Anki Desktop, open **Tools → Add-ons**.
2. Click **Get Add-ons...**.
3. Enter add-on code **`490461948`**.
4. Restart Anki.

[Open the AnkiWeb add-on page](https://ankiweb.net/shared/info/490461948)

### GitHub release

Download the `.ankiaddon` file from the latest GitHub release, then open it with Anki or
choose **Tools → Add-ons → Install from file...**.

## Usage

1. Open **Tools → Anki Media Deduplicator...**.
2. Click **Scan Media**.
3. Review the Dry Run summary and duplicate groups.
4. Click **Apply Deduplication** and check the confirmation carefully.
5. Sync Anki normally after completion.

The add-on does not run automatically and does not start a sync.

## Safety

Files are verified again when you apply a scan result. If a file has changed or disappeared,
its duplicate group is skipped. A canonical file is always made available and note references
are migrated before redundant copies are trashed.

As with any tool that modifies a collection, make sure your collection has a current backup
before applying changes.

## Limitations

- Exact duplicates only; similar images or transcoded audio are not detected.
- Files with different extensions are not merged.
- Unused-media cleanup is outside this add-on's scope.
- Apply cannot be cancelled after confirmation.

## Compatibility

- Anki Desktop 26.08.1 is the primary target.
- Anki Desktop 25.09.4 and newer are supported.
- Older deprecated Anki APIs are not supported.

## Development

```bash
python3 -m venv .venv
.venv/bin/python -m pip install pytest ruff
.venv/bin/python -m pytest tests benchmarks
.venv/bin/ruff check .
```

The test suite includes a synthetic 50,000-file workload.

## License

GNU Affero General Public License v3.0 or later.
