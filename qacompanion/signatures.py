"""Failure fingerprint normalization for qacompanion.

Per docs/spec.md: signature = test name + first error line, paths baselined,
whitespace collapsed, case-folded. Two failures match iff their signatures
are equal strings.
"""

import re

SEPARATOR = " :: "

# A path-ish token: any whitespace-delimited run (quotes excluded) that
# contains at least one / or \ separator. Such tokens reduce to their final
# component, so absolute/relative/drive-prefixed spellings collide.
_PATH_RE = re.compile(r"""[^\s'\"]*[\\/][^\s'\"]*""")


def baseline_paths(text):
    """Reduce every path-ish token to its final component."""

    def _basename(match):
        return match.group(0).replace("\\", "/").rsplit("/", 1)[-1]

    return _PATH_RE.sub(_basename, text)


def _collapse(text):
    return " ".join(text.split())


def normalize(test_name, first_error_line):
    """Build the canonical signature for one observed failure."""
    test_part = baseline_paths(_collapse(test_name)).casefold()
    error_part = baseline_paths(_collapse(first_error_line)).casefold()
    return f"{test_part}{SEPARATOR}{error_part}"


def canonical(signature):
    """Normalize a composed signature string; idempotent.

    Single gate for every --sig entering the system (teacher records and
    lookups alike): splits at the first separator so an already-normalized
    signature round-trips unchanged while path/case/whitespace variants
    collapse onto it.
    """
    test_part, _, error_part = signature.partition(SEPARATOR)
    return normalize(test_part, error_part)
