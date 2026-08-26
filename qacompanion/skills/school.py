"""S22 school mode: interactive session walking recent unconfirmed diagnoses.

Born from "formalize the teacher loop into a repeatable ritual." Walks
pending (unconfirmed) cases one by one, letting the parent confirm,
correct, or create a new case in one pass. Ledger and case base are
updated atomically.

Pins (fixtures-first discipline):
- pending = cases where confirmed_by is "unknown";
- session processes up to N cases (default: all pending);
- confirm sets confirmed_by to the supplied name;
- correct updates diagnosis and confirmed_by atomically;
- new case creation appends to the store during the session;
- all writes are atomic (CaseStore.save);
- exit 0 session completed, 1 operational error, 2 env error.

Exit contract (proposed spec amendment):
0 session completed, 1 operational error, 2 environment error.
"""

import sys
from pathlib import Path

from .. import store
from . import journal


class SchoolError(Exception):
    """Operational failure in the school session."""


def get_pending_cases(cases):
    """Return cases where confirmed_by is 'unknown' (pending review)."""
    return [c for c in cases if c.get("confirmed_by") == "unknown"]


def confirm_case(case, by):
    """Mark a case as confirmed. Returns updated case dict."""
    case["confirmed_by"] = by
    return case


def correct_case(case, by, new_diagnosis):
    """Update a case's diagnosis and confirm it. Returns updated case dict."""
    case["diagnosis"] = new_diagnosis
    case["confirmed_by"] = by
    return case


def format_case(case, index, total):
    """Render a case for interactive display."""
    lines = [
        f"--- Case #{case['id']} ({index}/{total}) ---",
        f"  signature: {case['signature'][:80]}{'...' if len(case['signature']) > 80 else ''}",
        f"  error: {case['error_excerpt'][:120]}{'...' if len(case['error_excerpt']) > 120 else ''}",
        f"  diagnosis: {case['diagnosis']}",
        f"  times_seen: {case['times_seen']}",
        f"  confirmed_by: {case['confirmed_by']}",
    ]
    return "\n".join(lines)


def format_session_summary(processed, confirmed, corrected, created):
    """Render the session summary."""
    parts = [f"school session complete: {processed} case(s) processed"]
    if confirmed:
        parts.append(f"  confirmed: {confirmed}")
    if corrected:
        parts.append(f"  corrected: {corrected}")
    if created:
        parts.append(f"  new cases created: {created}")
    return "\n".join(parts)


def run_session(cs, by, limit=None, stdin=None, ledger=None):
    """Run an interactive school session.

    Args:
        cs: CaseStore instance.
        by: name of the confirmer (e.g., 'human', 'agent-a').
        limit: max cases to process (None = all pending).
        stdin: file-like for input (defaults to sys.stdin).
        ledger: optional journal ledger path for logging.

    Returns:
        dict with counts: processed, confirmed, corrected, created.
    """
    if stdin is None:
        stdin = sys.stdin

    cases = cs.load()
    pending = get_pending_cases(cases)

    if limit is not None:
        pending = pending[:limit]

    if not pending:
        return {"processed": 0, "confirmed": 0, "corrected": 0, "created": 0}

    processed = 0
    confirmed = 0
    corrected = 0
    created = 0
    total = len(pending)

    for i, case in enumerate(pending, 1):
        print(format_case(case, i, total))
        print()
        print("Options: [c]onfirm, [e]dit diagnosis, [s]kip, [n]ew case, [q]uit")
        print("> ", end="", flush=True)

        choice = stdin.readline().strip().lower()

        if choice == "c":
            case["confirmed_by"] = by
            confirmed += 1
            processed += 1
            print(f"  -> confirmed case #{case['id']}\n")
        elif choice == "e":
            print("  New diagnosis: ", end="", flush=True)
            new_diag = stdin.readline().strip()
            if new_diag:
                case["diagnosis"] = new_diag
                case["confirmed_by"] = by
                corrected += 1
                processed += 1
                print(f"  -> corrected case #{case['id']}\n")
            else:
                print("  -> skipped (empty diagnosis)\n")
        elif choice == "n":
            print("  Signature: ", end="", flush=True)
            sig = stdin.readline().strip()
            print("  Error excerpt: ", end="", flush=True)
            err = stdin.readline().strip()
            print("  Diagnosis: ", end="", flush=True)
            diag = stdin.readline().strip()
            if sig and err and diag:
                from .. import signatures as sig_mod
                from ..store import utc_now_stamp
                next_id = cases[-1]["id"] + 1 if cases else 1
                new_case = {
                    "id": next_id,
                    "signature": sig_mod.canonical(sig),
                    "error_excerpt": err,
                    "diagnosis": diag,
                    "times_seen": 1,
                    "last_seen": utc_now_stamp(),
                    "confirmed_by": by,
                }
                cases.append(new_case)
                created += 1
                processed += 1
                print(f"  -> created case #{new_case['id']}\n")
            else:
                print("  -> skipped (incomplete fields)\n")
        elif choice == "q":
            print("  -> quitting session\n")
            break
        else:
            print(f"  -> skipped (unrecognized: '{choice}')\n")

    # Persist all case modifications atomically
    if processed > 0:
        cs.save(cases)

    # Log to journal if ledger specified
    if ledger and processed > 0:
        summary = f"school: {processed} cases processed, {confirmed} confirmed, {corrected} corrected, {created} new"
        try:
            journal.add(summary, ledger=ledger)
        except journal.JournalError:
            pass  # journal logging is best-effort

    return {
        "processed": processed,
        "confirmed": confirmed,
        "corrected": corrected,
        "created": created,
    }
