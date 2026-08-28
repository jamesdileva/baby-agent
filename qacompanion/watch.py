"""Resident digest daemon — periodic hash-based file scanning.

qa watch --archives PATH --roots PATH[,PATH...]
         [--interval SECONDS] [--once]
"""

import hashlib
import json
import logging
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from .skills.digest import DigestError, DigestStore, digest_directory, parse_markdown

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL = 300  # 5 minutes
LEDGER_FILENAME = "scan-ledger.json"
LEDGER_VERSION = 1


class WatchError(Exception):
    pass


class ScanLedger:
    """Persistent scan state — per-file hashes for change detection."""

    def __init__(self, path):
        self.path = Path(path)
        self.data = {"version": LEDGER_VERSION, "last_scan": None, "files": {}}

    def load(self):
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if raw.get("version") != LEDGER_VERSION:
                logger.warning("ledger version mismatch, re-scanning from scratch")
                self.data = {"version": LEDGER_VERSION, "last_scan": None, "files": {}}
                return
            self.data = raw
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("corrupt ledger at %s, re-scanning from scratch: %s", self.path, exc)
            self.data = {"version": LEDGER_VERSION, "last_scan": None, "files": {}}

    def save(self):
        tmp = self.path.with_suffix(".json.tmp")
        self.data["last_scan"] = _now_iso()
        tmp.write_text(json.dumps(self.data, indent=2) + "\n", encoding="utf-8")
        os.replace(str(tmp), str(self.path))

    def get_hash(self, rel_path):
        entry = self.data["files"].get(rel_path)
        return entry["sha256"] if entry else None

    def set_hash(self, rel_path, sha256, size):
        self.data["files"][rel_path] = {
            "sha256": sha256,
            "last_digested": _now_iso(),
            "size": size,
        }

    def remove_missing(self, existing_paths):
        """Remove ledger entries for files that no longer exist."""
        to_remove = [k for k in self.data["files"] if k not in existing_paths]
        for k in to_remove:
            del self.data["files"][k]
        return len(to_remove)


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def scan_roots(roots, ledger):
    """Walk roots, return list of (root, rel_path, abs_path) for changed files."""
    changed = []
    all_rel = set()
    for root in roots:
        root = Path(root)
        if not root.is_dir():
            logger.warning("root not a directory, skipping: %s", root)
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            try:
                rel = str(path.relative_to(root))
            except ValueError:
                continue
            full_key = f"{root}:{rel}"
            all_rel.add(full_key)
            try:
                sha = file_sha256(path)
            except OSError as exc:
                logger.warning("cannot hash %s: %s", path, exc)
                continue
            if ledger.get_hash(full_key) != sha:
                changed.append((root, rel, path, full_key, sha))
    return changed, all_rel


def digest_changed(changed, ledger, store_path=None):
    """Digest changed files and update ledger."""
    results = {"files_scanned": 0, "entries_added": 0, "entries_updated": 0, "errors": []}
    for root, rel, path, full_key, sha in changed:
        results["files_scanned"] += 1
        if not path.suffix == ".md":
            ledger.set_hash(full_key, sha, path.stat().st_size)
            continue
        try:
            sections = parse_markdown(path)
            store = DigestStore(store_path)
            for section in sections:
                _, created = store.add(
                    source=f"{root.name}:{rel}",
                    heading=section["heading"],
                    content=section["content"],
                )
                if created:
                    results["entries_added"] += 1
            ledger.set_hash(full_key, sha, path.stat().st_size)
        except DigestError as exc:
            results["errors"].append((str(path), str(exc)))
        except OSError as exc:
            results["errors"].append((str(path), str(exc)))
    return results


class WatchDaemon:
    def __init__(self, archives, roots, interval=DEFAULT_INTERVAL, once=False,
                 data_dir=None, store_path=None):
        self.archives = Path(archives)
        self.roots = [Path(r) for r in roots]
        self.interval = interval
        self.once = once
        self.shutdown_requested = False
        self.store_path = store_path

        if data_dir is None:
            data_dir = self.archives
        self.ledger = ScanLedger(Path(data_dir) / LEDGER_FILENAME)

    def _handle_signal(self, signum, frame):
        logger.info("shutdown requested (signal %d)", signum)
        self.shutdown_requested = True

    def run(self):
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

        self.ledger.load()
        logger.info("watch daemon starting (interval=%ds, once=%s)", self.interval, self.once)

        while not self.shutdown_requested:
            self._scan_cycle()
            if self.once:
                break
            self._interruptible_sleep()

        self.ledger.save()
        logger.info("watch daemon stopped")

    def _scan_cycle(self):
        all_roots = [self.archives] + self.roots
        changed, all_rel = scan_roots(all_roots, self.ledger)
        removed = self.ledger.remove_missing(all_rel)

        if changed:
            results = digest_changed(changed, self.ledger, self.store_path)
            logger.info(
                "scanned %d file(s): %d added, %d updated, %d errors, %d removed ledger entries",
                results["files_scanned"], results["entries_added"],
                results["entries_updated"], len(results["errors"]), removed,
            )
            for path, err in results["errors"]:
                logger.warning("digest error %s: %s", path, err)
        else:
            logger.info("no changes detected")

        self.ledger.save()

    def _interruptible_sleep(self):
        deadline = time.monotonic() + self.interval
        while time.monotonic() < deadline and not self.shutdown_requested:
            time.sleep(min(1, deadline - time.monotonic()))


def watch(archives, roots, interval=DEFAULT_INTERVAL, once=False,
          data_dir=None, store_path=None, verbose=False):
    """High-level entry point for qa watch."""
    if verbose:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    else:
        logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(message)s")

    archives = Path(archives)
    if not archives.is_dir():
        raise WatchError(f"archives path is not a directory: {archives}")

    root_paths = []
    for r in roots:
        p = Path(r)
        if not p.is_dir():
            raise WatchError(f"root path is not a directory: {p}")
        root_paths.append(p)

    daemon = WatchDaemon(
        archives=archives,
        roots=root_paths,
        interval=interval,
        once=once,
        data_dir=data_dir,
        store_path=store_path,
    )
    daemon.run()
    return {"status": "ok"}
