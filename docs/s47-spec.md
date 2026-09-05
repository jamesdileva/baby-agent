# S47 — Experience Memory: Design Spec

Spec of record for the sprint: [ROADMAP-agentlite.md](ROADMAP-agentlite.md)
§S47. Builds on S31–S46. One slice, stdlib only, no CLI changes.

## Overview

The QA case base becomes one specialized source inside a broader memory
layer. S47 adds the missing store — **agent experiences** (episodic +
failure memory from coding sessions) — and the unified read layer over
all four memory sources. Automatic context injection stays out (S56 owns
the ContextBuilder/MemoryRetriever); retrieval is tool-driven, the
proven S27 pattern.

**Store mapping (documented):**

```text
failure memory      cases.jsonl        (existing, S1-S10)
documentation       digest.jsonl       (existing, S20/S29)
semantic/procedural journal.md         (existing, S15)
episodic/agent      experience.jsonl   (NEW this sprint)
```

## Module layout

```text
qacompanion/agent/experience.py    # Experience, ExperienceStore, MemoryLayer, tools
tests/test_agent_experience.py
```

## Experience record

```text
experience_id (uuid hex), session_id?, goal (required),
context {}, actions [], failure?, diagnosis?, resolution?,
verification {}, outcome (required: success|failed|recovered|
human_corrected|partial), confidence (0..1, default 0.5),
times_seen (default 1), tags [], project_type?, languages [],
recorded_at, last_reinforced_at
```

`to_dict`/`from_dict` strict (malformed → ValueError, S1 culture),
JSONL-ready, non-ASCII safe.

## ExperienceStore

- JSONL at `experience.jsonl` (cwd default), overridable via
  `QA_EXPERIENCE_FILE` (the QA_CASES_FILE convention). Atomic writes
  (tmp + os.replace); load is strict about malformed lines; BOM/CRLF
  tolerated (S19 lessons).
- **Recurrence over duplication**: recording an experience whose
  normalized goal matches an existing one bumps `times_seen`, updates
  confidence toward the newer value, refreshes `last_reinforced_at` —
  "better at recurring problems" made mechanical. Distinct goals append.

## Retrieval (stdlib scoring, honestly labeled)

`find_similar(query, k=5)` scores keyword overlap between query terms
and goal + tags + failure/diagnosis/resolution text, boosted by
times_seen and confidence. No embeddings — the upgrade path (semantic
retrieval) is documented for S56; the ranking is deterministic and
testable now.

## MemoryLayer (the unified read)

`search(query, k_per_source=3)` queries all four stores and returns
merged, score-ranked, **source-labeled** results
(`source: experience|case|doc|journal`). A missing/unreadable store
degrades to empty — never crashes; per-source scoring is thin and
explicit (keyword match on the store's natural text fields).

## The three tools (category "memory", brain-level — requires_workspace
False, like the S27 knowledge tools)

```text
experience_record  {goal, outcome, session_id?, diagnosis?, resolution?,
                    actions?, tags?, project_type?, confidence?}  SAFE_WRITE
experience_search  {query, k?}                                    READ_ONLY
memory_search      {query, k_per_source?}                         READ_ONLY
```

`agent_registry()` grows to 49 tools.

## Testing strategy (tests/test_agent_experience.py)

- Record round trips (incl. non-ASCII), strict validation, JSONL
  persistence across store instances, BOM/CRLF tolerance, atomicity.
- Recurrence: same normalized goal bumps times_seen / refreshes stamp,
  no duplicate row; distinct goals append.
- Retrieval ranking: keyword overlap; times_seen/confidence boosts; k
  limit; empty store → empty.
- MemoryLayer: merged results carry source labels; each real store
  exercised with its own fixture API (CaseStore/DigestStore/journal);
  missing store files degrade to empty.
- Tools: registration matrix; through-registry record+search; default
  SAFE_WRITE posture (record); agent_registry membership (49).

Expected suite growth: 1258 → ~1285 OK.

## Exit criteria (from ROADMAP-agentlite.md §S47)

Teach a successful recovery procedure (experience_record), run a similar
query, and the experience is retrieved ranked-first — the tool path that
S56 will wire into automatic context. Full suite green; preflight clean.
