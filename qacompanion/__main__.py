"""argv dispatch -> subcommand modules; exit-code policy.

0 success, 1 operational failure (bad input, unreadable/corrupt store).
Modules stay silent; all output lives here.
"""

import argparse
import os
import sys

from . import accuracy as accuracy_mod
from . import lookup as lookup_mod
from . import report as report_mod
from . import signatures
from . import store
from . import transport
from .skills import auto_capture, flaky


def build_parser():
    parser = argparse.ArgumentParser(
        prog="qacompanion",
        description="Accumulate test-failure cases; recognize recurring ones.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    record = sub.add_parser("record", help="add or bump a failure case")
    record.add_argument("--sig", required=True, help="normalized failure fingerprint")
    record.add_argument("--err", required=True, help="error excerpt")
    record.add_argument("--diag", required=True, help="diagnosis text")
    record.add_argument("--by", default=None, help="who confirmed this diagnosis")

    lookup = sub.add_parser("lookup", help="find the stored diagnosis for a signature")
    lookup.add_argument("--sig", required=True, help="normalized failure fingerprint")

    sub.add_parser("report", help="summarize the case base")

    sub.add_parser(
        "flakes",
        help="pass-after-fail stats; chronic flakes listed separately",
    )

    sub.add_parser("accuracy", help="score recall against the frozen holdout")

    exporter = sub.add_parser("export", help="atomic copy of the case base")
    exporter.add_argument("--out", required=True, help="destination path for the copy")

    importer = sub.add_parser(
        "import", help="validate a case file, then atomically replace the store"
    )
    importer.add_argument(
        "--in", dest="infile", required=True, help="cases.jsonl-format file to import"
    )
    importer.add_argument(
        "--merge",
        action="store_true",
        help="fold duplicate signatures into existing cases (bumps times_seen)",
    )

    runner = sub.add_parser(
        "run",
        help="wrap a command; auto-record its failure on nonzero exit",
        epilog=(
            "Hang policy (explicit decision, docs/DECISIONS.md): no timeout "
            "is enforced; a hung child hangs this wrapper. The child's "
            "merged stdout+stderr is echoed verbatim to stderr. Nested "
            "'qa run' invocations are refused."
        ),
    )
    runner.add_argument(
        "cmd",
        nargs=argparse.REMAINDER,
        metavar="-- CMD [ARGS ...]",
        help="command to wrap, passed as an argv list (no shell)",
    )

    return parser


def _cmd_record(args):
    try:
        case, created = store.CaseStore().record(
            signature=signatures.canonical(args.sig),
            error_excerpt=args.err,
            diagnosis=args.diag,
            by=args.by,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    verb = "recorded new case" if created else "bumped case"
    print(f"{verb} #{case['id']} times_seen={case['times_seen']}")
    return 0


def _cmd_lookup(args):
    try:
        cases = store.CaseStore().load()
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    query = signatures.canonical(args.sig)
    print(lookup_mod.format_matches(lookup_mod.select(cases, query)))
    return 0


def _cmd_report(args):
    try:
        cases = store.CaseStore().load()
        sections = [report_mod.format_report(cases), report_mod.accuracy_line(cases)]
        if flaky.has_entries():
            entries = flaky.FlakeStore().load()
            sections.append(flaky.format_flakes(cases, entries))
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print("\n".join(sections))
    return 0


def _cmd_flakes(args):
    try:
        cases = store.CaseStore().load()
        entries = flaky.FlakeStore().load()
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(flaky.format_flakes(cases, entries))
    return 0


def _cmd_accuracy(args):
    try:
        cases = store.CaseStore().load()
        entries = accuracy_mod.load_holdout()
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    hits, total = accuracy_mod.replay(cases, entries)
    print(accuracy_mod.format_accuracy(hits, total))
    return 0


def _cmd_export(args):
    try:
        count = transport.export_cases(store.CaseStore(), args.out)
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"exported {count} case(s) -> {args.out}")
    return 0


def _cmd_import(args):
    try:
        added, merged, total = transport.import_cases(
            store.CaseStore(), args.infile, merge=args.merge
        )
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"imported {added} new case(s), merged {merged}; store holds {total}")
    return 0


def _cmd_run(args):
    cmd = list(args.cmd)
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]
    if not cmd:
        print("error: run requires a command after '--'", file=sys.stderr)
        return 1
    if os.environ.get(auto_capture.GUARD_ENV) == "1":
        print("error: nested 'qa run' refused (recursion guard)", file=sys.stderr)
        return 1
    try:
        result = auto_capture.run_wrapped(cmd)
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    sys.stderr.write(result["output_text"])
    sys.stderr.flush()
    if result["record_error"]:
        print(
            f"warning: auto-record failed ({result['record_error']})",
            file=sys.stderr,
        )
        return result["returncode"]
    if result["pass_error"]:
        print(
            f"warning: pass counting failed ({result['pass_error']})",
            file=sys.stderr,
        )
    for row in result["passed"]:
        print(f"pass counted case #{row['id']} times_passed={row['times_passed']}")
    recorded = result["recorded"]
    if recorded is None:
        return result["returncode"]
    case = recorded["case"]
    verb = "auto-recorded new case" if recorded["created"] else "auto-bumped case"
    print(
        f"{verb} #{case['id']} times_seen={case['times_seen']} "
        f"exit={result['returncode']}"
    )
    return result["returncode"]


_COMMANDS = {
    "record": _cmd_record,
    "lookup": _cmd_lookup,
    "report": _cmd_report,
    "flakes": _cmd_flakes,
    "accuracy": _cmd_accuracy,
    "export": _cmd_export,
    "import": _cmd_import,
    "run": _cmd_run,
}


def main(argv=None):
    args = build_parser().parse_args(argv)
    return _COMMANDS[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
