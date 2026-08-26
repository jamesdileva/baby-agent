"""S13 snapshot skill: archive-with-manifest (workplace literacy).

Born from "archive it so it's not lost.". `qa snapshot SOURCE
[--archives DIR] [--label LABEL]` makes a timestamped full-tree copy
of SOURCE into the archives folder (default ./archives) plus a
MANIFEST.json recording the absolute source path, creation instant,
and every archived file's relative posix path, size and SHA256. A
post-copy pass re-hashes the whole archive and reports
"manifest verified: N/N" - the manifest is never taken on faith
(honesty rule).

Pins (fixtures-first discipline, golden-report pattern per S10-S12):
stamps are UTC YYYYMMDDThhmmssZ, optionally prefixed "<label>-";
labels are rejected outright when empty or containing '/', '\\',
':' or dot components ('.', '..'); a stamp collision in the archives
root REFUSES to overwrite and touches nothing; the manifest never
lists itself; file rows are sorted for deterministic output;
hashing is chunked (1 MiB) so large files are never buffered whole;
empty directories survive via the manifest's "dirs" row; symlinks
copy as content (shutil default), a dangling link surfacing as an
environment error.

Exit contract PROPOSED as a spec amendment (same class as preflight
and locate, docs/DECISIONS.md): 0 snapshot created and self-verified;
1 operational failure (bad source, bad label, stamp collision);
2 environment error (copy/write failure or post-copy verification
drift). Rendered as ONE honest error line, never a traceback
(case#4 class).

A standalone re-verifier for old archives is deliberately deferred:
creation self-verifies today; revisit when a consumer needs it.
"""

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

HASH_CHUNK = 1024 * 1024
SCHEMA = 1

_MANIFEST_NAME = "MANIFEST.json"


class SnapshotError(ValueError):
    """Operational failure: bad input, refused action (exit-1 class)."""


class SnapshotEnvError(EnvironmentError):
    """Environment failure: copy/write/verify broke midway (case#4 class)."""


def utc_now_text():
    """Compact UTC stamp: YYYYMMDDThhmmssZ."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def normalize_label(label):
    """None passes through; otherwise reject unsafe archive-name labels."""
    if label is None:
        return None
    if label == "":
        raise SnapshotError("invalid label: empty")
    if any(ch in label for ch in ("/", "\\", ":")) or label in (".", ".."):
        raise SnapshotError(
            f"invalid label: {label!r} "
            "(no '/', '\\', ':' or dot components)"
        )
    return label


def make_stamp(label=None):
    """'<label>-<utcstamp>' or bare '<utcstamp>'."""
    moment = utc_now_text()
    return f"{label}-{moment}" if label else moment


def sha256_file(path):
    """Chunked digest so large files never buffer whole."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            block = handle.read(HASH_CHUNK)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def rel_paths(root):
    """Sorted (files, dirs) below root as relative posix paths.

    The top-level MANIFEST.json is excluded from files - the manifest
    can never hash itself.
    """
    files = []
    dirs = []
    for dirpath, dirnames, filenames in _walk(Path(root)):
        current = Path(dirpath)
        for name in dirnames:
            dirs.append((current / name).relative_to(root).as_posix())
        for name in filenames:
            candidate = current / name
            if candidate == Path(root) / _MANIFEST_NAME:
                continue
            files.append(candidate.relative_to(root).as_posix())
    return sorted(files), sorted(dirs)


def _walk(root):
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            entries = list(current.iterdir())
        except OSError:
            continue
        subdirs = []
        filenames = []
        for entry in entries:
            if entry.is_dir():
                subdirs.append(entry)
            else:
                filenames.append(entry.name)
        yield str(current), [entry.name for entry in subdirs], filenames
        stack.extend(reversed(subdirs))


def build_manifest(archive_dir, source, created_utc, label):
    """Manifest dict over a copied tree; pure read, deterministic."""
    files_rel, dirs_rel = rel_paths(archive_dir)
    entries = []
    for rel in files_rel:
        path = Path(archive_dir) / rel
        entries.append(
            {
                "path": rel,
                "size": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return {
        "tool": "qacompanion snapshot",
        "schema": SCHEMA,
        "created_utc": created_utc,
        "source": source,
        "label": label,
        "stamp": Path(archive_dir).name,
        "files": entries,
        "dirs": dirs_rel,
    }


def write_manifest(archive_dir, manifest):
    payload = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    (Path(archive_dir) / _MANIFEST_NAME).write_text(payload, encoding="utf-8")


def load_manifest(archive_dir):
    raw = (Path(archive_dir) / _MANIFEST_NAME).read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, dict) or not isinstance(data.get("files"), list):
        raise ValueError("not a qacompanion snapshot manifest")
    return data


def verify_archive(archive_dir):
    """Re-hash the tree against its manifest.

    Returns {"ok": bool, "checked": int, "problem": str-or-None};
    problems cover missing/deleted files, size or hash drift,
    unlisted extras and vanished recorded dirs.
    """
    try:
        manifest = load_manifest(archive_dir)
    except (ValueError, OSError) as exc:
        return {"ok": False, "checked": 0, "problem": f"manifest unreadable ({exc})"}
    archive_dir = Path(archive_dir)
    listed = set()
    problems = []
    checked = 0
    for entry in manifest["files"]:
        rel = entry["path"]
        listed.add(rel)
        checked += 1
        path = archive_dir / rel
        if not path.is_file():
            problems.append(f"missing file: {rel}")
            continue
        if path.stat().st_size != entry["size"]:
            problems.append(f"size drift: {rel}")
            continue
        if sha256_file(path) != entry["sha256"]:
            problems.append(f"hash drift: {rel}")
    files_actual, dirs_actual = rel_paths(archive_dir)
    extra = sorted(set(files_actual) - listed)
    if extra:
        problems.append(f"unlisted file(s): {', '.join(extra)}")
    for rel in manifest.get("dirs", []):
        if rel not in set(dirs_actual):
            problems.append(f"missing dir: {rel}")
    return {
        "ok": not problems,
        "checked": checked,
        "problem": "; ".join(problems) if problems else None,
    }


def create_snapshot(source, archives_root, label=None, stamp=None,
                    created_utc=None):
    """Copy SOURCE into ARCHIVES_ROOT/<stamp>, write + self-verify manifest.

    Raises SnapshotError for operational refusals (never touches the
    archives root in that case) and SnapshotEnvError when a copy or
    verification breaks midway.
    """
    src = Path(source)
    if not src.is_dir():
        raise SnapshotError(f"source is not a directory: {src}")
    label = normalize_label(label)
    stamp = stamp or make_stamp(label)
    dest = Path(archives_root) / stamp
    if dest.exists():
        raise SnapshotError(
            f"refusing to overwrite existing snapshot stamp: {dest}"
        )
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dest)
        created = created_utc or datetime.now(timezone.utc).isoformat()
        manifest = build_manifest(
            dest,
            source=str(src.resolve()),
            created_utc=created,
            label=label if label is not None else src.name,
        )
        write_manifest(dest, manifest)
        verdict = verify_archive(dest)
    except OSError as exc:
        raise SnapshotEnvError(f"environment: snapshot failed ({exc})") from exc
    if not verdict["ok"]:
        raise SnapshotEnvError(
            f"environment: post-copy verification failed: {verdict['problem']}"
        )
    total = sum(entry["size"] for entry in manifest["files"])
    return {
        "stamp": stamp,
        "dest": str(dest.resolve()),
        "source": str(src.resolve()),
        "files": len(manifest["files"]),
        "bytes": total,
        "checked": verdict["checked"],
    }


def render(results):
    """Golden three-line report; verified N/N is the honesty anchor."""
    return "\n".join(
        [
            f"snapshot '{results['stamp']}':",
            f"archived {results['files']} file(s), "
            f"{results['bytes']} byte(s) "
            f"from {results['source']} -> {results['dest']}",
            f"manifest verified: {results['checked']}/{results['files']} "
            "file(s)",
        ]
    )
