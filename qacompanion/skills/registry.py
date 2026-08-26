"""Declarative skill registry: JSON rule packs loaded at runtime.

Each skills/*.json file is a rule pack. Rules map patterns (regex on
error text, exit-code class) to classification/diagnosis/action hints.
New rules take effect on next run; no code changes required.

Empty skills dir = no rules; core behavior is identical.
"""

import json
import re
import sys
import threading
from pathlib import Path

REQUIRED_FIELDS = {"pattern", "classification", "diagnosis_hint"}
OPTIONAL_FIELDS = {"id", "exit_code", "action_hint", "_compiled", "_pack"}
VALID_CLASSIFICATIONS = {
    "test-failure", "environment-error", "build-failure",
    "configuration-error", "dependency-error", "flaky-test",
    "unknown",
}

MAX_PATTERN_LEN = 1000
_REGEX_TIMEOUT = 0.5


class RegistryError(Exception):
    """Raised on malformed rule packs or invalid rules."""


def _validate_rule(rule, pack_name, index):
    """Validate a single rule dict. Raises RegistryError on problems."""
    if not isinstance(rule, dict):
        raise RegistryError(
            f"pack {pack_name!r}: rule #{index} is not a dict"
        )
    unknown = set(rule.keys()) - (REQUIRED_FIELDS | OPTIONAL_FIELDS)
    if unknown:
        raise RegistryError(
            f"pack {pack_name!r}: rule #{index} has unknown fields: "
            + ", ".join(sorted(unknown))
        )
    missing = REQUIRED_FIELDS - set(rule.keys())
    if missing:
        raise RegistryError(
            f"pack {pack_name!r}: rule #{index} missing required fields: "
            + ", ".join(sorted(missing))
        )
    pat = rule["pattern"]
    if not isinstance(pat, str) or not pat:
        raise RegistryError(
            f"pack {pack_name!r}: rule #{index} pattern must be non-empty string"
        )
    if len(pat) > MAX_PATTERN_LEN:
        raise RegistryError(
            f"pack {pack_name!r}: rule #{index} pattern exceeds "
            f"{MAX_PATTERN_LEN} chars"
        )
    try:
        re.compile(pat)
    except re.error as exc:
        raise RegistryError(
            f"pack {pack_name!r}: rule #{index} invalid regex: {exc}"
        )
    cls = rule["classification"]
    if cls not in VALID_CLASSIFICATIONS:
        raise RegistryError(
            f"pack {pack_name!r}: rule #{index} unknown classification {cls!r}"
        )
    diag = rule["diagnosis_hint"]
    if not isinstance(diag, str) or not diag:
        raise RegistryError(
            f"pack {pack_name!r}: rule #{index} diagnosis_hint must be non-empty string"
        )
    if "exit_code" in rule:
        ec = rule["exit_code"]
        if not isinstance(ec, int) or ec < 0 or ec > 255:
            raise RegistryError(
                f"pack {pack_name!r}: rule #{index} exit_code must be int 0-255"
            )
    if "action_hint" in rule:
        ah = rule["action_hint"]
        if not isinstance(ah, str) or not ah:
            raise RegistryError(
                f"pack {pack_name!r}: rule #{index} action_hint must be non-empty string"
            )


def _validate_pack(pack, pack_name):
    """Validate a full pack dict. Raises RegistryError on problems."""
    if not isinstance(pack, dict):
        raise RegistryError(f"pack {pack_name!r} is not a JSON object")
    unknown_top = set(pack.keys()) - {"name", "version", "rules"}
    if unknown_top:
        raise RegistryError(
            f"pack {pack_name!r} has unknown top-level fields: "
            + ", ".join(sorted(unknown_top))
        )
    if "rules" not in pack:
        raise RegistryError(f"pack {pack_name!r} missing 'rules' array")
    rules = pack["rules"]
    if not isinstance(rules, list):
        raise RegistryError(f"pack {pack_name!r}: 'rules' is not an array")
    for i, rule in enumerate(rules, 1):
        _validate_rule(rule, pack_name, i)


def load_pack(path):
    """Load and validate a single JSON rule pack file.

    Returns the validated pack dict with compiled regex patterns added
    as '_compiled' on each rule (for internal use only).
    """
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise RegistryError(f"cannot read {path}: {exc}")
    if raw[:3] == b'\xef\xbb\xbf':
        raw = raw[3:]
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RegistryError(f"non-UTF-8 in {path.name}: {exc}")
    try:
        pack = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RegistryError(f"malformed JSON in {path.name}: {exc}")
    _validate_pack(pack, path.name)
    for rule in pack["rules"]:
        rule["_compiled"] = re.compile(rule["pattern"])
    return pack


def load_all(skills_dir):
    """Load all *.json rule packs from a directory.

    Returns (packs, errors) where packs is a list of validated pack
    dicts and errors is a list of (path, error_string) for any packs
    that failed to load. Skips non-JSON files silently.
    """
    skills_dir = Path(skills_dir)
    packs = []
    errors = []
    if not skills_dir.is_dir():
        return packs, errors
    for path in sorted(skills_dir.glob("*.json")):
        try:
            packs.append(load_pack(path))
        except RegistryError as exc:
            errors.append((path, str(exc)))
    return packs, errors


def _match_one_pattern(compiled, text, timeout):
    """Run compiled.search(text) in a thread with a timeout guard.

    Returns True if the pattern matched within the timeout, False otherwise.
    A timeout degrades to 'unsure' (no match) — never hangs.
    """
    result = [False]
    def _run():
        result[0] = bool(compiled.search(text))
    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        return False
    return result[0]


def match_rules(packs, error_text, exit_code=None):
    """Match error text (and optional exit code) against all rules.

    Returns a list of matched rules (each is a dict with '_compiled'
    removed). Empty list = no matches. Multiple matches = caller decides
    how to present (AMBIGUOUS if >1).

    Each pattern is executed with a timeout guard — a runaway regex
    degrades to 'unsure' (no match) instead of hanging lookup.
    """
    matches = []
    for pack in packs:
        pack_name = pack.get("name", "unnamed")
        for rule in pack["rules"]:
            if not _match_one_pattern(rule["_compiled"], error_text, _REGEX_TIMEOUT):
                continue
            if "exit_code" in rule and rule["exit_code"] != exit_code:
                continue
            clean = {k: v for k, v in rule.items() if k != "_compiled"}
            clean["_pack"] = pack_name
            matches.append(clean)
    return matches


def format_rule_matches(matches):
    """Render matched rules as human-readable text."""
    if not matches:
        return "no matching rules"
    lines = []
    for m in matches:
        lines.append(f"rule {m.get('id', '?')} [{m['_pack']}]: {m['classification']}")
        lines.append(f"  diagnosis: {m['diagnosis_hint']}")
        if m.get("action_hint"):
            lines.append(f"  action: {m['action_hint']}")
    if len(matches) > 1:
        lines.append("AMBIGUOUS - multiple rules matched")
    return "\n".join(lines)
