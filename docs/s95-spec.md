# S95 — Rung-3 demos + success-hygiene filter

Status: landed 2026-09-27. Rung 2 graduated S94.1, so rung-3 demo
authoring OPENS. One bundled corpus-side change (the
investigation's child).

## The investigation (why ep11 beats ep14)

Success-hygiene forensics, failures/run by source: ep11-era 0.28
with 0 guessed paths vs ep12 0.94/12, ep13 1.12/9, ep14 1.16/6.
ep14's corpus absorbed ~100 verdict trajectories at ~1 fail/run
with UNCORRECTED wrong turns and terse finals — and the
assistant-only loss imitates [TOOL:] calls including the failed
ones. ep14 at inference (44–64 failures, guessed 0.2–0.33)
behaves exactly like its training data. ep11 won on data hygiene
(pre-verdict-wave corpus), not size. So "more demos" was never
going to save ep14; clean data will save ep15.

## Track 1: rung-3 demos (gate open)

Three import-following demos on fresh modules (never taxcalc/cart
— the S91 eval-module lesson): invoice/prices, checkout/rates,
basket/fees (with a genuine wrong-turn read). Plain reads only —
code_imports/code_references are NOT in the lean catalog, and
demos must use only inference-offered tools (the S72 lesson).
Validator + gate; finals walk the import chain.

## Track 2: success-hygiene filter

`MAX_FAILED_TOOL_STEPS = 2`: verified successes with more failed
tool steps are excluded with a recorded reason. `ok` means TOOL
success (a failing suite still has ok=True), so the filter cuts
tool-error thrash precisely; scripted recovery demos carry
exactly one deliberate failed read and pass. Live effect: 82
thrash trajectories excluded (3–12 failed steps each), all 16
agent-authored demos + all scripted demos survive. Report tallies
the exclusions automatically.

## Dedupe fix (found live)

The lane re-recorded every demo under fresh suffixes on each
rebuild (13→26 authored records observed) — unbounded demo
inflation straight at the dilution fight. `build_agent_corpus`
now skips covered goals like `build_corpus` does (idempotency
test pins it). History left in place (valid successes, benign
overweight toward clean demos); future rebuilds stay flat.

## Live

- Lane 16/16, curate 1435/2/1, export 365 = 360 + 5 SRFT.
- Suite 1698 OK (1695 + 3), pyflakes clean.

## Colab order

Fresh `training/training.jsonl` + s92 kit (UNCHANGED — no kit
variable this generation) → ep15, same 7B base → GGUF-LoRA
import → pinned ep15 vs ep11-q4, 5 tasks. Crown rule stands.
