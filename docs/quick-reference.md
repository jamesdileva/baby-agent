# Quick Reference — baby-agent operations

The standing commands. Full details live in the worklog (AGENTS.md) and
the per-sprint specs (docs/sNN-spec.md).

## The two loops

### Daily loop (minutes, keeps the corpus fed with real data)

```bash
qa gemini-drip        # one real benchmark pass on the free-tier brain
```

- Costs ~7-9 requests of the **20/day** flash-lite budget — two drips a
  day fit comfortably; the third usually 429s (that's honest, exit 1).
- Verified passes AND honest failures are recorded; the next
  `qa curate` chain picks them up.
- Fresh sessions from your own agent use? `qa mine-sessions --source
  opencode` (and `--source zcode`) folds them in the same way.

### Generation loop (one Colab job per generation)

1. **Rebuild the corpus** (hygiene + idempotent: only new/stale goals
   are re-demoed):

   ```bash
   qa build-corpus      # [--category NAME] [--levels N] for partial builds
   ```

   This chains curate → build-training → kit export automatically.

2. **Train on Colab** (free T4, ~5 minutes):
   - Upload `training/training.jsonl` and `training-kit/train_ep1.py`
     via the **files panel** (left sidebar folder icon — not into a cell).
   - Cell 1: `!pip install -U transformers peft datasets trl accelerate`
   - Cell 2: `!pip uninstall -y torchao`  (Colab ships an old one; recent
     peft raises on it instead of ignoring it)
   - Cell 3: `%run train_ep1.py`
   - The script sanity-checks the model and refuses to declare success on
     garbage. If it passes: `!zip -r epN-merged.zip epN-merged`, download.

3. **Import locally** (from the directory containing `epN-merged/`):
   - Copy `ModelFile` (repo root) and change its first line to
     `FROM ./epN-merged`.
   - `ollama create baby-agent:epN -f ModelFile`
   - `ollama create baby-agent:epN-q4 -f ModelFile --quantize q4_K_M`
     (q4 is ~3× faster on CPU and the verdict-day keeper)

4. **The verdict**:

   ```bash
   qa verdict --models baby-agent:epN-q4,baby-agent:ep2-q4 --ab-demos
   ```

   Prints per-task results + the protocol-metric table
   (discovery-first rate, with-calls rate, guessed-path rate, success).
   `--ab-demos` runs the ep0.5 on/off pair (worked-example injection)
   for the FIRST listed model. `compare()`-style honesty: regressions
   are called out, never shipped silently.

## Utility commands

| command | purpose |
|---|---|
| `qa curate` | run the S62 curation gate over the store |
| `qa build-training` | rebuild the S63 training export from curated data |
| `qa mine-sessions --source opencode` | fold in new agent sessions |
| `qa preflight` | the done-claim gate (clean tree, no BOMs) |
| `qa serve` | the dashboard at http://127.0.0.1:8765/ |
| `qa ask "question"` | the QA brain over the case base |

## How to run dash
python -m qacompanion serve --port 8765

## Knobs and locations

| what | where |
|---|---|
| experience store | `experience.jsonl` (env `QA_EXPERIENCE_FILE`) |
| curated exports | `curated/` (env `QA_CURATED_DIR`) |
| training exports | `training/` (env `QA_TRAINING_DIR`) |
| training kit | `training-kit/` (committed) |
| dashboard brain | `QA_AGENT_PROVIDER=gemini` before `qa serve` |
| local-model patience | `OLLAMA_TIMEOUT` (native floor 300s), `OLLAMA_THINK=false`, `OLLAMA_NUM_CTX` |
| gemini pin | `GEMINI_MODEL=gemini-3.1-flash-lite` (each model has its own 20/day bucket) |

## The standing rules (short version)

- Tests green or it didn't happen; every claim runs through the
  verification gate.
- Mined ≠ verified: only ACCEPT + successful + verification evidence
  ever reaches `training.jsonl`, and exclusions carry reasons.
- Every generation is benchmarked — never assumed better. A generation
  that fails is recorded as failed.
