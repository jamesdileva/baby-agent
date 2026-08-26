"""S21 archive-mine skill: learn from past eras.

Digest Antfarm archives, DECISIONS.md files, git logs, and failure
transcripts into importable cases. Every diagnosis ever paid for across
every colony era becomes a case.

Pins (fixtures-first discipline):
- DECISIONS.md parsed by ## heading sections;
- git log parsed by conventional-commit prefixes;
- transcript parsed by FAIL/ERROR markers;
- output is cases.jsonl-compatible (id=0 placeholder for import);
- known lore patterns (FAIL(0.0s), BOM, stale-installer) are mineable;
- dedup by signature within a mining run (first occurrence wins).
"""

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

from .. import signatures


class MineError(Exception):
    """Operational failure: unreadable source or bad output path."""


# --- DECISIONS.md parser ---

_HEADING_RE = re.compile(r"^## (.+)$", re.MULTILINE)

# Patterns that indicate a failure-related decision
_FAILURE_KEYWORDS = re.compile(
    r"(?i)(error|fail|bom|enoent|mismatch|corrupt|phantom|"
    r"wrong.*cwd|tool.*missing|version.*mismatch|permission.*denied|"
    r"json.*decode|signature|flake|regression|duplicate|"
    r"parse.*rule|volatile|crash|abort|reject)",
)

# Common error patterns to extract as error excerpts
_ERROR_EXCERPT_PATTERNS = [
    re.compile(r"(?i)(jsondecodeerror:.+?)(?:\"|$|\n)"),
    re.compile(r"(?i)(\bENOENT\b[^\n]*?)(?:\.|$|\n)"),
    re.compile(r"(?i)(FAIL[:\s]+[^\n]+?)(?:\.|$|\n)"),
    re.compile(r"(?i)(fatal:\s*.+?)(?:\"|$|\n)"),
    re.compile(r"(?i)(sha256\s+mismatch[^\n]*?)(?:\.|$|\n)"),
    re.compile(r"(?i)(not a git repository[^\n]*?)(?:\.|$|\n)"),
    re.compile(r"(?i)(permission denied[^\n]*?)(?:\.|$|\n)"),
    re.compile(r"(?i)(command not found[^\n]*?)(?:\.|$|\n)"),
    re.compile(r"(?i)(fileNotFoundError[^\n]*?)(?:\.|$|\n)"),
]

# Diagnosis extraction: look for lines that explain the root cause
_DIAGNOSIS_PATTERNS = [
    re.compile(r"(?:diagnosis|root cause|cause|happens when|result of)[:\s]+(.+?)(?:\.|$)", re.I),
    re.compile(r"(?:Rule|Rationale|Lesson)[:\s]+(.+?)(?:\.|$)", re.I),
]


def _extract_diagnosis(text):
    """Extract a diagnosis sentence from decision body text."""
    for pattern in _DIAGNOSIS_PATTERNS:
        match = pattern.search(text)
        if match:
            diag = match.group(1).strip().rstrip(".")
            if len(diag) > 20:
                return diag + "."
    # Fallback: first substantial sentence that isn't a heading or status line
    for line in text.splitlines():
        line = line.strip()
        if (
            len(line) > 40
            and not line.startswith("#")
            and not line.startswith("Status:")
            and not line.startswith("Provenance:")
            and not line.startswith("-")
            and "RATIFIED" not in line
            and "IMPLEMENTED" not in line
            and "CLOSED" not in line
        ):
            return line.rstrip(".") + "."
    return None


def _extract_error_excerpt(text):
    """Extract an error excerpt from decision body text."""
    for pattern in _ERROR_EXCERPT_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(1).strip()
    return None


def _construct_signature(title, body):
    """Construct a canonical signature from a decision title and body.

    The signature format is: test_name :: error_line
    For mined decisions, test_name comes from the title and error_line
    from the body or title.
    """
    # Clean the title to use as test name
    test_name = re.sub(r"\[.+\]", "", title).strip()
    test_name = re.sub(r"^D-\d+\s*", "", test_name).strip()

    # Try to extract error line from body
    error_line = _extract_error_excerpt(body)
    if not error_line:
        # Use a condensed version of the title as error line
        error_line = test_name.lower()

    return signatures.canonical(f"{test_name} :: {error_line}")


def parse_decisions(text):
    """Parse DECISIONS.md text into mined case entries.

    Returns a list of dicts: {signature, error_excerpt, diagnosis, source}.
    """
    cases = []
    sections = []

    # Split on ## headings
    parts = _HEADING_RE.split(text)
    # parts[0] is text before first heading (skip), then alternating title/body
    for i in range(1, len(parts), 2):
        title = parts[i].strip()
        body = parts[i + 1] if i + 1 < len(parts) else ""
        sections.append((title, body))

    for title, body in sections:
        # Only process failure-related decisions
        combined = title + " " + body
        if not _FAILURE_KEYWORDS.search(combined):
            continue

        diagnosis = _extract_diagnosis(body)
        if not diagnosis:
            continue

        error_excerpt = _extract_error_excerpt(body) or title
        signature = _construct_signature(title, body)

        cases.append({
            "signature": signature,
            "error_excerpt": error_excerpt[:4000],
            "diagnosis": diagnosis[:4000],
            "source": f"DECISIONS.md: {title}",
        })

    return cases


# --- Git log parser ---

_GIT_LOG_RE = re.compile(
    r"^(?P<hash>[0-9a-f]{7,40})\s+(?P<subject>.+)$", re.MULTILINE
)

_FIX_PREFIXES = re.compile(
    r"^(?:fix|bugfix|hotfix|patch|resolve|correct|repair)[\s:]+", re.I
)


def parse_git_log(text):
    """Parse git log --oneline text into mined case entries.

    Returns a list of dicts: {signature, error_excerpt, diagnosis, source}.
    """
    cases = []
    for match in _GIT_LOG_RE.finditer(text):
        hash_val = match.group("hash")
        subject = match.group("subject").strip()

        # Only process fix-related commits
        if not _FIX_PREFIXES.search(subject):
            continue

        # Construct signature from commit subject
        test_name = _FIX_PREFIXES.sub("", subject).strip()
        if not test_name:
            continue

        error_line = f"fixed in {hash_val}"
        signature = signatures.canonical(f"{test_name} :: {error_line}")

        cases.append({
            "signature": signature,
            "error_excerpt": subject,
            "diagnosis": f"Fixed in commit {hash_val}: {subject}",
            "source": f"git log: {hash_val}",
        })

    return cases


# --- Transcript parser ---

_FAIL_LINE_RE = re.compile(
    r"(?:^FAIL[:\s]+(.+)$|^ERROR[:\s]+(.+)$)", re.MULTILINE | re.I
)

_TEST_NAME_RE = re.compile(
    r"(?:FAILED|FAIL)\s+\(([^)]+)\)|"
    r"(?:Ran\s+\d+\s+tests?\s+in)|"
    r"^(test_\w+)", re.MULTILINE | re.I
)


def parse_transcript(text):
    """Parse a failure transcript into mined case entries.

    Returns a list of dicts: {signature, error_excerpt, diagnosis, source}.
    """
    cases = []

    for match in _FAIL_LINE_RE.finditer(text):
        error_line = (match.group(1) or match.group(2) or "").strip()
        if not error_line:
            continue

        # Try to extract test name from surrounding context
        start = max(0, match.start() - 500)
        context = text[start : match.start()]
        test_name = "unknown_test"
        name_match = _TEST_NAME_RE.search(context)
        if name_match:
            test_name = (name_match.group(1) or name_match.group(2) or "unknown_test").strip()

        signature = signatures.canonical(f"{test_name} :: {error_line}")

        cases.append({
            "signature": signature,
            "error_excerpt": error_line[:4000],
            "diagnosis": "Pending teacher review (mined from transcript).",
            "source": "transcript",
        })

    return cases


# --- Main mining function ---

def _dedup_cases(cases):
    """Dedup by signature; first occurrence wins."""
    seen = set()
    deduped = []
    for case in cases:
        sig = case["signature"]
        if sig not in seen:
            seen.add(sig)
            deduped.append(case)
    return deduped


def mine_directory(directory, sources=None):
    """Mine all supported sources in a directory.

    sources: list of source types to mine. Default: all.
    Returns {cases_mined, sources_scanned, errors}.
    """
    directory = Path(directory)
    if not directory.is_dir():
        raise MineError(f"not a directory: {directory}")

    if sources is None:
        sources = ["decisions", "git", "transcripts"]

    all_cases = []
    errors = []
    sources_scanned = 0

    if "decisions" in sources:
        for path in directory.rglob("DECISIONS.md"):
            sources_scanned += 1
            try:
                text = path.read_text(encoding="utf-8-sig")
                cases = parse_decisions(text)
                for case in cases:
                    case["source"] = str(path.relative_to(directory)) + ": " + case["source"].split(": ", 1)[-1]
                all_cases.extend(cases)
            except OSError as exc:
                errors.append((str(path), str(exc)))

    if "git" in sources:
        git_dirs = list(directory.rglob(".git"))
        for git_dir in git_dirs:
            repo_dir = git_dir.parent
            sources_scanned += 1
            try:
                result = subprocess.run(
                    ["git", "log", "--oneline", "-50"],
                    cwd=str(repo_dir),
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if result.returncode == 0:
                    cases = parse_git_log(result.stdout)
                    for case in cases:
                        rel = str(repo_dir.relative_to(directory))
                        case["source"] = f"{rel}/git: " + case["source"].split(": ", 1)[-1]
                    all_cases.extend(cases)
            except (OSError, subprocess.TimeoutExpired) as exc:
                errors.append((str(repo_dir), str(exc)))

    if "transcripts" in sources:
        for ext in ("*.txt", "*.log", "*.transcript"):
            for path in directory.rglob(ext):
                sources_scanned += 1
                try:
                    text = path.read_text(encoding="utf-8-sig")
                    if _FAIL_LINE_RE.search(text):
                        cases = parse_transcript(text)
                        for case in cases:
                            rel = str(path.relative_to(directory))
                            case["source"] = rel
                        all_cases.extend(cases)
                except OSError as exc:
                    errors.append((str(path), str(exc)))

    deduped = _dedup_cases(all_cases)
    return {
        "cases_mined": len(deduped),
        "cases": deduped,
        "sources_scanned": sources_scanned,
        "errors": errors,
    }


def export_mined(cases, out_path):
    """Write mined cases as a cases.jsonl-compatible file (id=0 placeholder).

    Returns the number of cases written.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = ""
    for case in cases:
        entry = {
            "id": 0,
            "signature": case["signature"],
            "error_excerpt": case["error_excerpt"],
            "diagnosis": case["diagnosis"],
            "times_seen": 1,
            "last_seen": "2026-01-01T00:00:00Z",
            "confirmed_by": "archive-mine",
        }
        payload += json.dumps(entry, ensure_ascii=False) + "\n"

    handle_fd, tmp_name = tempfile.mkstemp(
        dir=str(out_path.parent), prefix=".mined-", suffix=".tmp"
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(handle_fd, "w", encoding="utf-8", newline="\n") as h:
            h.write(payload)
        os.replace(tmp_path, out_path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise

    return len(cases)


def format_results(results):
    """Render mining results as human-readable output."""
    lines = []
    lines.append(
        f"mined {results['cases_mined']} case(s) "
        f"from {results['sources_scanned']} source(s)"
    )
    if results["errors"]:
        for path, err in results["errors"]:
            lines.append(f"warning: {path}: {err}")
    for case in results["cases"][:10]:
        src = case.get("source", "?")
        sig = case["signature"][:60]
        lines.append(f"  [{src}] {sig}")
    if results["cases_mined"] > 10:
        lines.append(f"  ... and {results['cases_mined'] - 10} more")
    return "\n".join(lines)
