"""Signature matching and lookup output formatting (pure logic, no I/O).

Honesty states per docs/spec.md:
- known:   print case id, diagnosis, times_seen
- unknown: print exactly `no matching case`
- unsure:  several stored cases share one signature -> print each, append
  `AMBIGUOUS - teacher review required` (never silently pick a winner)
"""

NO_MATCH = "no matching case"
AMBIGUOUS = "AMBIGUOUS - teacher review required"


def select(cases, signature):
    """All stored cases whose signature equals `signature` exactly."""
    return [case for case in cases if case["signature"] == signature]


def format_matches(matches):
    """Render the honesty state for a lookup result."""
    if not matches:
        return NO_MATCH
    ordered = sorted(
        matches, key=lambda case: (-case["times_seen"], case["id"])
    )
    lines = []
    for case in ordered:
        lines.append(f"case #{case['id']} times_seen={case['times_seen']}")
        lines.append(f"diagnosis: {case['diagnosis']}")
    if len(matches) > 1:
        lines.append(AMBIGUOUS)
    return "\n".join(lines)
