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


KIT_VERSION = "s89"


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
        # S88: NO grad clipping on the 7B path. torch 2.11's
        # GradScaler.unscale_() RAISES on fp16 grads ("Attempting to
        # unscale FP16 gradients" — the allow_fp16=False clip path),
        # and the trainer clips via accelerate's clip_grad_norm_ ->
        # unscale_ before every step. (S89: with fp32 adapters the
        # clip path would pass, but 0 stays — one change per slice,
        # and _get_grad_norm's inf-clip is pointless work anyway.
        # Restoring 1.0 is a candidate follow-up once ep11 trains.)
        # 3B keeps 1.0 (proven path untouched).
        max_grad_norm=(0 if SEVEN_B else 1.0),
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
        # form pinned S83; v5 kwarg name pinned S84 — 5.17 prints
        # "`torch_dtype` is deprecated! Use `dtype` instead!" and the
        # deprecated spelling loaded float32, i.e. it NO-OPs)
        import inspect as _inspect
        _fp_kwargs = ({"dtype": torch.float16}
                      if "dtype" in _inspect.signature(
                          AutoModelForCausalLM.from_pretrained).parameters
                      else {"torch_dtype": torch.float16})
        model = AutoModelForCausalLM.from_pretrained(
            BASE_MODEL, quantization_config=bnb, device_map="auto",
            **_fp_kwargs)
        # belt and suspenders: the config default (bf16) leaks into
        # adapter dtypes and compute fallbacks if left in place
        model.config.torch_dtype = torch.float16
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
          f"config.torch_dtype={model.config.torch_dtype} "
          f"bf16_params={len(_bf16)}")
    for _line in _bf16[:10]:
        print(f"  bf16: {_line}")
    # the compute dtype is the other silent fallback: print the
    # EFFECTIVE value (post-load config), not what was requested
    _qconf = getattr(model.config, "quantization_config", None)
    if isinstance(_qconf, dict):
        _eff_compute = _qconf.get("bnb_4bit_compute_dtype")
    else:
        _eff_compute = getattr(_qconf, "bnb_4bit_compute_dtype", None)
    if _eff_compute is None:
        _hq = getattr(model, "hf_quantizer", None)
        _eff_compute = getattr(
            getattr(_hq, "quantization_config", None),
            "bnb_4bit_compute_dtype", None)
    print(f"dtype audit: effective bnb_4bit_compute_dtype={_eff_compute}")
    if _bf16:
        sys.exit("DTYPE GATE FAILED: bf16 params present on a T4 build "
                 "— paste the versions + bf16 list above; do not train")
    if "bfloat16" in str(_eff_compute).lower():
        sys.exit("DTYPE GATE FAILED: bnb compute dtype resolved to bf16 "
                 "— paste the versions + effective dtype above; do not "
                 "train")
    model = get_peft_model(model, lora)
    # second gate, post-LoRA: adapters inherit dtypes from wherever
    # they please (config default, target modules) — census them too,
    # since the S83 crash arrived with a CLEAN pre-LoRA audit and died
    # at the first backward
    _lora_dtypes = sorted({f"{_n}:{_p.dtype}"
                           for _n, _p in model.named_parameters()
                           if "lora_" in _n})
    _bf16_post = [_d for _d in _lora_dtypes if "bfloat16" in _d]
    print(f"dtype audit: lora_params={len(_lora_dtypes)} "
          f"bf16_lora={len(_bf16_post)}")
    for _line in _bf16_post[:10]:
        print(f"  bf16 lora: {_line}")
    if _bf16_post:
        sys.exit("DTYPE GATE FAILED: bf16 LoRA adapters on a T4 build "
                 "— paste the versions + bf16 lora list above; do not "
                 "train")
    if SEVEN_B:
        # S85 setup-time bf16 hunt: the S84 audit proved params,
        # adapters AND bnb compute clean, yet bf16 grads STILL reached
        # the scaler — so the source is runtime, not weights (the
        # process autocast default is the prime suspect on torch 2.11).
        # One micro-batch forward+backward under explicit fp16 autocast
        # censuses grad dtypes BY NAME, then zeroes everything. Either
        # outcome diagnoses: bf16 here = a rogue explicit-bf16 op;
        # clean here + trainer crash = the trainer's autocast default
        # is bf16 (pinned below for the run).
        try:
            _ac_dtype = torch.get_autocast_dtype("cuda")
        except Exception as _ac_exc:
            _ac_dtype = f"probe failed: {_ac_exc}"
        print(f"autocast probe: default cuda autocast dtype={_ac_dtype}")
        if "bfloat16" in str(_ac_dtype).lower():
            for _setter in ("set_autocast_dtype",
                            "set_autocast_gpu_dtype"):
                _fn = getattr(torch, _setter, None)
                if _fn is None:
                    continue
                try:
                    try:
                        _fn("cuda", torch.float16)
                    except TypeError:
                        _fn(torch.float16)
                    print(f"autocast probe: pinned fp16 via "
                          f"torch.{_setter}")
                    break
                except Exception as _pin_exc:
                    print(f"autocast probe: torch.{_setter} failed: "
                          f"{_pin_exc}")
        try:
            _pdev = getattr(model, "device", None)
            if _pdev is None:
                _pdev = next(model.parameters()).device
            _ptok = tokenizer("Probe the dtype census.",
                              return_tensors="pt").to(_pdev)
            with torch.amp.autocast("cuda", dtype=torch.float16):
                _out = model(input_ids=_ptok["input_ids"],
                             labels=_ptok["input_ids"])
            _out.loss.backward()
            _ghist = {}
            _bf16_grads = []
            for _n, _p in model.named_parameters():
                if _p.grad is None:
                    continue
                _gdt = str(_p.grad.dtype)
                _ghist[_gdt] = _ghist.get(_gdt, 0) + 1
                if "bfloat16" in _gdt:
                    _bf16_grads.append(f"{_n}:{_p.grad.dtype}")
            print(f"autocast probe: grad dtype histogram={_ghist}")
            for _line in _bf16_grads[:10]:
                print(f"  bf16 grad: {_line}")
            if _bf16_grads:
                sys.exit("GRAD GATE FAILED: bf16 grads from a clean "
                         "audit — paste the autocast + histogram lines "
                         "above; do not train")
            model.zero_grad()
            del _out, _ptok
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except SystemExit:
            raise
        except Exception as _probe_exc:
            print(f"autocast probe: census skipped: {_probe_exc}")
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
    # S89 adapter dtype (THE fix, from the S88 census): torch 2.11's
    # GradScaler.unscale_() — the clip AND norm-logging path — rejects
    # fp16 grads (ValueError) and lacks a bf16 kernel on sm75
    # (NotImplementedError); fp32 grads pass fine. So the adapters
    # must be FP32, not fp16: the S86 census caught construction
    # casting them fp32->bf16, the S87 cast fp16-fixed the bf16 crash
    # only to meet the fp16 crash. Cast every lora_ param to fp32
    # AFTER SFTTrainer construction (post-construction casts stick —
    # the S87 fp16 census held) with an attesting print. This is the
    # standard mixed-precision recipe: fp32 master weights, fp16
    # compute. 161MB for 40M params — negligible on the T4.
    _cast_n = 0
    for _n, _p in model.named_parameters():
        if "lora_" in _n and str(_p.dtype) != "torch.float32":
            _p.data = _p.data.to(torch.float32)
            _cast_n += 1
    print(f"adapter cast: {_cast_n} lora params -> torch.float32")
    # S86 precision flags (always printed, near-free): what the
    # trainer THINKS it runs — the S85 probe proved the model side
    # clean, so a bf16-leaning trainer/accelerator config is the last
    # unobserved actor
    try:
        _acc = trainer.accelerator
        print(f"precision flags: fp16={config.fp16} bf16={config.bf16} "
              f"half_precision_backend="
              # S87: SFTConfig on transformers 5.17 has NO
              # half_precision_backend (caught live) — getattr, not boom
              f"{getattr(config, 'half_precision_backend', 'n/a')} "
              f"accelerator.mixed_precision="
              f"{getattr(_acc, 'mixed_precision', 'n/a')} "
              f"scaler_enabled="
              f"{getattr(getattr(_acc, 'scaler', None), '_enabled', 'n/a')}")
    except Exception as _flag_exc:
        print(f"precision flags: probe failed: {_flag_exc}")
    # S86 failure-path census: the S85 crash arrived with 392 fp32
    # grads and STILL died on a bf16 group inside the scaler, and
    # Colab collapses the middle traceback frames — so on
    # NotImplementedError, name every bf16 tensor IN SITU (params,
    # grads, autocast default, config) and re-raise. Zero cost when
    # green; the whole diagnosis when red. (S88: also catches
    # ValueError — torch 2.11's unscale_ rejects fp16 grads on the
    # clip path, same fail-loud treatment.)
    try:
        trainer.train()
    except (NotImplementedError, ValueError):
        print("FAILURE CENSUS (trainer died in torch/amp — naming "
              "every bf16 tensor):")
        try:
            _phist = {}
            for _n, _p in model.named_parameters():
                _phist[str(_p.dtype)] = _phist.get(str(_p.dtype), 0) + 1
            print(f"failure census: param dtype histogram={_phist}")
            for _n, _p in model.named_parameters():
                if "bfloat16" in str(_p.dtype):
                    print(f"  bf16 param: {_n}:{_p.dtype}")
        except Exception as _cen_exc:
            print(f"failure census: param scan failed: {_cen_exc}")
        try:
            _ghist2 = {}
            for _n, _p in model.named_parameters():
                if _p.grad is None:
                    continue
                _gdt = str(_p.grad.dtype)
                _ghist2[_gdt] = _ghist2.get(_gdt, 0) + 1
            print(f"failure census: grad dtype histogram={_ghist2}")
            for _n, _p in model.named_parameters():
                if (_p.grad is not None
                        and "bfloat16" in str(_p.grad.dtype)):
                    print(f"  bf16 grad: {_n}:{_p.grad.dtype}")
        except Exception as _cen_exc2:
            print(f"failure census: grad scan failed: {_cen_exc2}")
        try:
            print(f"failure census: autocast default="
                  f"{torch.get_autocast_dtype('cuda')} "
                  f"config.torch_dtype={model.config.torch_dtype}")
        except Exception as _cen_exc3:
            print(f"failure census: misc probe failed: {_cen_exc3}")
        raise
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
