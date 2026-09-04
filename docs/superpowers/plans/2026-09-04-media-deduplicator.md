# Anki Media Deduplicator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an Anki 26.08.1 add-on that safely consolidates byte-identical same-extension media and migrates note references before trashing redundant files.

**Architecture:** Qt-independent modules index, hash, group, infer canonical names, parse references, and execute a safety-first plan through injected ports. A thin Anki adapter runs scans in QueryOp and applies changes in CollectionOp; Qt only presents progress, dry-run results, and confirmation.

**Tech Stack:** Python 3.10+, hashlib, sqlite3, concurrent.futures, pytest, Anki Python API, Qt 6 through `aqt.qt`.

**Spec:** User requirements and the approved architecture in this conversation.

## Global Constraints

- Target Anki Desktop 26.08.1, with compatibility for 25.09.4+ where APIs match.
- Exact same-extension duplicates only; SHA-256 candidates require final chunked byte comparison.
- Directory work is O(N); hashing is O(total candidate bytes); memory is O(N).
- Scan is read-only and cancellable; Apply revalidates every group and is not cancellable after confirmation.
- References are updated before deletion; all deletion uses `MediaManager.trash_files()`.
- `_`/`latex-` names and static notetype media are never deduplicated.

---

### Task 1: Scanner, hashing, cache, and duplicate groups

**Files:** Create `models.py`, `scanner.py`, `hashing.py`, `cache.py`, `dedupe.py`; test in `test_scanner.py`, `test_hashing.py`, `test_cache.py`, `test_dedupe.py`.

**Interfaces:** `scan_directory(path, protected, cancellation, opener) -> IndexResult`; `find_duplicates(files, cache, cancellation, opener, max_workers=4) -> list[DuplicateGroup]`.

- [ ] Write behavioral tests for filtering, bucketing, quick/full hashing, byte comparison, cancellation, stale/corrupt cache, and same-extension grouping.
- [ ] Run focused tests and confirm failures are caused by missing production modules.
- [ ] Implement the minimum pure-Python core and rerun focused tests.
- [ ] Refactor while green and commit the working core.

### Task 2: Filename planning and media-reference rewriting

**Files:** Create `filename_inference.py`, `references.py`, `planner.py`; test in `test_filename_inference.py`, `test_references.py`, `test_planner.py`.

**Interfaces:** `select_canonical(group, reference_counts, media_dir, opener) -> CanonicalChoice`; `rewrite_field(text, replacements) -> RewriteResult`; `build_plan(scan, notes) -> DeduplicationPlan`.

- [ ] Write tests for all restoration states, Android long suffixes, numeric originals, short names, target conflict, all supported tags/entities, repeated references, and deterministic fallback.
- [ ] Run focused tests and confirm the expected missing-feature failures.
- [ ] Implement exact tag-scoped rewriting and confidence-based canonical selection.
- [ ] Run all pure-core tests and commit.

### Task 3: Apply safety, Anki integration, UI, and real validation

**Files:** Create `apply.py`, `compatibility.py`, `progress.py`, `addon.py`, `ui.py`, package initializer, README/LICENSE; test in `test_apply.py`, `test_crash_safety.py`, `test_compatibility.py`, and `benchmarks/test_synthetic_50000.py`.

**Interfaces:** `ApplyExecutor.execute(plan, collection_port) -> ApplyResult`; `open_dialog()` registered under Tools; QueryOp scan and CollectionOp apply.

- [ ] Write crash-order, stale-plan, residual-reference, official-trash-port, and synthetic complexity tests and observe failures.
- [ ] Implement the Anki adapter and minimal Qt dialog, then run the full automated suite and static checks.
- [ ] Install the add-on into the local Anki profile, run Dry Run against the existing collection, and inspect the plan.
- [ ] After plan inspection, Apply to the authorized collection and verify references, review playback, Check Media, and a clean rescan without triggering sync automatically.
- [ ] Package the add-on and commit the verified result.
