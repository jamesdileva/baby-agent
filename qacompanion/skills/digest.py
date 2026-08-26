"""S20 digest skill: document ingestion and retrieval.

Point at a directory (or repo): parse all markdown/docs into the knowledge
base as retrievable entries. `qa ask "deployment?"` returns cited passages.
Project context becomes lookup, not re-reading.

Pins (fixtures-first discipline):
- digest store is JSONL, one JSON object per line (cases.jsonl pattern);
- sections split on /^#/ headings; text before first heading uses filename;
- content_hash is SHA-256 of body text for dedup;
- re-digest updates timestamp on matching hash, never duplicates;
- search is case-insensitive keyword match (AND semantics);
- citations show source file + heading + snippet.
"""

import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_STORE = "digest.jsonl"


class DigestError(Exception):
    """Operational failure: bad input, unreadable file, or store error."""


def _timestamp():
    """Return UTC ISO-8601 without timezone suffix."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _content_hash(text):
    """SHA-256 hex digest of stripped text content."""
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()


def parse_markdown(path):
    """Parse a markdown file into sections split on /^#/ headings.

    Returns a list of dicts: {heading, content}. Text before the first
    heading gets heading = filename stem. Empty sections are skipped.
    """
    try:
        raw = Path(path).read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise DigestError(f"cannot read {path}: {exc}") from exc

    filename = Path(path).stem
    sections = []
    current_heading = filename
    current_lines = []

    for line in raw.splitlines():
        if line.startswith("#"):
            if current_lines:
                body = "\n".join(current_lines).strip()
                if body:
                    sections.append({"heading": current_heading, "content": body})
            current_heading = line.lstrip("#").strip() or filename
            current_lines = []
        else:
            current_lines.append(line)

    body = "\n".join(current_lines).strip()
    if body:
        sections.append({"heading": current_heading, "content": body})

    if not sections:
        sections.append({"heading": filename, "content": "(empty document)"})

    return sections


class DigestStore:
    """Reader/writer for the digest.jsonl format."""

    def __init__(self, path=None):
        self.path = Path(path) if path is not None else Path(DEFAULT_STORE)

    def load(self):
        """Return all digest entries. Aborts on malformed input."""
        if not self.path.exists():
            return []
        text = self.path.read_text(encoding="utf-8-sig")
        entries = []
        for line_number, raw in enumerate(text.splitlines(), start=1):
            if not raw.strip():
                continue
            try:
                entry = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise DigestError(
                    f"line {line_number}: invalid JSON ({exc.msg})"
                ) from exc
            entries.append(entry)
        return entries

    def save(self, entries):
        """Atomically replace the digest store."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = "".join(
            json.dumps(e, ensure_ascii=False) + "\n" for e in entries
        )
        handle_fd, tmp_name = tempfile.mkstemp(
            dir=str(self.path.parent), prefix=".digest-", suffix=".tmp"
        )
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(handle_fd, "w", encoding="utf-8", newline="\n") as h:
                h.write(payload)
            os.replace(tmp_path, self.path)
        except BaseException:
            tmp_path.unlink(missing_ok=True)
            raise

    def add(self, source, heading, content, now=None):
        """Add a digested section. Dedup by content_hash: update if exists.

        Returns (entry, created).
        """
        stamp = now or _timestamp()
        chash = _content_hash(content)
        entry = {
            "id": 0,
            "source": source,
            "heading": heading,
            "content": content,
            "content_hash": chash,
            "digested_at": stamp,
        }
        entries = self.load()
        for existing in entries:
            if existing.get("content_hash") == chash:
                existing["digested_at"] = stamp
                self.save(entries)
                return existing, False
        entry["id"] = (entries[-1]["id"] + 1) if entries else 1
        entries.append(entry)
        self.save(entries)
        return entry, True


def digest_directory(directory, store_path=None):
    """Walk a directory, parse markdown files, store digested sections.

    Returns {files_scanned, entries_added, entries_updated, errors}.
    """
    directory = Path(directory)
    if not directory.is_dir():
        raise DigestError(f"not a directory: {directory}")

    store = DigestStore(store_path)
    results = {
        "files_scanned": 0,
        "entries_added": 0,
        "entries_updated": 0,
        "errors": [],
    }

    for path in sorted(directory.rglob("*.md")):
        results["files_scanned"] += 1
        try:
            sections = parse_markdown(path)
        except DigestError as exc:
            results["errors"].append((str(path), str(exc)))
            continue
        rel = str(path.relative_to(directory))
        for section in sections:
            _, created = store.add(
                source=rel,
                heading=section["heading"],
                content=section["content"],
            )
            if created:
                results["entries_added"] += 1
            else:
                results["entries_updated"] += 1

    return results


def search(query, store_path=None):
    """Search digest entries for case-insensitive keyword matches.

    Returns list of matching entries sorted by relevance (keyword density).
    """
    store = DigestStore(store_path)
    entries = store.load()
    if not entries or not query or not query.strip():
        return []

    keywords = query.lower().split()
    scored = []
    for entry in entries:
        text_lower = entry["content"].lower()
        heading_lower = entry.get("heading", "").lower()
        hits = sum(1 for kw in keywords if kw in text_lower or kw in heading_lower)
        if hits > 0:
            scored.append((hits / len(keywords), entry))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [entry for _, entry in scored]


def _snippet(text, query, context_chars=80):
    """Extract a snippet around the first keyword match."""
    keywords = query.lower().split()
    text_lower = text.lower()
    best_pos = len(text)
    for kw in keywords:
        pos = text_lower.find(kw)
        if 0 <= pos < best_pos:
            best_pos = pos

    start = max(0, best_pos - context_chars)
    end = min(len(text), best_pos + context_chars)
    snippet = text[start:end].strip()
    if start > 0:
        snippet = "..." + snippet
    if end < len(text):
        snippet = snippet + "..."
    return snippet


def format_results(results, query):
    """Render search results as human-readable cited output."""
    if not results:
        return f"no matching passages for '{query}'"
    lines = []
    for entry in results[:10]:
        src = entry.get("source", "?")
        heading = entry.get("heading", "?")
        snippet = _snippet(entry["content"], query)
        lines.append(f"[{src}] #{heading}")
        lines.append(f"  {snippet}")
    if len(results) > 10:
        lines.append(f"  ... and {len(results) - 10} more")
    return "\n".join(lines)
