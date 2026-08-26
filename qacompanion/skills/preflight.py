"""S11 preflight skill: standing QA rules as executable checks.

ROADMAP S11 encodes exactly three colony rules:

- R3: an installer/artifact sha256 must be quoted in the install
  transcript BEFORE the probe begins (stale-installer custody lore,
  seed case #3);
- no config file may carry a UTF-8 BOM (the utf-8-sig crash lore,
  case #2);
- the git working tree must be clean before claiming anything done.

`qa preflight [--transcript FILE]` runs all three read-only checks and
prints one checklist line per rule, naming the rule violated. Omitting
--transcript skips the R3 row honestly (nothing probed, nothing to
check). Exit contract PROPOSED as a spec amendment: spec.md's frozen
Subcommands table has no preflight row (QUESTION mailed to the human
per AGENTS.md; DECISIONS entry filed this slice). Implemented as:
0 all checked rules passed, 1 at least one rule FAILED, 2 environment
error - git plumbing unusable (not a repository / broken HEAD / git
missing) or an unreadable explicit transcript - rendered as ONE honest
error line, never a traceback (case#4 class).

All checks are read-only (directory walks, byte peeks, two read-only
git queries). Units inject a fake subprocess.run for hermeticity;
real-git coverage lives in the temp-repo e2e pair.
"""

import os
import re
import subprocess
from pathlib import Path

RULE_R3 = "R3 sha256-quoted-before-probe"
RULE_BOM = "no-BOM-in-configs"
RULE_TREE = "clean-tree"

PASS = "pass"
FAIL = "FAIL"
SKIP = "skip"

CONFIG_SUFFIXES = (".json", ".toml", ".ini", ".cfg", ".yaml", ".yml")
BOM = b"\xef\xbb\xbf"

_SHA256_RE = re.compile(r"(?i)\b[0-9a-f]{64}\b")
_PROBE_RE = re.compile(
    r"(?i)\b(probe|probing|download|downloading|install|installing|launch|execute|run)\b"
)


class PreflightEnvError(EnvironmentError):
    """Environment failure: checks cannot even run (case#4 class)."""


def _git(argv, root):
    """Run a read-only git query; any failure is an environment error."""
    try:
        proc = subprocess.run(
            ["git", *argv],
            cwd=str(root),
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise PreflightEnvError(f"environment: git not found ({exc})") from exc
    if proc.returncode != 0:
        detail = (proc.stderr or "").strip() or f"exit {proc.returncode}"
        raise PreflightEnvError(f"environment: git {' '.join(argv)} failed ({detail})")
    return proc.stdout


def iter_config_paths(root):
    """Sorted repo-relative posix paths of config-suffixed files (.git excluded)."""
    matches = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d != ".git")
        for name in filenames:
            path = Path(dirpath) / name
            if path.suffix.lower() in CONFIG_SUFFIXES:
                matches.append(path.relative_to(root).as_posix())
    return sorted(matches)


def first_bytes(root, rel_path):
    with open(Path(root) / rel_path, "rb") as handle:
        return handle.read(3)


def check_r3(transcript_text):
    """First quoted sha256 must precede the first probe marker line."""
    lines = (transcript_text or "").splitlines()
    quote = next((i for i, ln in enumerate(lines) if _SHA256_RE.search(ln)), None)
    probe = next((i for i, ln in enumerate(lines) if _PROBE_RE.search(ln)), None)
    if probe is None:
        return SKIP, f"no probe markers found (rule vacuous; {len(lines)} line(s))"
    if quote is None:
        return FAIL, "probe began with no sha256 quoted anywhere"
    if quote >= probe:
        return FAIL, (
            f"sha256 first quoted on line {quote + 1}, "
            f"probe began on line {probe + 1}"
        )
    return PASS, f"sha256 quoted on line {quote + 1} precedes probe on line {probe + 1}"


def check_no_bom(items):
    """items: [(rel_path, first_three_bytes)] -> (status, detail)."""
    bad = [rel for rel, head in items if head[:3] == BOM]
    if bad:
        return FAIL, "; ".join(f"{rel} starts with a UTF-8 BOM" for rel in bad)
    return PASS, f"{len(items)} config file(s) scanned, none starts with a BOM"


def check_clean_tree(text):
    rows = [line for line in (text or "").splitlines() if line.strip()]
    if rows:
        return FAIL, f"{len(rows)} uncommitted change(s) in git status --porcelain"
    return PASS, "git status --porcelain empty"


def run_checks(root, transcript_text=None):
    """Run every rule under repo `root`; read-only.

    Returns [{rule, status, detail}]. Raises PreflightEnvError instead
    of pretending results exist when the environment cannot answer.
    """
    toplevel = Path(_git(["rev-parse", "--show-toplevel"], root).strip())

    rows = []
    if transcript_text is None:
        rows.append(
            {
                "rule": RULE_R3,
                "status": SKIP,
                "detail": "no transcript supplied - rule skipped honestly",
            }
        )
    else:
        status, detail = check_r3(transcript_text)
        rows.append({"rule": RULE_R3, "status": status, "detail": detail})

    items = []
    for rel in iter_config_paths(toplevel):
        try:
            items.append((rel, first_bytes(toplevel, rel)))
        except OSError as exc:
            raise PreflightEnvError(
                f"environment: unreadable config {rel} ({exc})"
            ) from exc
    status, detail = check_no_bom(items)
    rows.append({"rule": RULE_BOM, "status": status, "detail": detail})

    status, detail = check_clean_tree(_git(["status", "--porcelain"], toplevel))
    rows.append({"rule": RULE_TREE, "status": status, "detail": detail})
    return rows


def format_results(rows):
    """Checklist rendering; each row names its rule."""
    lines = ["preflight checklist:"]
    for row in rows:
        lines.append(f"[{row['status']}] {row['rule']}: {row['detail']}")
    return "\n".join(lines)
