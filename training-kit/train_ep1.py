"""baby-agent:ep1 — QLoRA SFT over the exported S63 training corpus.

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
