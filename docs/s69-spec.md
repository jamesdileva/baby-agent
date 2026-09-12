# S69 — Protocol Consistency (gen-4 corpus fixes)

Status: scoped 2026-09-12. Roadmap continuation after the gen-3
verdict. The gen-3 trajectory analysis named three corpus artifacts
that INDUCED model failures; this sprint fixes the data format at the
source so gen-4 trains on a protocol that is self-consistent end to
end.

## The three fixes

### 1. Quote-free test commands

The corpus's `run_tests` commands embed the quoted interpreter path
(`"C:\...\python.exe" -m unittest`) — but the taught textual protocol
forbids quotes inside values, so every gen-3 run opened with mangled
`command="\\"` calls. Fix: `_tests_command` emits the unquoted path
(no spaces here) or falls back to `python -m unittest -v` when the
interpreter path contains spaces. The benchmark's own verifier keeps
its quoting — it is not model-visible.

### 2. One escaping dialect: render == parse

`format_tool_call` renders values JSON-style (backslashes doubled,
quotes escaped, real newlines inside values) while the runtime parser
(`_parse_textual_tool_calls`) captures RAW bytes between quotes — the
corpus taught the model to write calls whose args parse WRONG (the
doubled-backslash paths that file-not-found'd all through gen-3).
Fix: define the escaping ONCE —
- render: backslash → `\\`, quote → `\"`, newline → `\n`, then wrap in
  quotes;
- parse: unescape the same set after capture.
Multi-line `write_file` content becomes expressible (`\n` sequences),
the renderer and parser agree by construction, and a round-trip test
pins render(parse(x)) == x for adversarial values.

### 3. No provenance suffixes in training goals

The S63 session-unique goal suffix (` (benchmark run <id>)`) is store
provenance, not task semantics — but it rode into the chat records and
gen-3's fabricated finals parroted "benchmark run 6bd97c9c" back at
us. Fix: `training.py` strips the suffix when building chat records.

## Corpus invalidation (the rebuild must notice)

The demos CHANGE but their goals do not — the idempotent rebuild would
skip everything. Fix: demos are tagged `corpus-v3`; `build_corpus`
skips only goals covered by a CURRENT-VERSION record, and
`mark_superseded_demos` also supersedes scripted demos lacking the
current version tag (their FORMAT is stale for training; they stay in
the store for provenance). A gen-4 rebuild therefore re-demos all 96
tasks in the new format (~1 minute) and the training export comes out
100% current-version.

## Deliberately deferred

- ep0.5 stays opt-in and net-negative-flagged (the gen-3 A/B showed
  demo injection induces final-answer imitation at this model scale);
  the A/B dimension keeps watching per generation.
- Parser hardening for pathological model output (quote-matching
  heuristics) — the corpus now teaches expressible calls; robustness
  work only if gen-4's trajectories show residual mangling.

## Verification

- Round-trip test: render → parse → identical args for values with
  backslashes, quotes, and newlines.
- Every gen-4 corpus record: quote-free commands (assert no `"` in any
  run_tests arg), current-version tag, first-step discovery unchanged.
- Live: rebuild → training export → the human's Colab job → ep4 →
  `qa verdict` against ep3/ep2 with the same metric table.
