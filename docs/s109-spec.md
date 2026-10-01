# S109 — The post-README seam: demonstrate the tempted call being
# rejected (ep22's single training variable)

## Problem (forensics on the gen-21 explore-qa failures)

Rung 7 did not move: 0/6 (ep21 0/3, ep20 0/3), all max-iterations.
The S108 transfer was GRANULAR, and the trajectory names the seam:

- **Transferred:** the anti-guess beat (ep21 guessed_path 0.0 vs
  ep20's 0.5556 — the champion guesses paths on explore-qa, ep21
  never does) and listing-first (the trajectory opens list → README).
- **The seam:** after README — which says "see the docs folder," the
  exact moment the S108 drill demonstrates returning to the listing —
  ep21 instead loops `code_references(symbol="main")` /
  `code_symbols(name="main")` with invented arguments, ×9 to
  max-iterations. The drill demonstrated the decoy-recovery but not
  the TEMPTED tool-call rejection at that moment.

**The institutional pattern, third instance:** drilled beats transfer
on first contact and evaporate at the continuation seam (cascade
chain-2, the fabricated anchor, now this). The fix method is proven:
demonstrate the wandering being rejected AT the seam.

## Design — ep22's ONE variable: the seam beat in the explore drills

The three S108 drills are re-authored on their proven fixtures with
NEW goals (the lane skips covered goals; the lesson is new). Each now
demonstrates, at the post-README moment, exactly what the live model
does wrong — and its correction:

1. **explore-server v2:** list → read README → **the tempted call:
   `code_references(symbol="main")` — rejected, invalid arguments**
   → back to the listing → read docs/running.md → final quoting both
   facts with the source.
2. **explore-config v2:** list → read README → **the tempted call:
   `code_symbols(name="main")` — rejected** → back to the listing →
   read docs/configuration.md → final quoting both settings.
3. **explore-recovery v2:** list → the guessed read (`src/main.py`,
   not found) → **the tempted call (`code_references`) — also
   rejected** → back to the listing → read docs/testing.md → final.
   Both live wandering shapes demonstrated and corrected in one run.

The narratives name the rule explicitly: "the README pointed at the
docs — the next action was the listing, not a symbol hunt."

## Honest bounds

- Same-fixture re-authoring with new goals, per the S107 precedent
  (metrics/scale); nothing else in the corpus changes. ep22's only
  deliberate variable is this batch.
- The invalid codeintel calls ride the recorded trajectories as
  deliberate failed beats (the S107 eligibility exemption covers
  them: 2 failed steps per drill, under the cap anyway).
- Rung-4 authoring (open since rung-3 graduated) is queued as the
  NEXT generation's variable after this one, by direction.

## Test plan

1. Validator: all three v2 demos pass; batch count 29 -> 32.
2. Lane: all three pass the REAL fact-gate, tagged agent-authored +
   corpus-v8.
3. Corpus rebuild: deliberate pool +3; export carries the v2 drills;
   rebuild stays idempotent.
