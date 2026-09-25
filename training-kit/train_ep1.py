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
# optional base model: `python train_ep1.py ep11
# Qwen/Qwen2.5-Coder-7B-Instruct` (S79; default: the 3B)
GEN = sys.argv[1] if len(sys.argv) > 1 else "ep1"
BASE_MODEL = (sys.argv[2] if len(sys.argv) > 2
              else "Qwen/Qwen2.5-Coder-3B-Instruct")
SEVEN_B = "7B" in BASE_MODEL
DATASET = "training.jsonl"
OUTPUT_DIR = f"{GEN}-adapter"
MERGED_DIR = f"{GEN}-merged"


KIT_VERSION = "s83"


def load_dataset(path=DATASET):
    rows = [json.loads(line) for line in open(path, encoding="utf-8")
            if line.strip()]
    if not rows:
        sys.exit(f"no training records in {path} — run 'qa curate' and "
                 "'qa build-training' first")
    return rows


def main():
    import torch
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
        """S76.3: normalize EVERY apply_chat_template return shape to a
        flat python list of ints. Observed v5 shapes: dict, batched
        nested lists, tensors, list-wrapped tensors, and — the one that
        defeated two flatten attempts — a BatchEncoding (UserDict, so
        isinstance-dict is False; it SLICES like a batch, so every
        render read as a batch of exactly 1). The input_ids key comes
        FIRST because it is the BatchEncoding contract."""
        for _ in range(6):
            if hasattr(rendered, "input_ids"):
                rendered = rendered["input_ids"]
            elif isinstance(rendered, dict):
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

    def _ids(text):
        return _to_flat_token_ids(tokenizer(text,
                                            add_special_tokens=False))

    def _manual_masked_example(messages):
        """Fallback (used only if the template path yields no assistant
        tokens): construct the Qwen2.5 chat format explicitly —
        <|im_start|>role {content} <|im_end|> — with no
        apply_chat_template involved. Same segment layout the template
        produces for this model family. (The \n after each segment is
        written as an escape so the generated script tokenizes the
        newline the template emits.)"""
        input_ids: list = []
        labels: list = []
        for message in messages:
            seg = _ids(f"<|im_start|>{message['role']}\n")
            body = _ids(message["content"])
            end = _ids("<|im_end|>\n")
            input_ids.extend(seg + body + end)
            if message["role"] == "assistant":
                labels.extend(seg + body + end)
            else:
                labels.extend([-100] * (len(seg) + len(body) + len(end)))
        assistant_tokens = sum(1 for l in labels if l != -100)
        return {"input_ids": input_ids, "labels": labels},             assistant_tokens, len(labels)

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

    def build_all(mode):
        masked = []
        a_total = t_total = 0
        for r in rows:
            if mode == "template":
                example, a, t = masked_example(r["messages"])
            else:
                example, a, t = _manual_masked_example(r["messages"])
            masked.append(example)
            a_total += a
            t_total += t
        return masked, a_total, t_total

    masked_rows, total_assistant, total_tokens = build_all("template")
    ratio = total_assistant / max(total_tokens, 1)
    mode_used = "template"
    if ratio < 0.10:
        # the template path is broken under this transformers version —
        # rebuild the whole dataset with the explicit manual format so
        # one broken API cannot silently produce an untrained model
        print("template path yielded no assistant tokens — falling back "
              "to manual Qwen-format construction")
        first_render_shapes.append("fallback-manual")
        masked_rows, total_assistant, total_tokens = build_all("manual")
        ratio = total_assistant / max(total_tokens, 1)
        mode_used = "manual"
    print(f"mask path: {mode_used} | assistant-token ratio: "
          f"{ratio:.3f} ({total_assistant:,}/{total_tokens:,})")
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
        per_device_train_batch_size=(1 if SEVEN_B else 2),
        gradient_accumulation_steps=(8 if SEVEN_B else 4),
        num_train_epochs=3,
        learning_rate=2e-4,
        fp16=True,                      # T4 (Turing) has no bf16
        gradient_checkpointing=True,
        # S81: 7B needs checkpointing too (was `not SEVEN_B`, which
        # disabled the main activation saver on the hungriest path).
        # LoRA + checkpointing: frozen embeddings break the default
        # (reentrant) checkpoint implementation. The 4-bit path
        # checkpoint via prepare_model_for_kbit_training instead.
        gradient_checkpointing_kwargs={"use_reentrant": False},
        logging_steps=1,
        report_to=[],
        # S76: the dataset is pre-tokenized with labels — TRL must not
        # re-apply its own (unmasked) preparation
        dataset_kwargs={"skip_prepare_dataset": True},
        # S79: the 4-bit path wants the paged optimizer (adamw_torch is
        # right for the 3B fp16 path). optim is a TrainingArguments/
        # SFTConfig field — NOT an SFTTrainer kwarg (Colab catch).
        optim=("paged_adamw_32bit" if SEVEN_B else "adamw_torch"),
    )
    lora = LoraConfig(
        r=16, lora_alpha=32, lora_dropout=0.05,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
        task_type="CAUSAL_LM",
    )

    if SEVEN_B:
        # S79: 7B fp16 (~14GB) does not fit the free T4's 16GB with
        # activations — 4-bit QLoRA is the standard free-T4 7B setup
        from transformers import BitsAndBytesConfig
        # S83: real torch.dtype objects — the "float16" STRINGS were
        # silently unconverted on the Colab stack, so bnb compute fell
        # back to the model default (bf16) and bf16 grads reached the
        # fp16 GradScaler (NotImplementedError THROUGH the S79 fix).
        bnb = BitsAndBytesConfig(
            load_in_4bit=True, bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_use_double_quant=True)
        # torch_dtype MUST be fp16: Qwen2.5-7B's config defaults to
        # bfloat16, and on Turing (T4) bf16 is unsupported — the AMP
        # GradScaler then chokes on bf16 grads
        # (NotImplementedError: _amp_foreach_non_finite_check_and_unscale_
        # cuda not implemented for BFloat16 — Colab catch, S79; object
        # form pinned S83)
        model = AutoModelForCausalLM.from_pretrained(
            BASE_MODEL, quantization_config=bnb, torch_dtype=torch.float16,
            device_map="auto")
        # S81 lean prepare (T4 OOM fix): full
        # prepare_model_for_kbit_training upcasts norms to fp32 (+1GB
        # transient, peft #3265/#3293) and OOMs at
        # param.data.to(torch.float32) with 12+GB already allocated.
        # Lean path: skip the upcast/checkpoint wrapper here, enable
        # checkpointing manually (maintainer-sanctioned for constrained
        # GPUs), disable use_cache, and clear the allocator cache.
        # 7B-only, fail loudly — no silent 3B fallback (S79 attribution).
        import gc as _gc
        import torch as _torch
        _gc.collect()
        if _torch.cuda.is_available():
            _torch.cuda.empty_cache()
        from peft import prepare_model_for_kbit_training
        model = prepare_model_for_kbit_training(
            model, use_gradient_checkpointing=False)
        model.gradient_checkpointing_enable(
            gradient_checkpointing_kwargs={"use_reentrant": False})
        model.config.use_cache = False
        if _torch.cuda.is_available():
            _torch.cuda.empty_cache()
    else:
        model = AutoModelForCausalLM.from_pretrained(
            BASE_MODEL, torch_dtype="float16")
    # S83 dtype audit gate (Colab bf16 catch): the GradScaler crash
    # names no module, so assert the evidence HERE — versions, the
    # effective model dtype, and every bf16 param — before LoRA and
    # before the trainer. A single bf16 param on a T4 build refuses
    # loudly instead of dying 8 frames deep in torch/amp.
    try:
        import transformers as _tf_mod
        import peft as _peft_mod
        print(f"versions: transformers={_tf_mod.__version__} "
              f"peft={_peft_mod.__version__} torch={torch.__version__}")
    except Exception as _ver_exc:
        print(f"version probe failed: {_ver_exc}")
    try:
        import bitsandbytes as _bnb_mod
        print(f"bitsandbytes={_bnb_mod.__version__}")
    except Exception as _bnb_exc:
        print(f"bitsandbytes probe failed: {_bnb_exc}")
    _bf16 = sorted({f"{_n}:{_p.dtype}"
                    for _n, _p in model.named_parameters()
                    if "bfloat16" in str(_p.dtype)})
    print(f"dtype audit: model.dtype={model.dtype} "
          f"bf16_params={len(_bf16)}")
    for _line in _bf16[:10]:
        print(f"  bf16: {_line}")
    if _bf16:
        sys.exit("DTYPE GATE FAILED: bf16 params present on a T4 build "
                 "— paste the versions + bf16 list above; do not train")
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
