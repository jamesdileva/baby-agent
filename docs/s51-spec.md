# S51 — Skills 2.0: Design Spec

Spec of record for the sprint: [ROADMAP-agentlite.md](ROADMAP-agentlite.md)
§S51. Builds on S31–S50. One slice, stdlib only, no CLI changes.

## Overview

Reusable procedures as DATA. A skill is a JSON record (the S51 schema
the S50 resume seed already follows) that the MODEL retrieves and
follows with its ordinary tools — procedures are surfaced, not
hard-coded. The first consumer already exists: the S50 resume seed
(skills/agent/resume_interrupted_task.json) becomes loadable knowledge.

## Module layout

```text
qacompanion/agent/skills.py      # Skill schema + SkillLibrary + tools
tests/test_agent_skills.py
```

## Skill schema (strict, the S51 fields)

```text
name (required, identifier-like), goal (required), description,
required_tools [], preconditions [], procedure (required, ordered,
non-empty), verification, failure_modes [], examples [],
confidence 0..1 (default 0.5), tags []
```

`to_dict`/`from_dict` strict (malformed → ValueError). Library files are
JSON, one skill per file, named `<name>.json`.

## SkillLibrary

- Loads `*.json` from a directory (default `skills/agent` — where the
  S50 seed lives). Tolerant loading: a malformed file is recorded in
  `.errors` and skipped (a library of many skills must not die on one
  bad file — different contract from the strict single-file stores).
- `list_skills()`, `get(name)` (exact), `find(query, k=3)` — keyword
  scoring over name/goal/description/tags (the S47 retrieval pattern,
  deterministic).
- `teach(skill)` — persists a new/updated skill JSON atomically.

## The two tools (category "skills", brain-level requires_workspace=False)

```text
skill_find   {query, k?}    READ_ONLY   matching skills with their full
                                        procedures — the model reads the
                                        procedure and follows it with its
                                        ordinary tools (data-driven: the
                                        model executes, the library only
                                        surfaces)
skill_teach  {skill}        SAFE_WRITE  teach a new skill at runtime
                                        (validated, atomic)
```

Execution of procedures programmatically stays out (that is curation/
S62-scale machinery); verification of a followed skill still goes
through the S41 gate when applicable. `agent_registry()` grows to 51
tools.

## Testing strategy (tests/test_agent_skills.py)

- Schema: round trips (non-ASCII); validation rejections (missing
  name/goal/procedure, empty procedure, confidence bounds, bad types).
- Library: load from a fixture dir; tolerant malformed-file skip with
  `.errors`; missing dir → empty; list/get/find ranking; teach persists
  atomically and is findable afterwards.
- Resume seed integration: the REAL skills/agent/resume_interrupted_task
  .json loads and is found by query "interrupted" (the S50 → S51 loop
  closed).
- Tools: side-effect matrix; through-registry find; teach → find
  round trip through the registry; agent_registry membership (51).

Expected suite growth: 1319 → ~1330 OK.

## Exit criteria (from ROADMAP-agentlite.md §S51)

Teach/retrieve a skill; the agent follows its procedure (the model-facing
mechanism: skill_find surfaces procedure + verification; the S48
benchmark's recovered path demonstrates a procedure being followed).
Full suite green; preflight clean.
