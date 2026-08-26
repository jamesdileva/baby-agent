# baby-agent

A decoupled, lightweight, continuously-learning QA companion — no LLM inside.

Built by the Antfarm colony (agent-a, agent-b, and tess). Unlike its creators,
this tool burns zero tokens: it is a deterministic case-matching engine that
gets sharper the more failures it sees.

## The idea

Every software project develops signature failures — the same bug shapes
recurring under new clothes. Humans (and LLM agents) re-diagnose them from
scratch every time. `baby-agent` records each failure as a **case**
(fingerprint + diagnosis), so the Nth occurrence of a known failure is
recognized instantly, for free, forever.

LLM agents act as **teachers**: their reasoning distills lessons into cases.
The tool is the student: it stores, matches, reports — never guesses silently.

## Status

Pre-implementation. See [docs/spec.md](docs/spec.md) for the frozen v1 spec
and [docs/qa-companion-run.md](../../../Agents/docs/qa-companion-run.md) in
the Antfarm repo for the run brief that produced this spec.

## Roles in this repo

- agent-a: builder
- agent-b: critic/reviewer
- tess: primary user + QA (once promoted to Analyst) — her reviews feed cases;
  the case base sharpens her reviews
