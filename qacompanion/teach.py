"""Teach helper: validate and write rule packs for the skill registry.

Usage: qa teach --rule '{"pattern": "...", ...}' [--pack PATH]

Validates the rule, appends it to the specified pack (default:
skills/taught.json), creating the pack if needed. The pack is
re-validated after each write to catch corruption.
"""

import json
import sys
from pathlib import Path

from .skills.registry import (
    RegistryError,
    _validate_pack,
    _validate_rule,
    load_pack,
)


DEFAULT_PACK = "skills/taught.json"


def teach_rule(rule_dict, pack_path):
    """Validate a rule and append it to a pack file.

    Returns the updated pack dict. Raises RegistryError on problems.
    """
    if not isinstance(rule_dict, dict):
        raise RegistryError("rule must be a JSON object")
    _validate_rule(rule_dict, "teach-input", 1)

    pack_path = Path(pack_path)
    if pack_path.exists():
        try:
            pack = load_pack(pack_path)
        except RegistryError as exc:
            raise RegistryError(f"existing pack is malformed: {exc}")
    else:
        pack = {"name": "taught", "version": "1.0", "rules": []}
        pack_path.parent.mkdir(parents=True, exist_ok=True)

    pack["rules"].append(rule_dict)

    try:
        _validate_pack_recheck(pack, str(pack_path))
    except RegistryError as exc:
        pack["rules"].pop()
        raise RegistryError(f"rejected: {exc}")

    serializable = {
        k: v for k, v in pack.items()
        if k != "rules"
    }
    serializable["rules"] = [
        {k: v for k, v in r.items() if not k.startswith("_")}
        for r in pack["rules"]
    ]

    try:
        pack_path.write_text(
            json.dumps(serializable, indent=2, sort_keys=False) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        raise RegistryError(f"cannot write {pack_path}: {exc}")

    return pack


def _validate_pack_recheck(pack, pack_name):
    """Re-validate a pack dict (used after mutation)."""
    _validate_pack(pack, pack_name)


def render_teach(rule_dict, pack_path, created=False):
    """Render the result of a teach operation."""
    verb = "created" if created else "appended to"
    return (
        f"rule {rule_dict.get('id', '?')} {verb} {pack_path}\n"
        f"  pattern: {rule_dict['pattern']}\n"
        f"  classification: {rule_dict['classification']}\n"
        f"  diagnosis: {rule_dict['diagnosis_hint']}"
    )
