"""argv dispatch -> subcommand modules; exit-code policy.

0 success, 1 operational failure (bad input, unreadable/corrupt store);
preflight, locate and snapshot add 2 environment error (proposed
amendment, docs/DECISIONS.md). Modules stay silent; all output lives here.
"""

import argparse
import os
import sys
from pathlib import Path

from . import accuracy as accuracy_mod
from . import lookup as lookup_mod
from . import report as report_mod
from . import signatures
from . import store
from . import task
from . import teach as teach_mod
from . import transport
from .skills import archive_mine, auto_capture, digest, flaky, journal, locate, merge, preflight, regression, repocheck, school, snapshot


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

    checker = sub.add_parser(
        "preflight",
        help="run the colony QA checklist (R3 sha256 order, BOMs, clean tree)",
        epilog=(
            "Exit contract (proposed amendment, docs/DECISIONS.md): "
            "0 all checked rules pass, 1 rule violation found, 2 "
            "environment error (not a git work tree / git missing / "
            "unreadable transcript)."
        ),
    )
    checker.add_argument(
        "--transcript",
        default=None,
        help=(
            "transcript text file for the R3 sha256-ordering check "
            "(omitting it skips that rule honestly)"
        ),
    )

    finder = sub.add_parser(
        "locate",
        help="find repos by name fragment or commit-hash prefix",
        epilog=(
            "Walks common project roots (override with repeatable "
            "--root), depth 3, matching repo names or the 20 most "
            "recent commit hashes. Exit contract (proposed amendment, "
            "docs/DECISIONS.md): 0 match found, 1 no match / bad root, "
            "2 environment error (git unusable)."
        ),
    )
    finder.add_argument("query", help="name fragment or >=7-char hex hash prefix")
    finder.add_argument(
        "--root",
        action="append",
        default=None,
        dest="roots",
        metavar="DIR",
        help="search this directory instead of the defaults (repeatable)",
    )

    snapper = sub.add_parser(
        "snapshot",
        help="timestamped archive of a directory plus MANIFEST.json",
        epilog=(
            "Copies SOURCE whole into ARCHIVES (default ./archives) "
            "under a UTC stamp, then writes MANIFEST.json (relative "
            "paths, sizes, SHA256s, source path) and re-verifies every "
            "hash. Refuses to overwrite an existing stamp. Exit "
            "contract (proposed amendment, docs/DECISIONS.md): 0 "
            "created+verified, 1 bad source/label or stamp collision, "
            "2 environment error."
        ),
    )
    snapper.add_argument("source", help="directory to archive")
    snapper.add_argument(
        "--archives",
        default="archives",
        metavar="DIR",
        help="archives folder for the stamped copy (default: archives)",
    )
    snapper.add_argument(
        "--label",
        default=None,
        help=(
            "stamp prefix ('<label>-<utcstamp>'); no '/', '\\', ':' "
            "or dot components"
        ),
    )

    checker = sub.add_parser(
        "repocheck",
        help="multi-repo health report (dirty, ahead, missing remote)",
        epilog=(
            "Scans a directory for git repos and reports per repo: dirty "
            "files, commits ahead of upstream, missing remotes. Exit "
            "contract (proposed amendment, docs/DECISIONS.md): 0 all "
            "clean, 1 issues found, 2 environment error."
        ),
    )
    checker.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="parent directory to scan (default: cwd)",
    )

    journ = sub.add_parser(
        "journal",
        help="durable lessons ledger (append-only, searchable)",
        epilog=(
            "Append-only markdown ledger with auto-timestamped entries. "
            "Subcommands: add <text> appends an entry, grep <pattern> "
            "searches entries. Exit contract: 0 success, 1 operational "
            "failure."
        ),
    )
    journ.add_argument(
        "action",
        choices=["add", "grep"],
        help="add: append entry; grep: search entries",
    )
    journ.add_argument(
        "text",
        nargs="?",
        default=None,
        help="entry text (add) or search pattern (grep)",
    )
    journ.add_argument(
        "--ledger",
        default=None,
        metavar="FILE",
        help="ledger file path (default: JOURNAL.md in cwd)",
    )

    teacher = sub.add_parser(
        "teach",
        help="add a rule to the skill registry",
        epilog=(
            "Validates a JSON rule and appends it to a pack file "
            "(default: skills/taught.json). The pack is re-validated "
            "after each write. Exit contract: 0 rule accepted, "
            "1 validation error, 2 I/O error."
        ),
    )
    teacher.add_argument(
        "--rule",
        required=True,
        help="JSON rule object (pattern, classification, diagnosis_hint, ...)",
    )
    teacher.add_argument(
        "--pack",
        default=teach_mod.DEFAULT_PACK,
        metavar="PATH",
        help=f"pack file to write (default: {teach_mod.DEFAULT_PACK})",
    )

    merger = sub.add_parser(
        "merge",
        help="merge near-duplicate cases (dedup tool)",
        epilog=(
            "Merge case B into case A: combined times_seen, B removed, "
            "merged-from note added to A. Exit contract: 0 success, "
            "1 operational error (bad IDs, same case)."
        ),
    )
    merger.add_argument("--into", required=True, type=int, dest="into_id", help="target case ID (keeps signature/diagnosis)")
    merger.add_argument("--from", required=True, type=int, dest="from_id", help="source case ID (absorbed and removed)")

    digester = sub.add_parser(
        "digest",
        help="ingest markdown documents into the knowledge base",
        epilog=(
            "Walk a directory, parse .md files into sections, store them "
            "as retrievable entries. Re-digest updates existing entries "
            "(dedup by content hash). Exit contract: 0 success, "
            "1 operational error."
        ),
    )
    digester.add_argument("directory", help="directory of markdown files to ingest")
    digester.add_argument(
        "--store",
        default=None,
        metavar="PATH",
        help="digest store file (default: digest.jsonl)",
    )

    asker = sub.add_parser(
        "ask",
        help="search digested documents for a query",
        epilog=(
            "Search digest entries by case-insensitive keywords. Returns "
            "cited passages from ingested markdown. Exit contract: 0 "
            "matches found, 1 no matches."
        ),
    )
    asker.add_argument("query", help="search keywords")
    asker.add_argument(
        "--store",
        default=None,
        metavar="PATH",
        help="digest store file (default: digest.jsonl)",
    )

    miner = sub.add_parser(
        "mine",
        help="mine archives, git logs, and transcripts into cases",
        epilog=(
            "Digest DECISIONS.md files, git logs, and failure transcripts "
            "into importable cases. Known lore (FAIL(0.0s), BOM, stale-"
            "installer) is retrievable via lookup after mining. Exit "
            "contract: 0 success, 1 operational error."
        ),
    )
    miner.add_argument("directory", help="root directory to scan for sources")
    miner.add_argument(
        "--out",
        required=True,
        metavar="PATH",
        help="output file for mined cases (cases.jsonl format)",
    )
    miner.add_argument(
        "--sources",
        action="append",
        default=None,
        dest="sources",
        choices=["decisions", "git", "transcripts"],
        help="source types to mine (repeatable; default: all)",
    )

    schooler = sub.add_parser(
        "school",
        help="interactive session walking unconfirmed diagnoses",
        epilog=(
            "Walks pending (unconfirmed) cases, letting the parent "
            "confirm, correct, or create new cases in one pass. Exit "
            "contract: 0 session completed, 1 operational error."
        ),
    )
    schooler.add_argument(
        "--by",
        required=True,
        help="who is confirming (e.g., 'human', 'agent-a')",
    )
    schooler.add_argument(
        "--limit",
        type=int,
        default=None,
        help="max cases to process (default: all pending)",
    )
    schooler.add_argument(
        "--cases",
        default=None,
        metavar="PATH",
        help="cases store file (default: cases.jsonl)",
    )
    schooler.add_argument(
        "--ledger",
        default=None,
        metavar="PATH",
        help="journal ledger for session logging (default: none)",
    )

    tasklite = sub.add_parser(
        "tasklite",
        help="minimal task tracker (capstone project)",
        epilog=(
            "Subcommands: add <title>, list, done <id>, delete <id>, "
            "show <id>. Exit contract: 0 success, 1 operational failure."
        ),
    )
    tasklite.add_argument(
        "action",
        choices=["add", "list", "done", "delete", "show"],
        help="task action to perform",
    )
    tasklite.add_argument(
        "target",
        nargs="?",
        default=None,
        help="title (add) or task id (done/delete/show)",
    )
    tasklite.add_argument(
        "--file",
        default=None,
        metavar="PATH",
        help="tasks store file (default: tasks.jsonl)",
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
            sections.append(regression.format_regressions(cases, entries))
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


def _cmd_preflight(args):
    transcript_text = None
    if args.transcript:
        try:
            transcript_text = Path(args.transcript).read_text(encoding="utf-8-sig")
        except OSError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
    try:
        results = preflight.run_checks(Path.cwd(), transcript_text)
    except preflight.PreflightEnvError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(preflight.format_results(results))
    return 1 if any(r["status"] == "FAIL" for r in results) else 0


def _cmd_locate(args):
    if args.roots:
        roots = []
        for raw in args.roots:
            root = Path(raw)
            if not root.is_dir():
                print(f"error: root does not exist: {root}", file=sys.stderr)
                return 1
            roots.append(root)
    else:
        roots = locate.default_roots()
    try:
        results = locate.search(args.query, roots)
    except locate.LocateEnvError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(locate.render(results, args.query))
    return 0 if results["matches"] else 1


def _cmd_snapshot(args):
    try:
        results = snapshot.create_snapshot(
            args.source, args.archives, label=args.label
        )
    except snapshot.SnapshotError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(snapshot.render(results))
    return 0


def _cmd_repocheck(args):
    directory = Path(args.directory)
    if not directory.is_dir():
        print(f"error: {directory} is not a directory", file=sys.stderr)
        return 2
    try:
        results = repocheck.scan([directory])
    except repocheck.RepocheckEnvError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(repocheck.render(results, str(directory.resolve())))
    issues = (
        len(results["repos_dirty"])
        + len(results["repos_ahead"])
        + len(results["repos_missing_remote"])
    )
    return 1 if issues > 0 else 0


def _cmd_journal(args):
    if not args.text:
        print("error: journal requires text argument (entry or pattern)", file=sys.stderr)
        return 1
    try:
        if args.action == "add":
            entry = journal.add(args.text, ledger=args.ledger)
            print(journal.render_add(entry))
            return 0
        else:
            results = journal.grep(args.text, ledger=args.ledger)
            print(journal.render_grep(results, args.text))
            return 0 if results else 1
    except journal.JournalError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _cmd_teach(args):
    import json as json_mod
    try:
        rule_dict = json_mod.loads(args.rule)
    except json_mod.JSONDecodeError as exc:
        print(f"error: invalid JSON: {exc}", file=sys.stderr)
        return 1
    pack_path = Path(args.pack)
    created = not pack_path.exists()
    try:
        teach_mod.teach_rule(rule_dict, pack_path)
    except teach_mod.RegistryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(teach_mod.render_teach(rule_dict, pack_path, created=created))
    return 0


def _cmd_merge(args):
    try:
        result = merge.merge(store.CaseStore(), args.into_id, args.from_id)
    except merge.MergeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(merge.format_merge(result))
    return 0


def _cmd_digest(args):
    try:
        results = digest.digest_directory(args.directory, args.store)
    except digest.DigestError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    for path, err in results["errors"]:
        print(f"warning: {path}: {err}", file=sys.stderr)
    print(
        f"digested {results['files_scanned']} file(s): "
        f"{results['entries_added']} added, "
        f"{results['entries_updated']} updated"
    )
    return 0


def _cmd_ask(args):
    results = digest.search(args.query, args.store)
    print(format_results_ask(results, args.query))
    return 0 if results else 1


def format_results_ask(results, query):
    """Render ask results as human-readable cited output."""
    return digest.format_results(results, query)


def _cmd_mine(args):
    try:
        results = archive_mine.mine_directory(args.directory, args.sources)
    except archive_mine.MineError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    for path, err in results["errors"]:
        print(f"warning: {path}: {err}", file=sys.stderr)
    count = archive_mine.export_mined(results["cases"], args.out)
    print(archive_mine.format_results(results))
    return 0


def _cmd_school(args):
    cs = store.CaseStore(args.cases)
    try:
        result = school.run_session(
            cs,
            by=args.by,
            limit=args.limit,
            ledger=args.ledger,
        )
    except school.SchoolError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(school.format_session_summary(
        result["processed"],
        result["confirmed"],
        result["corrected"],
        result["created"],
    ))
    return 0


def _cmd_tasklite(args):
    ts = task.TaskStore(args.file)
    try:
        if args.action == "add":
            if not args.target:
                print("error: add requires a title", file=sys.stderr)
                return 1
            t = ts.add(args.target)
            print(f"created task #{t['id']} {t['title']}")
            return 0
        elif args.action == "list":
            tasks = ts.list_all()
            if not tasks:
                print("(no tasks)")
            for t in tasks:
                print(f"#{t['id']} [{t['status']}] {t['title']}")
            return 0
        elif args.action == "done":
            if args.target is None:
                print("error: done requires a task id", file=sys.stderr)
                return 1
            try:
                tid = int(args.target)
            except ValueError:
                print(f"error: invalid task id: {args.target}", file=sys.stderr)
                return 1
            try:
                t = ts.mark_done(tid)
            except ValueError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 1
            print(f"done #{t['id']} {t['title']}")
            return 0
        elif args.action == "delete":
            if args.target is None:
                print("error: delete requires a task id", file=sys.stderr)
                return 1
            try:
                tid = int(args.target)
            except ValueError:
                print(f"error: invalid task id: {args.target}", file=sys.stderr)
                return 1
            try:
                ts.delete(tid)
            except ValueError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 1
            print(f"deleted task #{tid}")
            return 0
        elif args.action == "show":
            if args.target is None:
                print("error: show requires a task id", file=sys.stderr)
                return 1
            try:
                tid = int(args.target)
            except ValueError:
                print(f"error: invalid task id: {args.target}", file=sys.stderr)
                return 1
            try:
                t = ts.show(tid)
            except ValueError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 1
            import json as json_mod
            print(json_mod.dumps(t, indent=2))
            return 0
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


_COMMANDS = {
    "record": _cmd_record,
    "lookup": _cmd_lookup,
    "report": _cmd_report,
    "flakes": _cmd_flakes,
    "accuracy": _cmd_accuracy,
    "export": _cmd_export,
    "import": _cmd_import,
    "run": _cmd_run,
    "preflight": _cmd_preflight,
    "locate": _cmd_locate,
    "snapshot": _cmd_snapshot,
    "repocheck": _cmd_repocheck,
    "journal": _cmd_journal,
    "teach": _cmd_teach,
    "merge": _cmd_merge,
    "digest": _cmd_digest,
    "ask": _cmd_ask,
    "mine": _cmd_mine,
    "school": _cmd_school,
    "tasklite": _cmd_tasklite,
}


def main(argv=None):
    args = build_parser().parse_args(argv)
    return _COMMANDS[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
