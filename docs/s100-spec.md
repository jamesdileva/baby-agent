# S100 — Failed-edit recovery demos + thrash-turn surgery

## Mechanism (S95.1 audit, evidenced)

ep15 strings 0/3 is not confusion — it is a self-inflicted wound with
no recovery: whole-file rewrite fixes `reverse` but drops `+ "!"`
from `shout` (transcription slip), the retry anchors on the stale
pre-edit file (`old_string not found`), then `run_tests, read,
run_tests, read` to max-iters with an empty final — a second edit is
never attempted. ep11 (21/21) transcribes cleanly AND recovers when
it fumbles. Two gaps: transcription fidelity under rewrite load
(probe B: single-function 2/2 PASS) and failed-edit recovery (probe
A: minimal-edit prompt line 0/3 — not instruction-steerable, must be
trained).

Corpus forensics: ep15's training is 184 scripted (all ≤2-line
anchors, zero mess) + 181 real verdict successes (mean 3.2-line
anchors, 55 whole-file-ish, ~1 fail/run of accidental thrash trained
verbatim as imitation targets). ep11 trained at ~90% scripted.
Research: KITE polarization (weak skill degrades while strong rise),
SCoRe behavior collapse (SFT without recovery states stops editing),
retry-data/Reflective Recovery (error→correction sequences DO teach
recovery), STaSC selectivity (unselective correction traces = noise).

## Recipe

- **C1/C2 — failed-edit-recovery demos** (new shape in
  `agent_authored_demos`, verified through the real loop + S41 gate):
  R1 replays ep15's exact failure prefix (real args from the saved
  trajectory: whole-file edit breaking `shout`, stale-anchor retry
  failing `not found`) then re-reads and lands a minimal corrective
  anchor from the fresh observation; R2/R3 generalize to fresh
  two-function modules. The stale miss is DECLARED
  (`demo["recovery_anchors"]`) and the validator simulates file
  state through the script: a declared miss must genuinely miss
  (count 0) against current content, be followed by a successful
  corrective edit on the same path, and every declaration must be
  consumed — authoring stays untrusted-by-design.
- **D — thrash-turn surgery** (`training.py`): chat renders drop
  `ok is False` tool turns (+observations) from UNDELIBERATE records
  only — deliberate = tagged `scripted-demo` / `agent-authored` /
  `recovery-demo` / `edit-recovery` (designed beats stay, per the
  retry-data literature); S72 premature-final interleave is kept
  (deliberate failure-state teaching) with cuts remapped onto the
  cleaned step list; `trajectories.jsonl` keeps full truth, only the
  taught chat is cleaned, and metadata labels
  `failed_turns_stripped`. Real-share cap 0.5 cleanest-first
  (fewest failed steps, tie-break session id) with report counts —
  future-proofing; the strip is the active ingredient today.
- **Out:** ep16 corpus via the standing lane → curate → export;
  Colab order: fresh `training.jsonl` + s92 kit (unchanged) → ep16
  → pinned 5-task verdict vs ep11-q4. ep16 ships only on a strings
  reading that moves with cleaner hygiene (failures back toward 3,
  guessed 0.0); ep11-q4 remains champion until then.

## Acceptance

- New validator tests (declare-and-miss, genuine-miss, consumed,
  corrected) + training tests (strip, deliberate-keeps-beat,
  share-cap) green; full suite exits 0.
- Live: lane runs green (R1–R3 verify first try — deterministic
  scripts), curate/export counts recorded, report shows
  `failed_turns_stripped` and `real_capped`.

## Live result (2026-09-27)

- Lane: 3 runs (R1–R3, all new goals), 3 passed, 0 rejected, 16
  skipped-existing. R1's recorded trajectory carries the genuine
  `edit_file ok=False` ("not found") beat, tagged
  `scripted-demo` + `agent-authored` + `edit-recovery`.
- Curate + export: 1481 trajectories, 387 eligible/step-trainable;
  deliberate 187 (184 + 3 R), real kept 187, **capped 13**
  (noisiest cut, cleanest-first); **97 failed turns stripped**
  from taught chats (`trajectories.jsonl` keeps full truth);
  SRFT 6. Export 380 = 374 + 6 (was 365 = 360 + 5).
- Suite 1738 OK (1727 + 11 new), pyflakes clean.
