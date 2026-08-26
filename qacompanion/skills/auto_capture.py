"""S7 auto-capture hook: wrap a command, auto-record its failure.

`qa run -- <cmd>` executes <cmd> as an argv list (never through a shell),
echoes the child's merged stdout+stderr verbatim to qacompanion's stderr
(nothing swallowed - the FAIL(0.0s) lesson), and on nonzero exit records
exactly one case:

- signature: normalized command line + last non-empty output line
  (the generic-command adaptation of "test name + first error line")
- error_excerpt: merged output tail, bounded to MAX_EXCERPT_CHARS
- diagnosis: honest placeholder naming exit code and command; never a
  fabricated diagnosis. Teacher review turns it into real lore.

A zero-exit run writes nothing to the store. Hang policy (explicit
decision, docs/DECISIONS.md): no timeout is enforced; a hung child hangs
the wrapper, exactly like running the command by hand.
"""

import os
import subprocess

from .. import signatures, store

GUARD_ENV = "QA_RUN_ACTIVE"
CONFIRMED_BY = "auto-capture"
MAX_EXCERPT_CHARS = 4000
NO_OUTPUT_PLACEHOLDER = "(no output)"


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


def parse_failure(argv_text, output_text):
    """Deterministic parse rule -> (signature, excerpt). Pure."""
    non_empty = [line.strip() for line in output_text.splitlines() if line.strip()]
    last_line = non_empty[-1] if non_empty else NO_OUTPUT_PLACEHOLDER
    truncated = len(output_text) > MAX_EXCERPT_CHARS
    excerpt = ("[truncated] " if truncated else "") + output_text[
        -MAX_EXCERPT_CHARS:
    ]
    signature = signatures.canonical(f"{argv_text} :: {last_line}")
    return signature, excerpt


def build_diagnosis(argv_text, returncode):
    return (
        f"auto-captured failure (exit {returncode}) from `{argv_text}`; "
        "diagnosis pending teacher review"
    )


def run_wrapped(cmd):
    """Execute cmd and, on failure, record one case.

    Returns {"returncode", "output_text", "recorded", "record_error"}:
    recorded is None on success, record_error carries a store-failure
    message. The child's exit code is never masked by a recording problem;
    callers surface record_error without changing the returned code.
    """
    completed = execute(cmd)
    output_text = (completed.stdout or b"").decode("utf-8", errors="replace")
    recorded = None
    record_error = None
    if completed.returncode != 0:
        argv_text = " ".join(cmd)
        signature, excerpt = parse_failure(argv_text, output_text)
        try:
            case, created = store.CaseStore().record(
                signature=signature,
                error_excerpt=excerpt,
                diagnosis=build_diagnosis(argv_text, completed.returncode),
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
    return {
        "returncode": completed.returncode,
        "output_text": output_text,
        "recorded": recorded,
        "record_error": record_error,
    }
