"""Fine-tune ``gemma-3-270m-it`` for FRIDAY intent classification.

Pipeline
--------
1. Load ``unsloth/gemma-3-270m-it`` with Unsloth's FastLanguageModel.
2. Wrap it in a LoRA adapter (rank 16, alpha 32, all linear modules).
3. Apply Gemma 3's chat template, train on ``train.gemma.jsonl``
   (1,500+ rows from ``scripts/format_for_finetune.py``).
4. Mask loss to model-turn tokens only via ``train_on_responses_only`` —
   without this the model also fits the prompt and stops being terse.
5. Merge LoRA into base, export GGUF Q4_K_M to ``models/`` so it lands
   exactly where ``scripts/bench_intent_routing.py`` expects.

Prerequisites (NOT installed by FRIDAY's default venv — install on the
training host before running)::

    pip install "unsloth[colab-new]@git+https://github.com/unslothai/unsloth.git"
    pip install --no-deps trl peft accelerate bitsandbytes
    # GGUF export (Unsloth shells out to llama.cpp under the hood):
    apt-get install -y build-essential cmake

A CUDA-capable GPU is required — Unsloth does not support CPU training.
For CPU-only training, swap to plain ``transformers`` + ``peft`` (much
slower; expect ~6–10× the runtime on a 270M-param model).

Outputs::

    models/gemma-3-270m-it-friday/         # HF-format merged checkpoint
    models/gemma-3-270m-it-friday/*.gguf   # quantized for llama.cpp
    models/gemma-3-270m-it-Q4_K_M.gguf     # symlink (or copy on Windows)
                                           # — what the bench loads

Usage::

    python scripts/train_gemma_lora.py
    python scripts/train_gemma_lora.py --epochs 5 --lr 1e-4
    python scripts/train_gemma_lora.py --skip-gguf   # HF only, faster iter
"""
from __future__ import annotations


def _relaunch_under_project_venv() -> None:
    """Stdlib-only venv shim — see ``main.py`` for rationale."""
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
TRAIN_JSONL = REPO / "tests" / "datasets" / "train.gemma.jsonl"
OUT_DIR     = REPO / "models" / "gemma-3-270m-it-friday"
GGUF_TARGET = REPO / "models" / "gemma-3-270m-it-Q4_K_M.gguf"


# =====================================================================
# Defaults — chosen for a 270M base on ~1.5K rows. Tested combinations
# documented inline.
# =====================================================================
DEFAULTS = dict(
    model_id="unsloth/gemma-3-270m-it",
    max_seq_length=1024,         # train.gemma.jsonl max ≈ 232 tokens
    lora_r=16,                   # 8 underfits, 32 wastes capacity on 270M
    lora_alpha=32,               # 2× rank, no scaling needed at inference
    lora_dropout=0.05,
    epochs=3,                    # loss plateaus by epoch 2 on this size
    per_device_batch=8,
    grad_accum=4,                # effective batch 32
    lr=2e-4,                     # standard for Gemma LoRA
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
        missing.append("unsloth (pip install \"unsloth[colab-new]@git+https://github.com/unslothai/unsloth.git\")")
    try:
        import trl  # noqa: F401
    except ImportError:
        missing.append("trl (pip install --no-deps trl)")
    try:
        import datasets  # noqa: F401
    except ImportError:
        missing.append("datasets (pip install datasets)")
    if missing:
        print("Missing required packages:", file=sys.stderr)
        for m in missing:
            print(f"  - {m}", file=sys.stderr)
        sys.exit(1)


def _check_input(path: Path) -> None:
    if not path.exists():
        print(f"ERROR: training file missing: {path}", file=sys.stderr)
        print("Run: python scripts/format_for_finetune.py", file=sys.stderr)
        sys.exit(1)


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
    ap.add_argument("--skip-gguf",      action="store_true",
                    help="Skip GGUF export (HF checkpoint only — useful for fast iteration).")
    ap.add_argument("--gguf-target",    type=Path, default=GGUF_TARGET,
                    help="Final GGUF path the bench script loads.")
    args = ap.parse_args()

    _check_prereqs()
    _check_input(args.input)

    # Imports deferred until after prereq + input checks so a clean
    # error message wins over an ImportError trace.
    from unsloth import FastLanguageModel
    from unsloth.chat_templates import get_chat_template, train_on_responses_only
    from datasets import load_dataset
    from trl import SFTTrainer, SFTConfig

    print(f"[train-gemma] loading {args.model_id} (max_seq_length={args.max_seq_length}) …")
    t0 = time.perf_counter()
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=args.model_id,
        max_seq_length=args.max_seq_length,
        load_in_4bit=False,   # 270M is small — full-precision LoRA is fine
        dtype=None,
    )
    print(f"[train-gemma] base loaded in {time.perf_counter() - t0:.1f}s")

    print(f"[train-gemma] wrapping LoRA r={args.lora_r} alpha={args.lora_alpha} "
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

    # Apply Gemma 3's chat template. Unsloth's ``get_chat_template`` knows
    # the canonical token sequence (``<start_of_turn>{role}\n…<end_of_turn>``).
    tokenizer = get_chat_template(tokenizer, chat_template="gemma-3")

    # Convert the messages-format JSONL into the flat-text format SFT expects.
    print(f"[train-gemma] loading dataset {args.input} …")
    ds = load_dataset("json", data_files=str(args.input), split="train")

    def _to_text(example: dict) -> dict:
        return {
            "text": tokenizer.apply_chat_template(
                example["messages"],
                tokenize=False,
                add_generation_prompt=False,
            )
        }

    ds = ds.map(_to_text, remove_columns=ds.column_names).shuffle(seed=args.seed)
    print(f"[train-gemma] dataset prepared: {len(ds)} rows")
    print(f"[train-gemma] sample text:\n---\n{ds[0]['text'][:400]}\n---")

    ckpt_dir = args.out / "_ckpt"
    ckpt_dir.mkdir(parents=True, exist_ok=True)

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
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
            bf16=True,
            optim="adamw_8bit",
            weight_decay=DEFAULTS["weight_decay"],
            max_seq_length=args.max_seq_length,
            dataset_text_field="text",
            seed=args.seed,
            report_to="none",
        ),
    )

    # CRITICAL: mask loss to model-turn tokens only. Without this the
    # model fits the (huge, repetitive) tool-list prompt and stops being
    # terse on the answer.
    trainer = train_on_responses_only(
        trainer,
        instruction_part="<start_of_turn>user\n",
        response_part="<start_of_turn>model\n",
    )

    print(f"[train-gemma] starting training "
          f"(epochs={args.epochs} batch={args.batch}×{args.grad_accum}="
          f"{args.batch * args.grad_accum} effective) …")
    t0 = time.perf_counter()
    trainer.train()
    print(f"[train-gemma] training finished in {time.perf_counter() - t0:.1f}s")

    print(f"[train-gemma] merging LoRA → {args.out}")
    model.save_pretrained_merged(
        str(args.out), tokenizer, save_method="merged_16bit",
    )

    if args.skip_gguf:
        print("[train-gemma] --skip-gguf set; HF checkpoint only.")
        return 0

    print(f"[train-gemma] exporting GGUF ({args.quantization}) → {args.out}")
    model.save_pretrained_gguf(
        str(args.out), tokenizer, quantization_method=args.quantization,
    )

    # Find the GGUF Unsloth produced and place it where bench expects.
    candidates = sorted(args.out.glob("*.gguf"))
    if not candidates:
        print("[train-gemma] WARNING: no GGUF file produced — skipping symlink.",
              file=sys.stderr)
        return 0
    src = candidates[-1]   # most recent
    if args.gguf_target.exists() or args.gguf_target.is_symlink():
        args.gguf_target.unlink()
    try:
        os.symlink(src, args.gguf_target)
        print(f"[train-gemma] symlinked {args.gguf_target} → {src}")
    except OSError:
        # Symlinks unsupported (Windows w/o developer mode) — fall back to copy.
        shutil.copy2(src, args.gguf_target)
        print(f"[train-gemma] copied {src} → {args.gguf_target}")

    print(f"\n[train-gemma] DONE.\n"
          f"  Bench it:   python scripts/bench_intent_routing.py --models gemma\n"
          f"  Test alone: python scripts/bench_intent_routing.py --models gemma --limit 30\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
