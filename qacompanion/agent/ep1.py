"""S64 ep1 corpus builder: scripted curriculum demonstrators -> a
verified, step-trainable training corpus — plus the external-compute
training kit export.

Why scripted demonstrators: the roadmap's ep1 needs MANY verified
trajectories, but the free-tier Gemini caps model-generated data at a
few benchmark passes per day, and this machine's GPU (AMD RX 6400,
4 GB, no CUDA) cannot fine-tune locally. The S60 curriculum declares
its defects BY CONSTRUCTION, so a scripted demonstrator that fixes the
DECLARED defect — driven through the REAL S37 loop with REAL subprocess
test execution and the S41 verification gate — produces genuinely
verified demonstrations. Provenance is honest: every record is tagged
`scripted-demo`; the corpus teaches protocol and procedure, and says
exactly what it is.

Pins (fixtures-first discipline):
- only runs that pass the S41 verification gate become records (the
  S63 eligibility gate re-checks at training time);
- the demonstrator's edit uses the declared old/new strings — never a
  whole-file rewrite, so the demonstration teaches surgical editing;
- deterministic: same variants x levels = same corpus content.
"""

from typing import Any, Dict, List, Optional, Tuple

from .benchmark import run_benchmark
from .contracts import ModelResponse, ToolCall
from .curriculum import _bug_fix_fixture, bug_fix_defect
from .experience import ExperienceStore
from .providers import FakeModelProvider
from .training import format_tool_call

DEMO_MODEL_TAG = "scripted-demo"

# the corpus recipe: every bug_fix variant across levels 1..5 (higher
# levels add the decoy function, teaching read-before-fix)
DEFAULT_VARIANTS = tuple(range(5))
DEFAULT_LEVELS = (1, 2, 3, 4, 5)


class ScriptedDemonstrator(FakeModelProvider):
    """A turn-scripted perfect fixer for one declared curriculum defect.

    Script: inspect -> run tests (fail) -> surgical edit -> run tests
    (pass) -> state the diagnosis. Model tag is `scripted-demo` so the
    recorded provenance is honest."""

    name = DEMO_MODEL_TAG
    model = DEMO_MODEL_TAG

    def __init__(self, module_file: str, test_command: str,
                 old_string: str, new_string: str, diagnosis: str):
        super().__init__([
            ToolCall(name="read_file", arguments={"path": module_file}),
            ToolCall(name="run_tests", arguments={"command": test_command}),
            ToolCall(name="edit_file", arguments={
                "path": module_file,
                "old_string": old_string,
                "new_string": new_string,
            }),
            ToolCall(name="run_tests", arguments={"command": test_command}),
            ModelResponse(text=diagnosis, finish_reason="stop"),
        ])


def _demonstrator_for(variant: int, level: int,
                      python: str) -> Tuple[ScriptedDemonstrator, dict, str]:
    """Build the demonstrator + fixture files + goal for one task."""
    module_code, test_code, goal, _failure, _skills, module, func = \
        _bug_fix_fixture(variant, level)
    _module, _func, good, bad = bug_fix_defect(variant)
    module_file = f"{module}.py"
    test_command = f'"{python}" -m unittest -v'
    diagnosis = (
        f"The test suite failed because {func} was implemented "
        f"incorrectly: the body was `{bad.strip()}` instead of "
        f"`{good.strip()}`. I replaced the defective line and the "
        f"tests pass.")
    provider = ScriptedDemonstrator(
        module_file=module_file, test_command=test_command,
        old_string=bad, new_string=good, diagnosis=diagnosis)
    files = {module_file: module_code, f"test_{module}.py": test_code}
    return provider, files, goal


def build_corpus(experience_store: ExperienceStore,
                 python: str, variants: Tuple[int, ...] = DEFAULT_VARIANTS,
                 levels: Tuple[int, ...] = DEFAULT_LEVELS
                 ) -> Dict[str, Any]:
    """Run every (variant, level) demonstrator through the benchmark;
    each verified pass is recorded with the S63 session-unique goal
    suffix. Returns honest stats; failures are kept as failed
    trajectories, never hidden."""
    import sys

    python = python or sys.executable
    stats: Dict[str, Any] = {"runs": 0, "passed": 0, "failed": 0,
                             "durations_s": 0.0, "tasks": []}
    for variant in variants:
        for level in levels:
            provider, files, goal = _demonstrator_for(variant, level, python)

            def fixture_writer(ws, _files=files):
                for name, content in _files.items():
                    (ws.root / name).write_text(content, encoding="utf-8")

            report = run_benchmark(provider, fixture_writer=fixture_writer,
                                   goal=goal,
                                   experience_store=experience_store)
            stats["runs"] += 1
            stats["durations_s"] += report.duration_seconds
            if report.success:
                stats["passed"] += 1
            else:
                stats["failed"] += 1
            stats["tasks"].append({
                "variant": variant, "level": level, "goal": goal,
                "success": report.success,
                "iterations": report.iterations,
                "termination": report.termination_reason,
            })
    return stats


# --- training kit export -------------------------------------------------

_TRAIN_SCRIPT = '''"""baby-agent:ep1 — QLoRA SFT over the exported S63 training corpus.

Run this OUTSIDE the qacompanion repo (Colab T4 / Kaggle GPU / any CUDA
box). qacompanion itself stays stdlib-only; these dependencies belong to
the training environment only.

    pip install -U transformers peft datasets trl bitsandbytes

Inputs: training.jsonl (S63 chat records: {"messages": [...],
"metadata": {...}}). Output: a LoRA adapter merged into a GGUF for
ollama, named baby-agent:ep1.

The honesty rule (docs/s64-spec.md): ep1 is NEVER assumed better —
evaluate with the repo's own harness and compare():
    run_evaluation([base_provider, OllamaProvider(model="baby-agent:ep1")])
    compare(...)  # regressions are documented, not shipped silently
"""

import json
import sys

BASE_MODEL = "Qwen/Qwen2.5-Coder-3B-Instruct"
DATASET = "training.jsonl"
OUTPUT_DIR = "ep1-adapter"


def load_dataset(path=DATASET):
    rows = [json.loads(line) for line in open(path, encoding="utf-8")
            if line.strip()]
    if not rows:
        sys.exit(f"no training records in {path} — run 'qa curate' and "
                 "'qa build-training' first")
    return rows


def main():
    from datasets import Dataset
    from peft import LoraConfig, get_peft_model
    from trl import SFTConfig, SFTTrainer

    rows = load_dataset()
    print(f"training records: {len(rows)}")
    dataset = Dataset.from_list([r["messages"] for r in rows])

    config = SFTConfig(
        output_dir=OUTPUT_DIR,
        per_device_train_batch_size=2,
        gradient_accumulation_steps=4,
        num_train_epochs=3,
        learning_rate=2e-4,
        bf16=True,
        logging_steps=1,
        report_to=[],
    )
    lora = LoraConfig(
        r=16, lora_alpha=32, lora_dropout=0.05,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
        task_type="CAUSAL_LM",
    )

    from transformers import AutoModelForCausalLM, AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL, torch_dtype="bfloat16", device_map="auto")
    model = get_peft_model(model, lora)
    model.print_trainable_parameters()

    trainer = SFTTrainer(
        model=model,
        args=config,
        train_dataset=dataset,
        processing_class=tokenizer,
    )
    trainer.train()
    trainer.save_model(OUTPUT_DIR)
    print("adapter saved to", OUTPUT_DIR)
    print("next: merge + convert to GGUF, `ollama create baby-agent:ep1`,")
    print("then evaluate with run_evaluation + compare() — honestly.")


if __name__ == "__main__":
    main()
'''

_TRAIN_README = '''# baby-agent:ep1 training kit

qacompanion stays stdlib-only — this kit runs on EXTERNAL free compute
(no billing, same ruling as the Gemini free tier):

- **Google Colab** (free T4): upload `training.jsonl` +
  `train_ep1.py`, `pip install -U transformers peft datasets trl
  bitsandbytes`, run the script.
- **Kaggle** (free 30 GPU-hours/week): same two files, P100/T4 kernel.

## The loop (roadmap §S64)

1. `qa curate && qa build-training` in the repo -> `training/training.jsonl`
2. train on external compute -> LoRA adapter
3. merge adapter -> GGUF -> `ollama create baby-agent:ep1 -f Modelfile`
4. evaluate HONESTLY with the repo harness (S57):
   base vs ep1 on the identical model x task cross product;
   `compare()` flags regressions AND improvements per task
5. a generation that forgets old lessons is documented, not shipped
   silently (roadmap honesty rule)

## Provenance

The corpus is tagged: `scripted-demo` records are scripted curriculum
demonstrations (real loop, real test execution, declared defects);
model-tagged records come from real provider runs. ep1 trained on
scripted demos teaches protocol and procedure — the S55 finding says
that is exactly what general small models lack.
'''


def format_demonstration(goal: str, steps: List[Dict[str, Any]],
                         final_answer: Optional[str],
                         model: Optional[str]) -> Optional[str]:
    """S64 slice 2 (ep0.5): render a verified experience as a worked
    example the model can imitate in-context — the adaptation half of
    "fine-tune / adapt", no gradients required. Bounded: <=6 steps,
    capped result heads. Returns None when there is nothing to show."""
    if not steps:
        return None
    lines = [f"## Worked example (provenance: {model or 'unknown'})",
             f"Goal: {str(goal)[:200]}"]
    for index, step in enumerate(steps[:6], 1):
        if not isinstance(step, dict) or not isinstance(
                step.get("args"), dict):
            continue
        lines.append(f"{index}. {format_tool_call(step['tool'], step['args'])}")
        head = str(step.get("result_head") or "")[:160]
        if head:
            lines.append(f"   -> {head}")
    final = (final_answer or "").strip()
    if final:
        lines.append(f"Final answer: {final[:300]}")
    return "\n".join(lines)


def export_training_kit(out_dir=None) -> Dict[str, str]:
    """Write the self-contained training kit (files, no dependencies
    added to qacompanion)."""
    from pathlib import Path

    directory = Path(out_dir or "training-kit")
    directory.mkdir(parents=True, exist_ok=True)
    paths = {
        "train_ep1.py": _TRAIN_SCRIPT,
        "README.md": _TRAIN_README,
    }
    for name, content in paths.items():
        (directory / name).write_text(content, encoding="utf-8",
                                      newline="")
    return {"out_dir": str(directory), "files": sorted(paths)}


def format_corpus_report(stats: Dict[str, Any]) -> str:
    lines = [
        "ep1 corpus report:",
        f"  runs: {stats['runs']} (passed: {stats['passed']}, "
        f"failed: {stats['failed']})",
        f"  total duration: {stats['durations_s']:.1f}s",
    ]
    for task in stats["tasks"]:
        if not task["success"]:
            lines.append(f"  FAILED variant={task['variant']} "
                         f"level={task['level']}: "
                         f"{task['termination']}")
    if stats["passed"] == stats["runs"]:
        lines.append("  all demonstrations verified")
    return "\n".join(lines)
