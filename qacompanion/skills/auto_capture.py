"""S7 auto-capture hook: wrap a command, auto-record its failure.

`qa run -- <cmd>` executes <cmd> as an argv list (never through a shell),
echoes the child's merged stdout+stderr verbatim to qacompanion's stderr
(nothing swallowed - the FAIL(0.0s) lesson), and on nonzero exit records
exactly one case:

- signature: normalized command line + error part chosen by the hybrid
  parse rule (D-0007 Amendment 1): summary-shaped lines (^OK / ^FAILED /
  ^Ran N) are stripped first and never key a signature; the FIRST
  ^FAIL/^ERROR marker line then wins (test identity - "test name + first
  error line"); marker-less generic commands fall back to the last
  remaining non-empty line. This keeps signatures stable when only a
  runner's summary counts vary between otherwise identical failures.
- error_excerpt: merged output tail, bounded to MAX_EXCERPT_CHARS
- diagnosis: the S9 environment skill classifies the merged output first;
  a match records an environment diagnosis ("tool missing", "wrong cwd",
  ...) instead of generic storage. Unclassified output keeps the honest
  placeholder naming exit code and command - never a fabricated
  diagnosis. Teacher review turns either into real lore.

A zero-exit run writes nothing to the store, but (S8) counts one pass
for each existing case keyed by this command via the flaky skill; a
stats failure there warns without masking the child's exit code. Hang
policy (explicit decision, docs/DECISIONS.md): no timeout is enforced;
a hung child hangs the wrapper, exactly like running the command by hand.
"""

import os
import re
import subprocess

from .. import signatures, store
from . import environment, flaky

GUARD_ENV = "QA_RUN_ACTIVE"
CONFIRMED_BY = "auto-capture"
MAX_EXCERPT_CHARS = 4000
NO_OUTPUT_PLACEHOLDER = "(no output)"

_SUMMARY_LINE = re.compile(r"^(?:OK|FAILED|Ran [0-9]+)")
_ERROR_MARKER = re.compile(r"^(?:FAIL|ERROR):?\s")


def execute(cmd):
    """Run cmd as an argv list with the recursion guard set for children."""
    env = dict(os.environ)
    env[GUARD_ENV] = "1"
    return subprocess.run(
        cmd,
        shell=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
    )


def _error_part(output_text):
    """Hybrid D-0007 Amendment 1 rule -> error-part string. Pure."""
    lines = [line.strip() for line in output_text.splitlines() if line.strip()]
    eligible = [line for line in lines if not _SUMMARY_LINE.match(line)]
    for line in eligible:
        if _ERROR_MARKER.match(line):
            return line
    return eligible[-1] if eligible else NO_OUTPUT_PLACEHOLDER


def parse_failure(argv_text, output_text):
    """Deterministic parse rule -> (signature, excerpt). Pure."""
    truncated = len(output_text) > MAX_EXCERPT_CHARS
    excerpt = ("[truncated] " if truncated else "") + output_text[
        -MAX_EXCERPT_CHARS:
    ]
    signature = signatures.canonical(f"{argv_text} :: {_error_part(output_text)}")
    return signature, excerpt


def build_diagnosis(argv_text, returncode):
    return (
        f"auto-captured failure (exit {returncode}) from `{argv_text}`; "
        "diagnosis pending teacher review"
    )


def run_wrapped(cmd):
    """Execute cmd; on failure record one case, on success count passes.

    Returns {"returncode", "output_text", "recorded", "record_error",
    "passed", "pass_error"}: recorded is None on success, record_error
    carries a store-failure message, passed lists the cases that counted
    a pass (S8), pass_error a flaky-stats failure. The child's exit code
    is never masked by a recording problem; callers surface the errors
    without changing the returned code.
    """
    completed = execute(cmd)
    output_text = (completed.stdout or b"").decode("utf-8", errors="replace")
    recorded = None
    record_error = None
    passed = []
    pass_error = None
    if completed.returncode != 0:
        argv_text = " ".join(cmd)
        signature, excerpt = parse_failure(argv_text, output_text)
        diagnosis = (
            environment.diagnose(output_text)
            or build_diagnosis(argv_text, completed.returncode)
        )
        try:
            case, created = store.CaseStore().record(
                signature=signature,
                error_excerpt=excerpt,
                diagnosis=diagnosis,
                by=CONFIRMED_BY,
            )
        except ValueError as exc:
            record_error = str(exc)
        else:
            recorded = {
                "case": case,
                "created": created,
                "signature": signature,
                "excerpt": excerpt,
            }
    else:
        try:
            passed = flaky.FlakeStore().observe_command_pass(" ".join(cmd))
        except ValueError as exc:
            pass_error = str(exc)
    return {
        "returncode": completed.returncode,
        "output_text": output_text,
        "recorded": recorded,
        "record_error": record_error,
        "passed": passed,
        "pass_error": pass_error,
    }
