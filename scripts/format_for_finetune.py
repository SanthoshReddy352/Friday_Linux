"""Convert tests/datasets/intent_train.jsonl → two model-specific JSONL
training files for the FRIDAY intent-router LoRA pipeline.

Outputs
-------
* ``tests/datasets/train.gemma.jsonl``
    Standard Gemma chat format. Each row is::

        {"messages": [
            {"role": "user",  "content": "<system text> + tool list + utterance"},
            {"role": "model", "content": "<bare tool name>"}
        ]}

    The "system" instruction is inlined into the user turn because base
    ``gemma-3-270m-it`` does not have a separate system role in its chat
    template. The training loss must be masked to only the model turn —
    the train script does this via ``train_on_responses_only``.

* ``tests/datasets/train.fngemma.jsonl``
    Function-Gemma developer-role format. Each row is::

        {"messages": [
            {"role": "developer", "content": "<schema instruction + JSON tool list>"},
            {"role": "user",      "content": "<utterance>"},
            {"role": "model",     "content": '<start_function_call>{"tool":"X","args":{}}<end_function_call>'}
        ]}

    The ``<start_function_call>``/``<end_function_call>`` envelope tokens
    match what ``core/gemma_router.py:_FUNCTION_CALL_RE`` already parses,
    so a tuned model drops cleanly into the existing inference path.

Args extraction
---------------
``args`` is intentionally always ``{}`` in the FN-Gemma envelope. This
pipeline trains tool *selection* only; teaching the model to populate
args (e.g. ``app_name="chrome"`` for ``launch_app``) requires the synth
to tag arg values per row, which is a follow-up. The benchmark in
``scripts/bench_intent_routing.py`` only scores tool-name accuracy, so
empty args do not affect the headline metric.

Usage::

    python scripts/format_for_finetune.py
    python scripts/format_for_finetune.py --input tests/datasets/intent_train.jsonl
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
REGISTRY_PATH = REPO / "tests" / "datasets" / "tool_registry.yaml"
TRAIN_INPUT = REPO / "tests" / "datasets" / "intent_train.jsonl"
GEMMA_OUTPUT = REPO / "tests" / "datasets" / "train.gemma.jsonl"
FNGEMMA_OUTPUT = REPO / "tests" / "datasets" / "train.fngemma.jsonl"


# =====================================================================
# Prompt templates — kept here as constants so the inference-time
# wrappers (core/gemma_router.py) can mirror them verbatim. If you edit
# these, edit the matching builders in gemma_router.py or the LoRA loses
# all its value at inference (prompt drift collapses accuracy to ~base).
# =====================================================================

GEMMA_USER_TEMPLATE = (
    "You are an intent classifier. Reply with only the tool name.\n\n"
    "Tools: {tool_list}\n\n"
    "Utterance: {utterance}"
)

FNGEMMA_DEVELOPER_TEMPLATE = (
    "You are a function-calling assistant. Choose at most one tool from "
    'this list. If none fit, return {{"tool": null}}.\n\n{schema}'
)


# =====================================================================
# Registry → reusable prompt fragments
# =====================================================================

def load_registry() -> list[dict]:
    return yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))["tools"]


def build_prompt_fragments(registry: list[dict]) -> tuple[str, str]:
    """Return (gemma_tool_list, fngemma_schema_json), computed once and
    inlined into every training record."""
    gemma_tool_list = ", ".join(t["name"] for t in registry)
    fn_schema = [
        {
            "name": t["name"],
            "description": t["description"],
            "parameters": t.get("parameters") or {},
        }
        for t in registry
    ]
    fngemma_schema_json = json.dumps(fn_schema, separators=(",", ":"))
    return gemma_tool_list, fngemma_schema_json


# =====================================================================
# Per-row record builders
# =====================================================================

def gemma_record(row: dict, tool_list: str) -> dict:
    user = GEMMA_USER_TEMPLATE.format(
        tool_list=tool_list,
        utterance=row["utterance"],
    )
    return {
        "messages": [
            {"role": "user", "content": user},
            {"role": "model", "content": row["expected_tool"]},
        ]
    }


def fngemma_record(row: dict, schema_json: str) -> dict:
    developer = FNGEMMA_DEVELOPER_TEMPLATE.format(schema=schema_json)
    if row["expected_tool"] == "llm_chat":
        envelope = '<start_function_call>{"tool": null}<end_function_call>'
    else:
        envelope = (
            '<start_function_call>'
            f'{{"tool": "{row["expected_tool"]}", "args": {{}}}}'
            '<end_function_call>'
        )
    return {
        "messages": [
            {"role": "developer", "content": developer},
            {"role": "user",      "content": row["utterance"]},
            {"role": "model",     "content": envelope},
        ]
    }


# =====================================================================
# I/O + sanity
# =====================================================================

def write_jsonl(records: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n",
        encoding="utf-8",
    )


def _estimate_tokens(text: str) -> int:
    """Char/4 heuristic — close enough to flag overflow on the
    Gemma tokenizer (which averages ~3.7 chars/token on English)."""
    return max(1, len(text) // 4)


def _sample_token_budget(rec: dict) -> int:
    """Sum of estimated tokens across all message contents."""
    return sum(_estimate_tokens(m["content"]) for m in rec["messages"])


# =====================================================================
# Main
# =====================================================================

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", type=Path, default=TRAIN_INPUT,
                    help="Source JSONL (default: intent_train.jsonl).")
    ap.add_argument("--gemma-out",   type=Path, default=GEMMA_OUTPUT)
    ap.add_argument("--fngemma-out", type=Path, default=FNGEMMA_OUTPUT)
    args = ap.parse_args()

    if not args.input.exists():
        print(f"ERROR: input file missing: {args.input}", file=sys.stderr)
        print("Run: python scripts/synth_intent_data.py --split train "
              "--out tests/datasets/intent_train.jsonl", file=sys.stderr)
        return 1

    registry = load_registry()
    tool_list, schema_json = build_prompt_fragments(registry)

    rows = [
        json.loads(line)
        for line in args.input.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    gemma_recs   = [gemma_record(r, tool_list)     for r in rows]
    fngemma_recs = [fngemma_record(r, schema_json) for r in rows]

    write_jsonl(gemma_recs,   args.gemma_out)
    write_jsonl(fngemma_recs, args.fngemma_out)

    # Headline summary
    print(f"input  : {args.input} ({len(rows)} rows)")
    print(f"gemma  : {args.gemma_out} ({len(gemma_recs)} rows)")
    print(f"fngemma: {args.fngemma_out} ({len(fngemma_recs)} rows)")
    print()

    # Token-budget sanity — caller picks max_seq_length based on this.
    g_max = max(_sample_token_budget(r) for r in gemma_recs)
    f_max = max(_sample_token_budget(r) for r in fngemma_recs)
    g_med = sorted(_sample_token_budget(r) for r in gemma_recs)[len(gemma_recs) // 2]
    f_med = sorted(_sample_token_budget(r) for r in fngemma_recs)[len(fngemma_recs) // 2]
    print("Token-budget estimate (chars/4 — Gemma tokenizer is ~3.7 chars/tok so add ~10%):")
    print(f"  gemma  : median {g_med:>4}  max {g_max:>4}  -> set max_seq_length=1024")
    suggest_fn = 2048 if f_max > 1500 else 1536
    print(f"  fngemma: median {f_med:>4}  max {f_max:>4}  -> set max_seq_length={suggest_fn}")
    print()

    # Show one of each so the operator can eyeball formatting before training.
    print("--- gemma sample (rec 0) ---")
    print(json.dumps(gemma_recs[0], ensure_ascii=False, indent=2)[:700])
    print("--- fngemma sample (rec 0) ---")
    print(json.dumps(fngemma_recs[0], ensure_ascii=False, indent=2)[:700])
    return 0


if __name__ == "__main__":
    sys.exit(main())
