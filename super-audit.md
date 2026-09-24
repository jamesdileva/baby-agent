# super-audit.md — baby-agent independent audit (code quality / tool-calling / skills / curriculum)

**Date:** 2026-09-24
**Scope:** code quality, logical bugs, robustness; tool-calling execution and token parsing;
state management and reliability of skills; algorithmic thresholds and data-gating in the
curriculum/curation/training pipeline.
**Method:** read current source under `qacompanion/agent/`, re-checked every claim from
`docs/claude-audit.md` (F1–F18) and `docs/gpt-audit.md` (G1–G27) against the present code,
and dug for the structural root causes both reports missed.
**Out of scope (per task):** pure security/vulnerability findings are validated in the ledger
but not developed, unless they directly cause an execution or data-integrity bug.

## Slice tracker (super-audit workthrough, §F order)

- [x] S1 — A1 + F16 gate: five typing imports, annotation-resolution test, CI matrix
- [x] S2 — B1 + B2: textual parser hardening + renderer round-trip ✅
- [x] S3 — C2 + C3: curation→skills handoff + `from_dict` guards ✅
- [x] S4 — D7(G3): apprenticeship lesson delivery ✅
- [x] S5 — D1(level) + D3 + D4.2: measurement trio ✅
- [x] S6 — A3: store concurrency locks + contention tests ✅
- [x] S7 — C1 + D5 (+D4.3): trust boundary + experience identity ✅
  (scoped: confirmation gate + evidence rule landed; composite identity
  + propose/certify split deferred to S7b — needs a DECISION + migration)
- [ ] S8 — A2 + F13 + F14: timeout enforcement + retry + audit bound
- [ ] S9 — F8 + F10 + F15 + F12: boundary correctness batch
- [ ] S10 — B3 + B4: flatten fence + validator/loop accounting
- [ ] S11 — D2 + D6: curriculum/training accounting batch
- [ ] S12 — F17 + F18: test isolation + docs rewrite

Interpreter note: this machine runs Python 3.14.3, where PEP 649/749 defers annotation
evaluation. Missing `typing` names therefore import cleanly here but fail on 3.9–3.13.
That masking is itself part of finding A1.

---

## 0. Validation ledger — do the old findings still exist?

`CONFIRMED` = present in current code at the cited lines. `ARCH` = architectural weakness,
code-confirmed. Security-only items are marked `EXCLUDED` (validated, not developed).

### Claude F1–F18

| ID | Claim | Status today | Evidence |
|---|---|---|---|
| F1 | Missing `typing` names break import on <3.14 | CONFIRMED (5 files) | `providers.py:24` lacks `Optional` used at 87,101,221,353,388; `multi_agent.py:24` lacks `Tuple` used at 116,283; `processes.py:35` lacks `Tuple` used at 81; `websearch.py:30` lacks `Workspace` used at 291; `skills.py:27` lacks `Workspace` used at 232 |
| F2 | `agent_registry()` unconditionally builds Windows-only computer use | CONFIRMED | `fs_tools.py:479-481` constructs `ComputerUseToolkit` unconditionally; `computer.py:247-253` raises on `os.name != "nt"` when no provider injected |
| F3 | Workspace bypass via `run_command` / EXECUTION default | Validated, EXCLUDED (security posture) | `permissions.py:47-53` EXECUTION→ALLOW; execution shell path unchanged |
| F4 | Registry timeout does not bound wall clock | CONFIRMED | `registry.py:361-371` — `future.result(timeout)` + `with ThreadPoolExecutor` → `shutdown(wait=True)` blocks; inner handler keeps running |
| F5 | Redirect chain not revalidated | Validated, EXCLUDED (SSRF) | — |
| F6 | Dashboard no CSRF boundary | Validated, EXCLUDED (CSRF) | — |
| F7 | `CaseStore.record()` read-modify-write race | CONFIRMED | `store.py:131-162` — `load()` → mutate → `save()` whole file, no lock |
| F8 | `Workspace("/")` containment bug | CONFIRMED | `workspace.py:54-56` — `p.startswith(r + os.sep)` fails for root `/` (`"//"`) and drive roots |
| F9 | Gemini key in URL query | Validated, EXCLUDED (secret handling) | `providers.py:103-108,223-228` still interpolates `?key=` |
| F10 | Git scope can exceed workspace | CONFIRMED as correctness bug (kept, §A4) | `workspace.py:59-63` finds parent git root; git tools `cwd=root` without toplevel-vs-root check |
| F11 | No provenance boundary in `_flatten_messages` | Kept as parsing/execution bug (§B3) | `providers.py:271-275` erases `role:` boundary for non-native providers |
| F12 | `curriculum._test_footer` calls unimported `textwrap` | CONFIRMED (dead code) | `curriculum.py:23` imports `random, re` only; `curriculum.py:48-54` calls `textwrap.dedent` |
| F13 | Blocking 60s provider retry sleep | CONFIRMED | `providers.py:125,247` — `time.sleep(60.0)` in request path, ignores cancel event / Retry-After |
| F14 | Duplicate `ALLOW_ALL_POLICY` + unbounded growth | CONFIRMED | `registry.py:112-125` minimal policy + `registry.py:125` singleton vs `permissions.py:114-179` engine + `permissions.py:179` singleton; `permissions.py:134-135` appends to `decisions` unbounded |
| F15 | `args_contains` substring matching | CONFIRMED as logic bug (§A4) | `permissions.py:82-87` — case-insensitive substring, no shell semantics |
| F16 | No CI/linter/packaging | CONFIRMED | no `.github/`, `pyproject.toml`, `setup.py`; F1/F2/F12 are the receipts |
| F17 | Tests write live store paths | CONFIRMED by design | no `setUpModule` temp-dir isolation; `digest.jsonl` creation previously diffed |
| F18 | Top-level docs describe a different program | CONFIRMED (docs drift) | `ARCHITECTURE.md` "No LLM, no network" vs `agent/` providers/web/browser/vision reality |

### GPT G1–G27 (learning-heavy; security-only rows excluded from development)

CONFIRMED in current code: G1, G2, G3, G4, G5, G6, G7, G8, G9, G10, G11, G12, G18, G19,
G20, G21, G22, G23, G24, G27. ARCH (code-confirmed architecture risk): G13 (kept as
capability-minimization note in §B4), G24. EXCLUDED as pure security (validated, not
developed): G15, G16, G17, G25, G26. G14 is folded into §C1 as a state-mutation
classification bug, not a security claim.

Deeper result: most G-findings are symptoms of four structural root causes (§E) the prior
audits named but did not isolate to exact lines. Several new breakages were also found
that neither audit reported (§B–§D, marked NEW).

---

## A. Core robustness and code quality

### A1. Deferred-annotation masking hides five broken imports (F1, still open)

All five files fail on Python 3.9–3.13 at class/function definition time because annotations
evaluate eagerly there:

- `providers.py:24` vs `Optional` at 87,101,221,353,388
- `multi_agent.py:24` vs `Tuple` at 116,283
- `processes.py:35` vs `Tuple` at 81
- `websearch.py:30` vs `Workspace` at 291
- `skills.py:27` vs `Workspace` at 232

On this repo's 3.14 toolchain everything imports, so the suite stays green while the bug
ships. The prior audits were right about the mechanism; the new observation is that the
fix must be process, not just imports: add the five names AND `python -m pyflakes` (or
`compileall` on 3.12) to CI (F16), otherwise the next missing name hides the same way.

### A2. Registry timeout reports but does not enforce (F4, still open)

`registry.py:361-371`:

```python
with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
    future = pool.submit(tool.handler, **arguments)
    try:
        output = future.result(timeout=tool.timeout_seconds)
    except concurrent.futures.TimeoutError:
        return _Outcome(ok=False, error="timed out ...", timed_out=True)
```

`future.result(timeout)` raises, but the worker thread keeps running, and exiting the
`with` block calls `shutdown(wait=True)`, which blocks until that thread finishes. Wall
time equals handler time, while the result claims `timed_out=True`. The `duration_ms`
measured in `execute()` (`registry.py:256-261`) therefore contradicts the error string,
exactly as the Claude repro showed. The inner S35 subprocess timeout (`proc.communicate`
+ tree-kill) is real, so shell tools are bounded — but any handler that hangs on a socket,
lock, or infinite loop hangs the loop while reporting a timeout. Fix: hoist to a shared
executor (no per-call `shutdown(wait=True)`), or run cancellable work in subprocesses,
and add a wall-clock assertion test (no such test exists today).

### A3. Both JSONL stores have the same unguarded read-modify-write (F7 + NEW sibling)

`CaseStore.record()` (`store.py:131-162`) is `load()` → mutate → `save()` (whole-file
`os.replace`) with no lock — the reported ~60% loss under 50-thread contention is
structurally expected. The audits missed that `ExperienceStore.record()`
(`experience.py:172-190`) is the identical shape with worse semantics (see §D5): concurrent
`record_session` calls from `ThreadingHTTPServer` threads, the watcher daemon, or
multi-agent runs can silently drop whole trajectories. `save()` being atomic does not help;
atomicity of the write is not atomicity of the read-modify-write. Portable stdlib fix is a
sidecar lockfile (`O_CREAT|O_EXCL` + retry) or per-process file lock; at minimum add a
two-thread concurrency test for each store (neither has one).

### A4. Small correctness bugs that survive because they fail closed or silent

- **Root containment (F8).** `_is_under` (`workspace.py:54-56`) string-compares
  `p.startswith(r + os.sep)`. For root `/`, `r + os.sep == "//"`, never matched; same for
  `C:\`. Only the root itself passes. Fails closed (every path rejected), so it presents as
  "agent thrashes on fs tools but shell works" rather than an escape. Fix with trailing-
  separator stripping or `Path.is_relative_to`.
- **Git scope exceeds workspace (F10).** `_find_git_root` (`workspace.py:59-63`) walks
  parents by design, but git tools run with `cwd=workspace.root` and only check
  `--is-inside-work-tree`. A workspace nested in a monorepo stages/commits outside its
  boundary. Compare `rev-parse --show-toplevel` to `workspace.root` and refuse or require
  confirmation.
- **Substring permission rules (F15).** `PermissionRule.matches`
  (`permissions.py:79-87`) does `needle.lower() in haystack.lower()`. Against shell strings
  this is not a control: `rm -rf` vs `rm  -rf`, flag splitting, `--recursive --force`,
  command substitution all miss. Keep rules as defense-in-depth and label them so in the
  docstring; never as the boundary.
- **Dead code with a guaranteed crash (F12).** `_test_footer` (`curriculum.py:48-54`) is
  only a definition today, but any future caller gets `NameError: textwrap` on every
  interpreter. It survived because nothing lints (F16). Delete it or import `textwrap`;
  either way gate with pyflakes.
- **Duplicate policy singletons + unbounded audit (F14).** `registry.py:125` and
  `permissions.py:179` both export `ALLOW_ALL_POLICY` with different classes; which one a
  caller gets depends on import path. The engine version appends to `decisions` on every
  `decide()` (`permissions.py:134-135`) with no trim — a long-lived server grows memory and
  interleaves unrelated sessions in one "audit trail". Make one factory (not a shared
  instance) or cap with `deque(maxlen=...)`.
- **Blocking retry sleep (F13).** `providers.py:125,247` sleeps up to 60s inside the
  provider call, inside a tool handler, inside a server thread. Three 429s park a thread
  for minutes with no cancel-event or `Retry-After` handling.
- **Hygiene (F16, F17, F18).** No CI matrix, no packaging metadata, tests default to live
  store paths, and top-level docs still describe "no LLM, no network" while the tree ships
  providers, web, browser, vision, and a dashboard. F18 matters functionally: a reviewer
  who believes the docs skips exactly the review that finds the execution bugs above.

---

## B. Tool-calling execution and token parsing

### B1. Textual protocol parser is brittle and can crash the loop (NEW, extends prior format fixes)

`providers.py:278-326` (`_parse_textual_tool_calls`, `_TOOL_LINE_RE`, `_ARG_PAIR_RE`,
`_UNESCAPES`/`_UNESCAPE_RE`):

1. **Greedy line regex.** `_TOOL_LINE_RE = r"\[\s*TOOL:\s*(\w+)\s*\((.*)\)\s*\]"` uses
   greedy `(.*)`. One call per line is assumed, but two calls on one line merge into one
   `argstr`, and values containing `)]` backtrack unpredictably. A malformed line is then
   silently dropped (no tool call emitted) and the turn is treated as a final answer —
   the model gets no error observation to correct against.
2. **Unquoted values are unrepresentable.** `_ARG_PAIR_RE` matches only `"..."` and
   `'...'` values. Bare `k=42`, `k=true`, `k=null` never match, fall through to the
   `not args` + `_BARE_VALUE_RE` path (which only handles a single bare string), and the
   call is emitted with missing arguments → strict validator rejects → wasted turn. See B2
   for why the trainer guarantees this happens.
3. **KeyError crash on unknown escapes.** Double-quoted values unescape via
   `_UNESCAPE_RE.sub(lambda m: _UNESCAPES[m.group(1)], value)` with
   `_UNESCAPES = {"\\",'\"',"n","t"}`. Any model-emitted `\r`, `\u`, `\'`, `\x`, etc.
   raises `KeyError`. That exception is not `ProviderError`, so `loop.py:214-229` (which
   catches only `ProviderError`) does not convert it to a terminal state — it propagates
   out of `AgentLoop.run`. A single adversarial or sloppy escape sequence in model output
   crashes the run instead of becoming an observation.
4. **Asymmetric dialects.** Double-quoted values unescape; single-quoted values stay raw
   (`providers.py:301-306`). The loop's prompt (`loop.py:47-57`) forbids quotes/newlines
   while the S69 dialect claims to support them — three sources of truth for one syntax.

Fix: non-greedy/anchored line match with explicit multi-call handling, a single escape
table with fallthrough (unknown escape → literal), symmetric quote handling, and malformed
lines surfaced as tool errors rather than silent finals. Add round-trip tests over
adversarial values including `)]`, `"]`, trailing backslashes, and `\r\u`.

### B2. Trainer renders calls the parser cannot read (NEW — render/parse split)

`training.format_tool_call` (`training.py:193-211`) renders strings quoted with
`\\`, `\"`, `\n`, `\t` escaping, but booleans as bare `true`/`false` and everything else
via `json.dumps` (bare numbers, `null`, arrays, objects). The runtime parser (B1) only
accepts quoted values. So the SFT corpus teaches exactly the syntax the inference parser
rejects: every non-string argument in training data is a guaranteed validation failure at
inference. Either extend the parser to typed literals or restrict the renderer to quoted
strings and pin the equivalence with a `format → parse → format` round-trip test. Today no
such test exists; the S69 round-trip test covers only strings.

### B3. Role boundary erased for non-native providers (F11 as execution bug)

`_flatten_messages` (`providers.py:271-275`) renders every non-system message as
`f"{role}: {content}"`. Tool output, web pages, and repo files therefore share a text
plane with `system:`/`user:` instructions after flattening. The Gemini native path wraps
results in `functionResponse` parts correctly; the Ollama default path does not. For this
audit's scope the impact is executional: untrusted tool content can read as instructions
and steer the next tool turn, and there is no fence or `^(system|user|assistant|tool):`
sanitization. Delimit tool blocks per session and strip/escape role-like line prefixes
before flattening.

### B4. Registry validator checks only the top level; loop accounting has three silent drops

- **Validator gaps** (`registry.py:128-167`): only `string/array/object/integer/number/
  boolean` at depth 0; nested `properties`/`items`, `enum`, `format`, and schemas without
  `type` (accepted unconditionally) are unchecked. `object` never validates its fields,
  `array` never its items. Malformed nested args pass validation and crash handlers
  (correctly converted to `ToolResult` errors, but after a wasted turn). Error strings also
  omit the tool name, complicating multi-call turns.
- **Empty responses loop silently** (`loop.py:243-246`): an empty-text, no-tool-call
  response records `failure_detected` and `continue`s without appending any message. The
  next turn sees identical messages; a stuck provider burns `max_iterations` with no new
  signal. Append a terse system note or count consecutive empties toward termination.
- **Changed-file tracking is JSON-fragile** (`loop.py:86-104`): only write-level tools
  whose output parses as `{"path": str}` count toward `files_changed`. Any handler that
  returns plain text or a differently shaped payload edits files invisibly to metrics,
  curation (`tool_count`), and the dashboard.
- **Per-turn fan-out has no partial-failure isolation:** multiple `tool_calls` in one turn
  (`loop.py:302-374`) each append `qa_brain` system advice on failure — N failures append N
  system messages with no bound — and recovery `TERMINATE` correctly aborts remaining
  calls, but the already-executed prefix is not marked as partial in the turn record.
- **Capability minimization (G13, kept narrow):** the benchmark's `LEAN_MODEL_CATALOG`
  (`benchmark.py:78-82`) is the right pattern, but the general `agent_registry`
  (`fs_tools.py:415-481`) registers everything including browser/computer/vision. Task-
  scoped catalogs should be the default, not the benchmark exception.

---

## C. Skills — state management and reliability

### C1. `skill_teach` / `experience_record` are state mutations without a trust state (G1/G2/G14)

- `SkillToolkit.skill_teach` (`skills.py:182-192`) validates shape (`from_dict`) and
  atomically writes `skills/agent/<name>.json` (`skills.py:156-166`). It never checks that
  the procedure worked, that `required_tools` exist, that `verification` passes, or who
  verified it. `SAFE_WRITE` makes it easier to invoke than execution tools.
- `MemoryToolkit.experience_record` (`experience.py:311-334`) accepts `goal/outcome/
  diagnosis/resolution/confidence` with no link to a session, verification record, or
  observed trajectory. Downstream, `curation.score` maps `outcome == "success"` to
  `verification = 1.0` (`curation.py:190-191`), so a self-authored string becomes a
  verification score and potentially training data (G5).

The structural fix both audits recommend is right: split the API into
`propose_*` (model-callable) vs `certify_*` (runtime/harness-only, carrying a
verification id), and never let `outcome` alone imply `verified`. Until then these tools
should be confirmation-gated or removed from the default catalog.

### C2. Curation skill candidates cannot load as skills (NEW — pipeline break, two independent causes)

`TrajectoryCurator._extract_lessons` (`curation.py:544-560`) emits:

```python
"name": _skill_name(exp.goal)          # "fix-the-bug-in-x" (hyphens)
"procedure": [{"step": i, "tool": t} ...]  # list[dict]
```

but `Skill` requires (`skills.py:43-72`):

- `name` matching `[a-z][a-z0-9_]*` — hyphens fail validation, so **every** generated
  candidate name is unteachable via `skill_teach`;
- `procedure` as non-empty `list[str]` — list-of-dict fails validation.

`_skill_name` (`curation.py:644-646`) and the candidate procedure shape (plus G7's dropped
`args`) mean the curation→skills handoff is broken by construction, not by edge case.
Fix by emitting underscore names and either `list[str]` steps or a schema migration that
accepts structured steps with `tool/arguments/observation/verified`.

### C3. `Skill.from_dict` silently corrupts non-list fields (NEW)

`skills.py:90-106` coerces with `list(...)` and `str(...)` without type checks:

- `"required_tools": "read_file"` (a string, not a list) becomes
  `['r','e','a','d',...]` and validates;
- non-string procedure steps become `str(step)` instead of raising.

Add `isinstance(..., list)` guards before coercion; reject scalar-where-list at the gate
(the same class of bug as `bool`-is-`int`, which the codebase already handles correctly
in the registry validator).

### C4. Retrieval and persistence are unreliable by mechanics, not just semantics (G18/G19/G8/G9/G24)

- **Substring retrieval** (`skills.py:144-154`, `experience.py:192-205`): `term in text`
  with `len(t) > 2` filtering. `test` matches `latest`/`contest`; `api` matches broadly;
  synonyms never match. Confidence is added to overlap (`overlap + confidence`), so a
  1-term overlap gap always beats any confidence difference, while a query with no
  >2-char terms returns top-k by confidence alone (the `not overlap and terms: continue`
  guard passes everything when `terms` is empty).
- **Fixed source weights** (`experience.py:227-245,249-297`): experience base 3.0, case
  2.5, doc 2.0, journal 1.5. A weak experience outranks a strong document by construction;
  weights are policy, not measured relevance, and are uncalibrated (G6/G19).
- **No provenance/version binding** (`skills.py:43-57`): no `skill_version`,
  `source_session_ids`, `tool_schema_versions`, `verified_by`, `last_verified_at`. A skill
  outlives the tool schema it was demonstrated against with no invalidation signal.
- **Unevidenced confidence** (`skills.py:59-72`): any value in `[0,1]` accepted with no
  evidence link; retrieval then boosts by it. Confidence must be computed from
  verification/replay history, not supplied by the claimant.
- **No rollback** (G24): promotion is a file write; there is no `REVOKED` state, version
  lineage, or regression-triggered demotion. Add the PROPOSED→QUARANTINED→TESTED→
  VERIFIED→PROMOTED→REVOKED lifecycle before more skills accumulate.
- **Library re-reads the directory on every call** (`skills.py:121-154`): `load()`,
  `get()`, `find()` each glob+parse all files; `teach()` overwrites in place with no
  backup/version. Fine at current scale, wrong as the persistence story for learned
  behavior.

---

## D. Curriculum, curation, and training — thresholds and data-gating

### D1. Difficulty is metadata, and level selection collapses after the first task (G10 + NEW)

- `tools_required` is the constant `3` for every task (`curriculum.py:367-371`); `reasoning`
  is `min(5, 1 + level//2)` and `steps` is `min(10, 2 + level)` — numbers that describe
  nothing the fixture does. Only `_bug_fix_fixture` varies with level (a decoy helper at
  `level >= 3`, `curriculum.py:94-95`); testing/refactor/regression/docs fixtures ignore
  `level` entirely.
- **NEW — level shadowing bug** (`curriculum.py:329-343`): `generate(count, level=None)`
  reassigns its own parameter in the loop:

  ```python
  level = level if level is not None else self._rng.randint(lo, hi)
  ```

  When the caller passes `None`, the first iteration draws a random level and every later
  iteration reuses it (`level is not None` is now true). A "mixed-level" curriculum of N
  tasks is really 1 random level × N. Use a separate local (`task_level`) and never assign
  to the parameter. Related: `self._counter` increments even on dedupe-skipped attempts,
  leaving gaps in `C-%04d` ids — harmless but confirms attempts and tasks are conflated.
- `_test_footer` dead code (F12/A4) sits in the same file: the one function that would
  exercise `textwrap` cannot run, so difficulty-infra rot goes unnoticed.

Difficulty must change task structure (files, indirection, misleading symptoms, cross-file
deps, competing hypotheses — the GPT report's level ladder is sound) and be covered by a
test asserting level actually varies fixture content.

### D2. Generation accounting and coverage mislead experiments (G22/G23)

- `generate()` (`curriculum.py:336-352`) tries `count * 20` attempts and silently returns
  fewer tasks when goal-dedupe collides. A caller requesting 100 that receives 87 gets no
  error, no `requested/produced/skipped/exhausted` breakdown. For a harness where dataset
  size is a controlled variable, silent shortfall invalidates comparisons. Return the
  accounting and add `strict=True` that raises.
- `coverage()` (`curriculum.py:383-389`) counts tasks mentioning each skill label. Ten
  near-identical `bug_fix` tasks read as "strong debugging coverage". A real matrix is
  `skill × difficulty × family × novelty × outcome` including success/recovery/transfer
  rates, not a histogram of labels.

### D3. Mastery tracker mutates on read and grows without bound (G12, extended)

`MasteryTracker` (`curriculum.py:395-431`):

```python
def working_level(self, skill):
    level = self._levels.get(skill, self.min_level)
    ...
    self._levels[skill] = level   # read changes state
    return level
```

Recording 3 successes then calling `working_level()` repeatedly ratchets the stored level
up once per call (same downward after failure streaks) with no new evidence. `recommend()`
calls `working_level()`, so a supposedly read-only recommendation mutates levels. And
`record()` appends to `_streaks[skill]` forever — unbounded per-skill growth. Fix: mutate
only in `record()`; make `working_level()` pure; bound streak history to the
`level_up_streak + level_down_failures` window actually read.

### D4. Curation gate: uncalibrated thresholds, shifting denominators, stale verdicts (G6 + NEW)

Constants (`curation.py:52-55`): `ACCEPT_THRESHOLD = 0.5`, `REVIEW_THRESHOLD = 0.3`,
`REVIEW_CONFIDENCE = 0.5`. No calibration against usefulness; the numbers are triage
policy presented as quality measurement.

1. **Mean over varying denominators** (`curation.py:183-261`): `overall` averages only
   known dims (`None` excluded). A trivial single-tool success averages over 7 dims while a
   rich recovered trajectory averages over 9 — different denominators compared as one
   number. Component divisors are equally arbitrary: `tool_use = distinct/4.0`
   (`curation.py:206-209`), `relevance = substance/5.0` (`curation.py:250-256`),
   `robustness = pairs/3.0` (`curation.py:238-243`), efficiency docked 0.2/penalty,
   clarity 0.3/penalty. A short solution scores lower for using fewer tools; a long one
   scores higher for vocabulary, not transfer value.
2. **NEW — verdict computed before diversity, never recomputed.** `curate()`
   (`curation.py:411-433`) builds trajectories (each `_trajectory` computes `verdict` from
   the pre-diversity `overall`), then `_apply_diversity` recomputes every `overall`
   (`curation.py:515-517`) without recomputing `verdict`. The stored verdict can disagree
   with the stored score on every record. Recompute verdict after diversity or exclude
   diversity from the gated score.
3. **Success implies verification (G5).** `score()` sets `verification = 1.0` whenever
   `outcome == "success"` (`curation.py:190-191`), valid only if experiences originate
   exclusively from trusted session conversion — but `experience_record` lets the model
   mint `success` directly (C1). Replace with a `verified_success` predicate keyed on a
   verification record the model cannot author.

### D5. Experience identity and mutation lose information (G20, extended)

`ExperienceStore.record()` (`experience.py:172-190`) dedupes on `_normalize_goal` alone
(lowercase, punctuation-stripped). Same wording with different project, failure,
environment, or solution collapses into one record — the benchmark's session-suffix
workaround (`benchmark.py:194-197`, `session_learning.py:167-173`) is the admission that
the key is lossy. Worse, reinforcement **overwrites**: `confidence`, `outcome`,
`diagnosis`/`resolution` (when present) are replaced by the latest arrival, so a later
failure flips a stored success to `failed` while still incrementing `times_seen` —
recurrence and contradiction share one counter. Identity should be
`goal + project + failure-signature + verification-context`; conflicting outcomes should
branch or version, not overwrite.

### D6. Training gate gaps: silent drops, truncation, and stale caching (extends G6/G21)

`training.py` discipline (curated-only input, ACCEPT + verified-success gate, exclusion
reasons) is the right shape; the holes are at the edges:

- **`INVALID` vanishes silently** (`training.py:307-314`): `build_records` skips
  `classification == "INVALID"` before record construction, so INVALID trajectories appear
  in neither `trajectories` counts nor `exclusion_reasons` — contradicting the "exclusions
  carry reasons" pin. Count them explicitly.
- **Truncation without marking:** `MAX_STEPS = 50` (`training.py:42`), `MAX_TEXT_CHARS =
  500`, first-3-failures cap (`training.py:100-112`) silently cut long trajectories and
  recovery histories. Eligibility is unaffected by truncation, so a truncated trace trains
  as a complete one. Record `truncated: true` and surface counts in the report.
- **Goal-suffix strip is overbroad** (`training.py:250`): `split(" (benchmark run")[0]`
  mangles any legitimate goal containing that substring. Strip only a trailing
  ` (benchmark run <hex>)` match.
- **Runtime catalog cache never invalidates** (`training.py:214-236`): `_RUNTIME_CATALOG`
  is process-global, built from a throwaway temp workspace. Catalog changes mid-process
  are invisible; tests that mutate `LEAN_MODEL_CATALOG` can poison each other.
- **Replayability (G21):** bounded captures (`tool`, `args`, first-line `result_head`,
  `session_learning.py:95-117`) are behavior traces, not replayable demonstrations —
  dependency, environment, git, race, and multi-file states are unrecoverable from them.
  Label the two tiers explicitly instead of implying sufficiency.

### D7. Apprenticeship does not deliver the lesson (G3, still open); legacy pipeline still destroys evidence (G4)

- **G3** (`apprenticeship.py:150-197`): the retry calls `student_factory(model=None)` on a
  fresh fixture with no lesson argument, no context injection, and no workspace
  application of the teacher's actions. Acceptance therefore tests
  `failed → teacher-has-actions → student-later-passed`, not
  `student-received-and-applied-lesson → passed`. The `AttemptFactory`-switches-behavior
  test fixture hides this by making the student solvable without the lesson. Fix with
  `student_factory(lesson=lesson, ...)` (or an explicit lesson message in the retry
  session), record exactly what the student saw, and add a test whose student can only
  pass if the lesson arrives.
- **G4** (`session_learning.py:280-311` vs `curation.py:401-462`): the S50 `curate()`
  `store.save(kept)` permanently deletes greeting/resume-pattern records and writes the
  resume skill seed as a side effect, while the S62 `TrajectoryCurator` assumes a stable
  source corpus with append-only RAW → FILTERED → CURATED → VERIFIED → TRAINING stages.
  Invoking the legacy path first destroys evidence the newer path would curate. Retire or
  gate the destructive path; raw experience must be immutable to curation.

---

## E. Structural root causes both audits circled but did not isolate

1. **No proposal-vs-certified type boundary.** Model-claimed (`experience_record`,
   `skill_teach`, `outcome="success"`) and runtime-certified (verification records,
   replayed skills) values share types, stores, and scores. Every trust bug (C1, D4.3, G5)
   is this single missing distinction. Introduce separate record kinds; only certified
   records influence curation/training/retrieval ranking.
2. **Reads mutate.** `working_level`/`recommend` (D3), `PermissionPolicy.decide` audit
   growth (A4/F14), and goal-dedupe reinforcement (D5) all change state on what callers
   reasonably treat as reads. The codebase's own "fixtures-first" honesty norm requires
   pure reads; enforce it by review rule.
3. **Goal text is the identity key in three subsystems.** Experience dedupe (D5), curation
   dedupe (`curation.py:416-429`, same normalization), and curriculum dedupe
   (`curriculum.py:346-349`) all key on normalized goal strings. Distinct lessons with
   similar wording merge; identical reruns need suffix hacks. Promote composite keys
   (`goal + project + failure-signature + verification-context`).
4. **Render and parse are developed separately.** Loop prompt vs parser (B1), trainer
   renderer vs parser (B2), Gemini schema coercion vs registry validator (B4) — each pair
   drifts because no test pins `render → parse → render`. One round-trip property test per
   pair closes all three.
5. **Silence as a default.** Short curricula (D2), dropped tool lines (B1), empty-response
   loops (B4), INVALID exclusions (D6), destructive curation (D7) all succeed quietly while
   losing data. The repo norm ("never silent", stated in S50/S62 pins) needs a mechanical
   form: every lossy operation returns `produced/skipped/exhausted` counts or raises.

---

## F. Remediation order (execution-bug value per effort)

1. **A1 + F16:** fix the five `typing` imports; add pyflakes + a 3.12 CI leg immediately.
   Nothing else is verifiable off-3.14 until this lands.
2. **B1 + B2:** harden the textual parser (no `KeyError`, typed literals, malformed-line
   errors) and pin renderer↔parser round-trips. This is the highest-value loop fix: it
   turns wasted turns and run crashes into correctable observations.
3. **C2 + C3 + D7(G3):** repair the curation→skills handoff (names, procedure shape, args),
   guard `from_dict` coercions, and actually deliver the apprenticeship lesson. These are
   the three places the learning story is broken by construction rather than by tuning.
4. **D4.2 + D1(level bug) + D3:** recompute verdicts post-diversity, stop shadowing `level`,
   make `working_level` pure. Each is a few lines and each currently invalidates its own
   subsystem's measurements.
5. **A3 + D5 + C1:** lock or serialize the two stores, composite experience identity
   without destructive overwrite, and split propose/certify APIs. This seals the
  Easy-to-poison → curated → trained chain at the type level.
6. **A2 + A4(F13/F14/F8/F10/F15) + B4 + D2/D6:** shared executor with wall-clock tests,
   cancel-aware retries, bounded audit trails, root/drive containment, git toplevel check,
   validator depth or explicit limits, curriculum accounting + truncation flags.
7. **Docs + hygiene (F17/F18):** temp-dir store isolation in tests with a clean-tree CI
   assertion; rewrite top-level architecture status to describe the agent runtime that
   actually ships.

---

## G. What holds up (calibration)

- `PathPolicy` layering (`workspace.py:66-136`): `..` ban, resolve-then-contain, protected
  prefixes with boundary checks, null-byte rejection, normcase handling — correct in
  design; F8 is a one-helper bug.
- Git argv construction (`git_tools.py`): no shell, `--` separators, `--no-pager`, correct
  `core.quotePath` handling — scope (F10), not injection, is the gap.
- `requires_confirmation` pipeline guarantee (`registry.py:309-316`, `permissions.py:156-161`):
  the tool's own declaration upgrades ALLOW→ASK regardless of policy — right precedence,
  sparsely applied.
- `validate_tool_arguments` bool-vs-int strictness (`registry.py:153-157`): the edge case
  most hand-rolled validators miss, correctly refused.
- `kill_process_tree` and the S35 per-command timeout: the one timeout layer that actually
  kills (POSIX `killpg`/new session, Windows `taskkill /F /T` + reap).
- Verification-first benchmark design (`benchmark.py:85-90,178-186`): model "done" never
  equals success; only the plan result counts — the principle §C1/D4 ask to be extended to
  memory and skills.
- Scale and honesty of the suite (1500+ tests, `skipUnless` platform guards, stated pins):
  the failures above are blind spots (concurrency, wall-clock, cross-version, redirect
  chains, non-Windows), not lack of effort — and each maps to a cheap new test.
