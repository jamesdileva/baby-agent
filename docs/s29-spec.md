# S29 — Resident Digest Daemon: Design Spec

## Overview

`qa watch --archives PATH --roots PATH[,PATH...]` runs as a long-lived
daemon that periodically scans file trees, detects new/changed files via
content hashing, and digests them into the digest store. It resumes
cleanly after crashes or restarts via a scan ledger.

## Architecture

```
qa watch --archives PATH --roots PATH[,PATH...]
         [--interval SECONDS] [--once]
```

- **Poll loop**: sleep `interval` (default 300s), then scan all roots.
- **Scan**: walk each root, compute per-file SHA-256, compare against ledger.
- **Digest**: pass new/changed files to the existing `digest_directory()` function.
- **Ledger**: persist scan state so restarts resume without re-digesting.

## Scan Ledger

### Format

JSON file at `<data_dir>/scan-ledger.json` (next to `cases.jsonl`).

```json
{
  "version": 1,
  "last_scan": "2026-08-28T01:00:00Z",
  "files": {
    "relative/path/to/file.md": {
      "sha256": "abcdef...",
      "last_digested": "2026-08-28T01:00:00Z",
      "size": 1234
    }
  }
}
```

### Atomicity

Write to `scan-ledger.json.tmp`, then `os.replace()` (atomic on POSIX
and NTFS). If the daemon crashes mid-write, the old ledger survives.

### Corruption recovery

If the ledger fails to parse (JSON decode error), log a warning and
re-scan all files from scratch. This is safe because `digest_directory()`
deduplicates by content hash — re-digesting the same content is idempotent
(it updates `last_digested` but produces no duplicate digest entries).

## Hash Storage

Per-file hashes live in the ledger itself (the `files` dict). No separate
hash file. The ledger IS the hash store.

Rationale: the ledger is small (one entry per tracked file), and keeping
hashes co-located with scan state avoids consistency issues between two
files.

## Signal Handling

On SIGINT / SIGTERM (or Ctrl+C on Windows):
1. Set a `shutdown_requested` flag.
2. Finish digesting the current file (don't interrupt mid-digest).
3. Write the ledger atomically.
4. Exit with code 0.

On Windows, `signal.signal(signal.SIGINT, handler)` and
`signal.signal(signal.SIGTERM, handler)` work for console apps.
The daemon also catches `KeyboardInterrupt` as a fallback.

## Edge Cases

| Scenario | Behavior |
|----------|----------|
| File changes mid-scan | Hash computed on whatever content is there; next scan picks up the new version |
| New files between scans | Detected on next scan (not in ledger or hash differs) |
| Symlinks | Followed by `os.walk()` default; hash the target content |
| Non-UTF-8 files | Skipped with warning (matches existing `digest_directory()` behavior) |
| Empty files | Skipped (nothing to digest) |
| Large files (>10MB) | Hashed but digested normally; no special handling |
| Ledger grows unbounded | Periodic compaction: remove entries for files that no longer exist on disk |

## Testing Strategy

The "24h unattended run" exit criterion is verified by a shorter proxy test:

1. **Unit tests** (mock clock, temp dirs): create files, run `--once` mode,
   verify ledger state, modify files, run again, verify only changed files
   re-digested.
2. **Crash recovery test**: write a corrupt ledger, verify daemon re-scans.
3. **Signal test**: send SIGINT during scan, verify ledger is written cleanly.
4. **Integration test** (5-minute unattended): create a temp archive tree,
   run daemon with `--interval 5`, inject new files at t=10s and t=20s,
   verify all files digested exactly once by t=30s.

The 24h run is a manual validation step, not a CI gate.

## CLI Contract

```
qa watch --archives PATH --roots PATH[,PATH...]
         [--interval SECONDS] [--once]
         [--data-dir PATH]
```

- `--once`: scan once and exit (for testing and cron-style usage).
- `--interval`: seconds between scans (default 300).
- `--data-dir`: where to store `scan-ledger.json` (default: same dir as `cases.jsonl`).
- Exit 0 on clean shutdown, exit 1 on unrecoverable error.

## Files to Create/Modify

- `tests/test_watch_daemon.py` — unit + integration tests
- `qa_companion/watch.py` — daemon implementation
- `qa_companion/cli.py` — wire `qa watch` subcommand
- `docs/ROADMAP.md` — expand S29 section with this spec summary
