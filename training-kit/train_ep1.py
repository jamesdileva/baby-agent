"""baby-agent:ep1 — QLoRA SFT over the exported S63 training corpus.

Run this OUTSIDE the qacompanion repo (Colab T4 / Kaggle GPU / any CUDA
box). qacompanion itself stays stdlib-only; these dependencies belong to
the training environment only.

    pip install -U transformers peft datasets trl accelerate

Inputs: training.jsonl (S63 chat records: {"messages": [...],
"metadata": {...}}). Output: ep1-merged/ — the base model WITH the
adapter baked in, ready for `ollama create` (or GGUF conversion).

The honesty rule (docs/s64-spec.md): ep1 is NEVER assumed better —
evaluate with the repo's own harness and compare():
    run_evaluation([base_provider, OllamaProvider(model="baby-agent:ep1")])
    compare(...)  # regressions are documented, not shipped silently

T4 note: Turing GPUs have no bf16 — this script trains in fp16 with
gradient checkpointing (free Colab T4 = 16 GB, plenty for a 3B QLoRA).
"""

import json
import sys

# optional generation name: `python train_ep1.py ep8` produces
# ep8-adapter/ and ep8-merged/ (default: ep1)
GEN = sys.argv[1] if len(sys.argv) > 1 else "ep1"
BASE_MODEL = "Qwen/Qwen2.5-Coder-3B-Instruct"
DATASET = "training.jsonl"
OUTPUT_DIR = f"{GEN}-adapter"
MERGED_DIR = f"{GEN}-merged"


KIT_VERSION = "s76.2"


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
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from trl import SFTConfig, SFTTrainer

    print(f"kit version: {KIT_VERSION}")
    rows = load_dataset()
    print(f"training records: {len(rows)}")

    # S76 ASSISTANT-ONLY LOSS (gen-8's one variable): the gen-5 verdict
    # showed most gradient mass teaching the model to predict
    # ENVIRONMENT output (user/observation turns) — imitation then
    # concentrated on the narrative. Build labels with every
    # non-assistant span at -100 so the loss trains ONLY on the
    # model's own behavior: [TOOL: ...] calls and final answers.
    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    first_render_shapes: list = []

    def _to_flat_token_ids(rendered):
        """S76.2: normalize EVERY apply_chat_template return shape to a
        flat python list of ints. v5 has been seen returning dicts,
        batched nested lists, and — the shape that defeated two
        flatten attempts — a LIST WRAPPING A TENSOR ([tensor([[...]])]):
        the outer list has no .tolist() and its element is not a
        list/tuple, so len() is always 1 and every render diffs to
        empty. Unwrap one-element wrappers, convert tensor/numpy via
        .tolist(), collapse nesting — bounded so a pathological shape
        fails loudly instead of hanging."""
        for _ in range(6):
            if isinstance(rendered, dict):
                rendered = rendered["input_ids"]
            elif hasattr(rendered, "tolist"):
                rendered = rendered.tolist()
            elif isinstance(rendered, (list, tuple)) and len(rendered) == 1:
                rendered = rendered[0]
            elif isinstance(rendered, (list, tuple)) and rendered                     and isinstance(rendered[0], (list, tuple)):
                rendered = rendered[0]
            elif isinstance(rendered, int):
                rendered = [rendered]
            else:
                break
        return rendered

    def masked_example(messages):
        """Render the conversation incrementally through the joint chat
        template (per-message rendering would corrupt the stream: Qwen
        injects a default system block into every render that lacks
        one) and attribute each new token to the message that
        introduced it."""
        input_ids: list = []
        labels: list = []
        prev_len = 0
        for index, message in enumerate(messages):
            raw = tokenizer.apply_chat_template(
                messages[:index + 1], tokenize=True)
            full = _to_flat_token_ids(raw)
            if index == 0:
                first_render_shapes.append(type(raw).__name__)
            new_tokens = full[prev_len:]
            prev_len = len(full)
            input_ids.extend(new_tokens)
            if message["role"] == "assistant":
                labels.extend(new_tokens)
            else:
                labels.extend([-100] * len(new_tokens))
        assistant_tokens = sum(1 for l in labels if l != -100)
        return ({"input_ids": input_ids, "labels": labels},
                assistant_tokens, len(labels))

    masked_rows = []
    total_assistant = 0
    total_tokens = 0
    for r in rows:
        example, a_tokens, all_tokens = masked_example(r["messages"])
        masked_rows.append(example)
        total_assistant += a_tokens
        total_tokens += all_tokens
    ratio = total_assistant / max(total_tokens, 1)
    print(f"assistant-token ratio: {ratio:.3f} "
          f"({total_assistant:,}/{total_tokens:,})")
    print(f"first-render shapes: {first_render_shapes[:3]}")
    if ratio < 0.10:
        # a broken mask would train on nothing — refuse like the
        # sanity generation gate does
        sys.exit("MASK GATE FAILED: assistant-token ratio under 10% — "
                 f"the label masking is broken (raw render shapes: "
                 f"{first_render_shapes[:3]}); do not train")
    dataset = Dataset.from_list(masked_rows)

    config = SFTConfig(
        output_dir=OUTPUT_DIR,
        per_device_train_batch_size=2,
        gradient_accumulation_steps=4,
        num_train_epochs=3,
        learning_rate=2e-4,
        fp16=True,                      # T4 (Turing) has no bf16
        gradient_checkpointing=True,
        # LoRA + checkpointing: frozen embeddings break the default
        # (reentrant) checkpoint implementation
        gradient_checkpointing_kwargs={"use_reentrant": False},
        logging_steps=1,
        report_to=[],
        # S76: the dataset is pre-tokenized with labels — TRL must not
        # re-apply its own (unmasked) preparation
        dataset_kwargs={"skip_prepare_dataset": True},
    )
    lora = LoraConfig(
        r=16, lora_alpha=32, lora_dropout=0.05,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
        task_type="CAUSAL_LM",
    )

    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL, torch_dtype="float16")
    model = get_peft_model(model, lora)
    model.print_trainable_parameters()

    from transformers import DataCollatorForSeq2Seq
    trainer = SFTTrainer(
        model=model,
        args=config,
        train_dataset=dataset,
        processing_class=tokenizer,
        data_collator=DataCollatorForSeq2Seq(
            tokenizer, model=model, label_pad_token_id=-100),
    )
    trainer.train()
    trainer.save_model(OUTPUT_DIR)
    print("adapter saved to", OUTPUT_DIR)

    # merge the adapter into the base so ollama (or llama.cpp) can take
    # the WHOLE model without any adapter dance
    merged = model.merge_and_unload()
    merged.save_pretrained(MERGED_DIR)
    tokenizer.save_pretrained(MERGED_DIR)

    # DISK-LEVEL fixup (the first ep1 verdict attempt, 2026-09-11):
    # in-memory config edits do NOT survive transformers v5's save —
    # it re-tied the head and wrote rope_theta in a new config format
    # ollama's converter cannot read (freq_base came out 0.0 and the
    # model emitted one repeated token). Patch the SAVED files:
    # explicit lm_head + legacy rope_theta key.
    import glob as _glob
    import json as _json
    from safetensors.torch import load_file as _load, save_file as _save
    for shard in _glob.glob(f"{MERGED_DIR}/*.safetensors"):
        state = _load(shard)
        if "model.embed_tokens.weight" in state                 and "lm_head.weight" not in state:
            state["lm_head.weight"] =                 state["model.embed_tokens.weight"].clone()
            _save(state, shard)
            print("fixup: lm_head made explicit in", shard)
    cfg_path = f"{MERGED_DIR}/config.json"
    cfg = _json.load(open(cfg_path, encoding="utf-8"))
    cfg["tie_word_embeddings"] = False
    cfg["rope_theta"] = (cfg.get("rope_theta")
                         or cfg.get("rope_parameters", {}).get("rope_theta")
                         or 1000000.0)
    _json.dump(cfg, open(cfg_path, "w", encoding="utf-8"), indent=2)
    print("fixup: tie_word_embeddings=False, rope_theta =",
          cfg["rope_theta"])

    # the honesty gate, in-process: never declare success on a model
    # that cannot speak — degenerate output ships silently otherwise
    inputs = tokenizer("The capital of France is", return_tensors="pt")
    out = merged.generate(**inputs, max_new_tokens=8, do_sample=False)
    text = tokenizer.decode(out[0], skip_special_tokens=True)
    print("SANITY GENERATION:", repr(text))
    body = text.lower().replace("the capital of france is", "").strip()
    if not body or len(set(body)) <= 2:
        print("DEGENERATE OUTPUT DETECTED — the model cannot speak. "
              "Do NOT download this model: check the loss curve above; "
              "typical fixes are lower learning rate (1e-4) or fewer "
              "epochs. Record the attempt as failed (roadmap honesty "
              "rule).")
        sys.exit(1)
    print(f"next: convert {MERGED_DIR} to GGUF with llama.cpp and "
          f"`ollama create baby-agent:{GEN}` — exact commands in "
          "training-kit/README.md (ollama 0.34.4+ requires the GGUF "
          "path),")
    print("then evaluate with qa verdict — honestly.")


if __name__ == "__main__":
    main()
