"""S25 weakest-subject requests: rank knowledge gaps, request teaching.

Scans the case base and classifies each case into a subject category
(registry-aligned: test-failure, environment-error, build-failure,
configuration-error, dependency-error, flaky-test, unknown). Categories
with zero or low case counts are flagged as knowledge gaps; the tool
generates teaching requests for the weakest subjects.

Exit: gap report generated; requested lessons closable via new cases.
"""

import re
from collections import Counter
from pathlib import Path

from .. import store

# Registry-aligned subject categories (subset that matters in practice)
CATEGORIES = (
    "test-failure",
    "environment-error",
    "build-failure",
    "configuration-error",
    "dependency-error",
    "flaky-test",
    "unknown",
)

# Categories with count < THIN_THRESHOLD are "thin"; 0 = "empty"
THIN_THRESHOLD = 3

# Patterns for classifying a case from signature + error_excerpt (lowered)
_PATTERNS = [
    # environment errors
    (r"enoent|file.?not.?found|no.?such.?file|errno", "environment-error"),
    (r"permission.?denied|access.?denied|eacces", "environment-error"),
    (r"not a git repository", "environment-error"),
    (r"wrong.?cwd|working.?directory", "environment-error"),
    # build failures
    (r"syntax.?error|indentation.?error|invalid.?syntax", "build-failure"),
    (r"make.*fail|ninja.*fail|cmake.*fail|cargo.*fail", "build-failure"),
    # configuration errors
    (r"bom|utf-?8-sig|encoding", "configuration-error"),
    (r"jsondecodeerror|json.?decode|invalid.?json", "configuration-error"),
    (r"config.?error|missing.?key|unknown.?field", "configuration-error"),
    # dependency errors
    (r"module.?not.?found|import.?error|no.?module.?named", "dependency-error"),
    (r"version.?mismatch|requires?.?python|incompatible", "dependency-error"),
    (r"pip.*fail|npm.*fail|cargo.*fail", "dependency-error"),
    # flaky tests
    (r"flake|flaky|intermittent|timing", "flaky-test"),
    # test failures (broad catch — must come after more specific patterns)
    (r"assert|assertEqual|assertion.?error|traceback|error:|exception",
     "test-failure"),
    (r"typeerror|valueerror|attributeerror|runtimeerror", "test-failure"),
    (r"failed|failures?|FAILED", "test-failure"),
]


def classify_case(case):
    """Classify a case dict into a subject category.

    Returns one of the CATEGORIES strings.  Deterministic: same input
    always yields the same category.
    """
    text = (
        case.get("signature", "") + " " + case.get("error_excerpt", "")
    ).lower()
    for pattern, category in _PATTERNS:
        if re.search(pattern, text):
            return category
    return "unknown"


def _case_count_by_category(cases):
    """Return Counter of category -> count for the given cases."""
    counts = Counter()
    for case in cases:
        counts[classify_case(case)] += 1
    return counts


def analyze_gaps(cases):
    """Analyze the case base for knowledge gaps.

    Returns a list of dicts sorted by count ascending (weakest first):
      [{"category": str, "count": int, "status": "empty"|"thin"|"covered",
        "request": str}]
    """
    counts = _case_count_by_category(cases)
    gaps = []
    for cat in CATEGORIES:
        n = counts.get(cat, 0)
        if n == 0:
            status = "empty"
            request = f"I have no cases for {cat} — please walk me through some."
        elif n < THIN_THRESHOLD:
            status = "thin"
            request = (
                f"I have only {n} case(s) for {cat} — "
                "do you have more examples?"
            )
        else:
            status = "covered"
            request = ""
        gaps.append({
            "category": cat,
            "count": n,
            "status": status,
            "request": request,
        })
    gaps.sort(key=lambda g: (g["count"], g["category"]))
    return gaps


def format_gap_report(gaps):
    """Render the gap analysis as human-readable text."""
    lines = ["Subject coverage report", ""]
    for g in gaps:
        marker = {"empty": "!!", "thin": "! ", "covered": "  "}[g["status"]]
        lines.append(f"  [{marker}] {g['category']}: {g['count']} case(s)")
    lines.append("")
    weak = [g for g in gaps if g["status"] != "covered"]
    if not weak:
        lines.append("All subjects adequately covered.")
    else:
        lines.append("Teaching requests:")
        for g in weak:
            lines.append(f"  - {g['request']}")
    return "\n".join(lines)


def track_gap_fill(cases_before, cases_after):
    """Detect when new cases fill previously empty/thin categories.

    Returns a list of dicts for categories that improved status:
      [{"category": str, "before": int, "after": int,
        "filled": "empty->thin"|"empty->covered"|"thin->covered"}]
    """
    before_counts = _case_count_by_category(cases_before)
    after_counts = _case_count_by_category(cases_after)
    filled = []
    for cat in CATEGORIES:
        b = before_counts.get(cat, 0)
        a = after_counts.get(cat, 0)
        if a <= b:
            continue
        b_status = "empty" if b == 0 else ("thin" if b < THIN_THRESHOLD else "covered")
        a_status = "empty" if a == 0 else ("thin" if a < THIN_THRESHOLD else "covered")
        if b_status == a_status:
            continue
        filled.append({
            "category": cat,
            "before": b,
            "after": a,
            "filled": f"{b_status}->{a_status}",
        })
    filled.sort(key=lambda f: f["category"])
    return filled


def format_gap_fill(fills):
    """Render gap-fill notifications as human-readable text."""
    if not fills:
        return ""
    lines = ["Gap fills:"]
    for f in fills:
        lines.append(
            f"  {f['category']}: {f['before']} -> {f['after']} "
            f"({f['filled']})"
        )
    return "\n".join(lines)


def run_analysis(cases_path=None):
    """Load cases and run gap analysis. Returns (gaps, cases).

    cases_path: optional path override; defaults to store default.
    """
    cs = store.CaseStore(cases_path)
    cases = cs.load()
    gaps = analyze_gaps(cases)
    return gaps, cases
