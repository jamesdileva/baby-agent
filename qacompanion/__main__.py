"""argv dispatch -> subcommand modules; exit-code policy.

0 success, 1 operational failure (bad input, unreadable/corrupt store).
Modules stay silent; all output lives here.
"""

import argparse
import sys

from . import accuracy as accuracy_mod
from . import lookup as lookup_mod
from . import report as report_mod
from . import signatures
from . import store


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

    sub.add_parser("accuracy", help="score recall against the frozen holdout")

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
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(report_mod.format_report(cases))
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


_COMMANDS = {
    "record": _cmd_record,
    "lookup": _cmd_lookup,
    "report": _cmd_report,
    "accuracy": _cmd_accuracy,
}


def main(argv=None):
    args = build_parser().parse_args(argv)
    return _COMMANDS[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
