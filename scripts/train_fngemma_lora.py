"""Fine-tune Function Gemma 270M for FRIDAY tool calling.

Differences from ``scripts/train_gemma_lora.py`` (read that first):

1. Different base model — Function Gemma uses Google's tool-call-tuned
   variant of the 270M base. The HF id below is a placeholder; verify
   against the published model card before running and override via
   ``--model-id`` if needed.

2. Custom chat template — Function Gemma's ``developer`` role is not in
   Unsloth's preset list. We register a minimal Jinja template that
   matches the format used in ``scripts/format_for_finetune.py``.

3. Special-token check — the LoRA only converges quickly if
   ``<start_function_call>`` and ``<end_function_call>`` are SINGLE
   tokens in the tokenizer. We probe at startup and add them as special
   tokens (resizing embeddings) when they aren't, so the envelope is one
   atomic unit during training.

4. Larger ``max_seq_length`` (2048) because the developer turn carries
   the full tool schema (~1,700 tokens for 49 tools).

Outputs::

    models/functiongemma-270m-it-friday/         # merged HF checkpoint
    models/functiongemma-270m-it-friday/*.gguf   # quantized
    models/functiongemma-270m-it-Q4_K_M.gguf     # symlink for the bench

Usage::

    python scripts/train_fngemma_lora.py
    python scripts/train_fngemma_lora.py --model-id google/functiongemma-270m-it
    python scripts/train_fngemma_lora.py --skip-gguf   # iterate fast
"""
from __future__ import annotations


def _relaunch_under_project_venv() -> None:
    import os
    import sys

    if os.environ.get("FRIDAY_SKIP_VENV_AUTOEXEC") == "1":
        return
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    venv_root = os.path.join(repo_root, ".venv")
    if os.name == "nt":
        candidate = os.path.join(venv_root, "Scripts", "python.exe")
    else:
        candidate = os.path.join(venv_root, "bin", "python3")
        if not os.path.exists(candidate):
            candidate = os.path.join(venv_root, "bin", "python")
    if not os.path.exists(candidate):
        return
    try:
        already = os.path.realpath(sys.prefix) == os.path.realpath(venv_root)
    except OSError:
        already = False
    if already:
        return
    if os.environ.get("_FRIDAY_VENV_RELAUNCHED") == "1":
        return
    os.environ["_FRIDAY_VENV_RELAUNCHED"] = "1"
    os.execv(candidate, [candidate, *sys.argv])


_relaunch_under_project_venv()


import argparse
import os
import shutil
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TRAIN_JSONL = REPO / "tests" / "datasets" / "train.fngemma.jsonl"
OUT_DIR     = REPO / "models" / "functiongemma-270m-it-friday"
GGUF_TARGET = REPO / "models" / "functiongemma-270m-it-Q4_K_M.gguf"


# =====================================================================
# Function Gemma chat template — handwritten because Unsloth's presets
# don't include the ``developer`` role used by Google's tool-call tune.
# Roles emitted: developer, user, model. The closing
# ``<start_of_turn>model\n`` is added when ``add_generation_prompt=True``
# so inference matches training.
# =====================================================================
FN_CHAT_TEMPLATE = (
    "{% for m in messages %}"
    "<start_of_turn>{{ m['role'] }}\n{{ m['content'] }}<end_of_turn>\n"
    "{% endfor %}"
    "{% if add_generation_prompt %}<start_of_turn>model\n{% endif %}"
)

ENVELOPE_OPEN  = "<start_function_call>"
ENVELOPE_CLOSE = "<end_function_call>"


DEFAULTS = dict(
    model_id="unsloth/functiongemma-270m-it",   # matches install_gemma_270m.py
    max_seq_length=2048,         # train.fngemma.jsonl max ≈ 1,707 tokens
    lora_r=16,
    lora_alpha=32,
    lora_dropout=0.05,
    epochs=3,
    per_device_batch=4,          # smaller than gemma — schema doubles seq len
    grad_accum=8,                # effective batch 32, same as gemma
    lr=2e-4,
    warmup_ratio=0.05,
    weight_decay=0.01,
    seed=42,
    quantization="q4_k_m",
)


def _check_prereqs() -> None:
    missing = []
    try:
        import unsloth  # noqa: F401
    except ImportError:
        missing.append("unsloth")
    try:
        import trl  # noqa: F401
    except ImportError:
        missing.append("trl")
    try:
        import datasets  # noqa: F401
    except ImportError:
        missing.append("datasets")
    if missing:
        print("Missing required packages: " + ", ".join(missing), file=sys.stderr)
        print("See scripts/train_gemma_lora.py docstring for install steps.", file=sys.stderr)
        sys.exit(1)


def _check_input(path: Path) -> None:
    if not path.exists():
        print(f"ERROR: training file missing: {path}", file=sys.stderr)
        print("Run: python scripts/format_for_finetune.py", file=sys.stderr)
        sys.exit(1)


def _ensure_envelope_tokens_atomic(tokenizer, model) -> bool:
    """If ``<start_function_call>`` or ``<end_function_call>`` tokenize
    to more than one piece, add them as special tokens and resize the
    model's embedding matrix. Returns True if anything changed.

    This MUST run before LoRA wrapping — otherwise resize_token_embeddings
    fails on the wrapped (PEFT) model.
    """
    needs_add: list[str] = []
    for tok in (ENVELOPE_OPEN, ENVELOPE_CLOSE):
        ids = tokenizer.encode(tok, add_special_tokens=False)
        if len(ids) != 1:
            needs_add.append(tok)
            print(f"[train-fn] envelope token {tok!r} encodes to {len(ids)} "
                  f"sub-tokens — will add as special.")
    if not needs_add:
        print("[train-fn] envelope tokens already atomic — no resize needed.")
        return False

    added = tokenizer.add_special_tokens({"additional_special_tokens": needs_add})
    print(f"[train-fn] added {added} special tokens; resizing embeddings.")
    model.resize_token_embeddings(len(tokenizer))
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model-id",       default=DEFAULTS["model_id"])
    ap.add_argument("--input",          type=Path, default=TRAIN_JSONL)
    ap.add_argument("--out",            type=Path, default=OUT_DIR)
    ap.add_argument("--max-seq-length", type=int, default=DEFAULTS["max_seq_length"])
    ap.add_argument("--lora-r",         type=int, default=DEFAULTS["lora_r"])
    ap.add_argument("--lora-alpha",     type=int, default=DEFAULTS["lora_alpha"])
    ap.add_argument("--lora-dropout",   type=float, default=DEFAULTS["lora_dropout"])
    ap.add_argument("--epochs",         type=int, default=DEFAULTS["epochs"])
    ap.add_argument("--batch",          type=int, default=DEFAULTS["per_device_batch"])
    ap.add_argument("--grad-accum",     type=int, default=DEFAULTS["grad_accum"])
    ap.add_argument("--lr",             type=float, default=DEFAULTS["lr"])
    ap.add_argument("--seed",           type=int, default=DEFAULTS["seed"])
    ap.add_argument("--quantization",   default=DEFAULTS["quantization"])
    ap.add_argument("--skip-gguf",      action="store_true")
    ap.add_argument("--gguf-target",    type=Path, default=GGUF_TARGET)
    args = ap.parse_args()

    _check_prereqs()
    _check_input(args.input)

    import torch
    from unsloth import FastLanguageModel
    from unsloth.chat_templates import train_on_responses_only
    from datasets import load_dataset
    from trl import SFTTrainer, SFTConfig

    # bf16 needs Ampere+ (compute capability >= 8.0). T4 / GTX-era cards
    # fall back to fp16 mixed precision; CPU runs in fp32.
    use_bf16 = torch.cuda.is_available() and torch.cuda.is_bf16_supported()
    use_fp16 = torch.cuda.is_available() and not use_bf16
    print(f"[train-fn] precision: bf16={use_bf16} fp16={use_fp16}")

    print(f"[train-fn] loading {args.model_id} (max_seq_length={args.max_seq_length}) …")
    t0 = time.perf_counter()
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=args.model_id,
        max_seq_length=args.max_seq_length,
        load_in_4bit=False,
        dtype=None,
    )
    print(f"[train-fn] base loaded in {time.perf_counter() - t0:.1f}s")

    # Envelope-token check MUST happen before LoRA wrapping (PEFT models
    # don't expose resize_token_embeddings).
    _ensure_envelope_tokens_atomic(tokenizer, model)

    # Custom Jinja template — supports the developer role.
    tokenizer.chat_template = FN_CHAT_TEMPLATE

    print(f"[train-fn] wrapping LoRA r={args.lora_r} alpha={args.lora_alpha} "
          f"dropout={args.lora_dropout}")
    model = FastLanguageModel.get_peft_model(
        model,
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=args.lora_dropout,
        target_modules=[
            "q_proj", "k_proj", "v_proj", "o_proj",
            "gate_proj", "up_proj", "down_proj",
        ],
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=args.seed,
    )

    # See train_gemma_lora.py for why we pre-tokenize in a plain loop
    # instead of using ``datasets.map()`` (dill/safetensors pickle bug).
    print(f"[train-fn] loading dataset {args.input} …")
    ds_raw = load_dataset("json", data_files=str(args.input), split="train")

    print(f"[train-fn] tokenizing {len(ds_raw)} rows in-process …")
    input_ids_list:  list[list[int]] = []
    attention_masks: list[list[int]] = []
    sample_text = ""
    for i, ex in enumerate(ds_raw):
        text = tokenizer.apply_chat_template(
            ex["messages"], tokenize=False, add_generation_prompt=False,
        )
        if i == 0:
            sample_text = text
        enc = tokenizer(
            text, truncation=True, max_length=args.max_seq_length,
            padding=False, return_tensors=None,
        )
        input_ids_list.append(enc["input_ids"])
        attention_masks.append(enc["attention_mask"])

    from datasets import Dataset as HFDataset
    ds = HFDataset.from_dict({
        "input_ids":      input_ids_list,
        "attention_mask": attention_masks,
    }).shuffle(seed=args.seed)
    seq_lens = [len(x) for x in input_ids_list]
    print(f"[train-fn] dataset ready: {len(ds)} rows pre-tokenized "
          f"(seq lens min={min(seq_lens)} median={sorted(seq_lens)[len(seq_lens)//2]} max={max(seq_lens)})")
    print(f"[train-fn] sample text:\n---\n{sample_text[:500]}\n…\n{sample_text[-200:]}\n---")

    ckpt_dir = args.out / "_ckpt"
    ckpt_dir.mkdir(parents=True, exist_ok=True)

    # Transformers 5.x renamed `tokenizer=` to `processing_class=`.
    trainer = SFTTrainer(
        model=model,
        processing_class=tokenizer,
        train_dataset=ds,
        args=SFTConfig(
            output_dir=str(ckpt_dir),
            per_device_train_batch_size=args.batch,
            gradient_accumulation_steps=args.grad_accum,
            warmup_ratio=DEFAULTS["warmup_ratio"],
            num_train_epochs=args.epochs,
            learning_rate=args.lr,
            lr_scheduler_type="cosine",
            logging_steps=10,
            save_strategy="epoch",
            bf16=use_bf16,
            fp16=use_fp16,
            optim="adamw_8bit",
            weight_decay=DEFAULTS["weight_decay"],
            max_seq_length=args.max_seq_length,
            # Pre-tokenized dataset above; tell SFTTrainer not to re-prep
            # (that's where the dill/safetensors pickle bug strikes).
            dataset_kwargs={"skip_prepare_dataset": True},
            seed=args.seed,
            report_to="none",
        ),
    )

    # Mask loss to the model turn only. instruction_part is the LAST user
    # turn; everything before <start_of_turn>model\n is masked out.
    trainer = train_on_responses_only(
        trainer,
        instruction_part="<start_of_turn>user\n",
        response_part="<start_of_turn>model\n",
    )

    print(f"[train-fn] starting training "
          f"(epochs={args.epochs} batch={args.batch}×{args.grad_accum}="
          f"{args.batch * args.grad_accum} effective) …")
    t0 = time.perf_counter()
    trainer.train()
    print(f"[train-fn] training finished in {time.perf_counter() - t0:.1f}s")

    print(f"[train-fn] merging LoRA → {args.out}")
    model.save_pretrained_merged(
        str(args.out), tokenizer=tokenizer, save_method="merged_16bit",
    )

    if args.skip_gguf:
        print("[train-fn] --skip-gguf set; HF checkpoint only.")
        return 0

    print(f"[train-fn] exporting GGUF ({args.quantization}) → {args.out}")
    model.save_pretrained_gguf(
        str(args.out), tokenizer=tokenizer, quantization_method=args.quantization,
    )

    candidates = sorted(args.out.glob("*.gguf"))
    if not candidates:
        print("[train-fn] WARNING: no GGUF produced — see manual fallback in "
              "scripts/train_gemma_lora.py docstring (llama.cpp convert + quantize).",
              file=sys.stderr)
        return 0
    src = candidates[-1]
    if args.gguf_target.exists() or args.gguf_target.is_symlink():
        args.gguf_target.unlink()
    try:
        os.symlink(src, args.gguf_target)
        print(f"[train-fn] symlinked {args.gguf_target} → {src}")
    except OSError:
        shutil.copy2(src, args.gguf_target)
        print(f"[train-fn] copied {src} → {args.gguf_target}")

    print(f"\n[train-fn] DONE.\n"
          f"  Bench it: python scripts/bench_intent_routing.py --models fn-gemma\n"
          f"  NOTE: requires the bench refactor in core/gemma_router.py to use\n"
          f"  the 'function-tuned' mode that mirrors format_for_finetune.py prompts.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
