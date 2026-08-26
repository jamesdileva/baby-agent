"""S9 environment skill: classify environment failures into real diagnoses.

Direct descendant of the npm-ENOENT and FAIL(0.0s) lessons (ROADMAP S9):
a large share of red runs are not product bugs at all but environment
failures - a missing tool, a wrong working directory, a version mismatch,
refused permissions, git invoked outside any repository. Recording those
with the generic "pending teacher review" placeholder wastes the one
diagnosis the colony has already paid for.

`classify(output_text)` scans the child's merged output against an
ORDERED, first-match-wins rule set of deterministic patterns and returns
(env_class, evidence). Classes, most-specific first:

- "empty repo"        git ran outside any work tree
- "version mismatch"  runtime/engine version does not satisfy a requirement
- "permission denied" OS refused access (locked file, ownership, ACL)
- "tool missing"      command/module resolution failed (PATH, spelling)
- "wrong cwd"         generic ENOENT family - a needed path was not found
                      relative to the working directory
- UNSURE              nothing matched; caller keeps the honest generic
                      placeholder ("unknown classes stay honest")

The FULL merged output is scanned, not just the keyed error line:
environment context (e.g. npm's `code ENOENT`) often appears mid-stream
while the tail is a generic exit summary. Matching is case-insensitive;
classification never changes signatures, store format, or lookup
semantics - it only refines the diagnosis text written at capture time.
A stored classification is a proposal like any other: teacher review can
overwrite it via `record`, exactly as for manual diagnoses.
"""

import re

UNSURE = "unsure"

_RULES = (
    (
        "empty repo",
        (r"fatal:\s*not a git repository",),
    ),
    (
        "version mismatch",
        (
            r"unsupported\s+(?:engine|python|node)\s+version",
            r"\brequires\s+(?:python|node|npm|pip)\s*>=?",
            r"\bversion\s+mismatch\b",
        ),
    ),
    (
        "permission denied",
        (
            r"\bpermissionerror\b",
            r"\bpermission denied\b",
            r"\baccess is denied\b",
            r"\beacces\b",
            r"\beperm\b",
        ),
    ),
    (
        "tool missing",
        (
            r"is not recognized as an internal or external command",
            r"\bcommand not found\b",
            r"\bno module named\b",
        ),
    ),
    (
        "wrong cwd",
        (
            r"\benoent\b",
            r"\[errno 2\]",
            r"\bno such file or directory\b",
            r"\bfilenotfounderror\b",
        ),
    ),
)

_COMPILED = tuple(
    (env_class, [re.compile(pattern, re.IGNORECASE) for pattern in patterns])
    for env_class, patterns in _RULES
)

_DIAGNOSES = {
    "empty repo": (
        "Environment failure (empty repo): git ran outside any work tree "
        "(no .git here or in any parent). cd into the target repo or init "
        "one before running git plumbing; not a product bug."
    ),
    "version mismatch": (
        "Environment failure (version mismatch): the runtime/tool version "
        "does not satisfy what the command requires. Align versions, then "
        "re-run; not a product bug."
    ),
    "permission denied": (
        "Environment failure (permission denied): the OS refused access "
        "(locked file, ownership, ACL, read-only target). Fix permissions "
        "or move the target; not product logic."
    ),
    "tool missing": (
        "Environment failure (tool missing): the invoked program/module "
        "was not found by the OS or interpreter (PATH, install state, "
        "spelling). Install it or fix PATH; not a product bug."
    ),
    "wrong cwd": (
        "Environment failure (wrong cwd): a needed file/directory was not "
        "found relative to the working directory (ENOENT family). Confirm "
        "the expected path exists and you are in the intended directory "
        "before diagnosing product code."
    ),
}


def classify(output_text):
    """First-match-wins scan -> (env_class, matched_text) or (UNSURE, None).

    Pure: no I/O, deterministic order, case-insensitive.
    """
    text = output_text or ""
    for env_class, patterns in _COMPILED:
        for pattern in patterns:
            match = pattern.search(text)
            if match:
                return env_class, match.group(0)
    return UNSURE, None


def build_diagnosis(env_class):
    """Deterministic diagnosis text naming the class and the escape hatch."""
    return _DIAGNOSES[env_class]


def diagnose(output_text):
    """Convenience: diagnosis string for classified output, None if unsure."""
    env_class, _ = classify(output_text)
    if env_class == UNSURE:
        return None
    return build_diagnosis(env_class)
