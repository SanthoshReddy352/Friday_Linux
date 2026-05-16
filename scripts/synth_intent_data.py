"""Synthesize Train (~1,500) and Test (~290) intent datasets with a
disjoint-template guarantee for FRIDAY's intent router LoRA pipeline.

Pipeline:
    1. Load tool_registry.yaml (single source of truth — 49 tools).
    2. For each tool, generate `target_per_tool` rows by sampling
       (concept, template) where the template comes from the split's
       paraphrase pool (POOL_A for train, POOL_B for test). Templates
       across pools share NO strings — checked at import time.
    3. Hard negatives are split 80/20 between train/test (deterministic
       index slice — no overlap), all labeled `expected_tool=llm_chat`.
    4. Chitchat seeds (CHITCHAT_TRAIN vs CHITCHAT_TEST — disjoint lists)
       fill the llm_chat positive bucket.
    5. Per-utterance hash check (`--verify-disjoint`) catches any
       coincident overlap between the two final files.

Usage:
    python scripts/synth_intent_data.py --split train \\
        --out tests/datasets/intent_train.jsonl
    python scripts/synth_intent_data.py --split test \\
        --out tests/datasets/intent_test.jsonl
    python scripts/synth_intent_data.py --verify-disjoint
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
REGISTRY = REPO / "tests" / "datasets" / "tool_registry.yaml"

# =====================================================================
# Style inference — per-concept, so heterogeneous tools still produce
# template-compatible utterances.
# =====================================================================
COMMAND_VERBS = {
    "open", "launch", "start", "play", "pause", "take", "snap", "grab",
    "set", "make", "mute", "unmute", "shut", "save", "rename", "move",
    "delete", "copy", "search", "google", "go", "fire", "skip", "next",
    "click", "scroll", "schedule", "cancel", "remove", "create", "add",
    "send", "show", "tell", "give", "read", "summarize", "list", "enable",
    "disable", "stop", "end", "begin", "remind", "find", "look", "forget",
    "switch", "turn", "exit", "quit", "goodbye", "drop", "push", "jot",
    "reschedule", "tldr",
}
CONFIRM_LEADS_BARE = {
    "yes", "yeah", "yep", "no", "nope", "nah", "sure", "okay", "ok",
    "alright", "do", "please",
}
GREET_LEADS = {"hi", "hello", "hey", "yo", "howdy"}


def style_of(concept: str) -> str:
    words = str(concept).strip().lower().split()
    if not words:
        return "query"
    first = words[0]
    if first in GREET_LEADS:
        return "greet"
    if first in CONFIRM_LEADS_BARE and len(words) <= 3:
        return "confirm"
    if first in COMMAND_VERBS:
        return "command"
    return "query"


# =====================================================================
# Paraphrase template pools — DISJOINT BY CONSTRUCTION.
# Pool A = training only. Pool B = test only. Per-style overlap check
# below guards future edits.
# =====================================================================
POOL_A: dict[str, list[str]] = {
    "query": [
        "{concept}",
        "{concept} please",
        "what is {concept}",
        "what's {concept}",
        "tell me {concept}",
        "give me {concept}",
        "do you know {concept}",
        "could you tell me {concept}",
        "show me {concept}",
        "i need {concept}",
        "friday {concept}",
        "hey friday what is {concept}",
        "friday {concept} please",
    ],
    "command": [
        "{concept}",
        "{concept} please",
        "{concept} now",
        "please {concept}",
        "could you {concept}",
        "can you {concept}",
        "go ahead and {concept}",
        "friday {concept}",
        "hey friday {concept}",
        "friday please {concept}",
    ],
    "confirm": [
        "{concept}",
        "{concept} please",
        "{concept} thanks",
        "{concept} go ahead",
        "{concept} that works",
    ],
    "greet": [
        "{concept}",
        "{concept} friday",
        "{concept} there",
    ],
}

POOL_B: dict[str, list[str]] = {
    "query": [
        "any chance you could share {concept}",
        "i'd love to know {concept}",
        "mind telling me {concept}",
        "real quick - {concept}",
        "uh hey, {concept}",
        "got a sec - {concept}",
        "would you mind sharing {concept}",
        "actually, {concept}",
    ],
    "command": [
        "i need you to {concept}",
        "any chance you could {concept}",
        "do me a favor and {concept}",
        "real quick, {concept}",
        "let's {concept}",
        "how about you {concept}",
        "would you {concept}",
        "actually, {concept}",
    ],
    "confirm": [
        "yeah {concept}",
        "alright {concept}",
        "sure thing {concept}",
        "okay {concept}",
    ],
    "greet": [
        "well {concept}",
        "oh, {concept}",
    ],
}


def _verify_template_pools_disjoint() -> None:
    """Raise at import time if any template string is in both pools for
    the same style. This is the strongest leakage guard — short-circuits
    before the generator can ever emit a coincident utterance."""
    for style in POOL_A:
        a = set(POOL_A.get(style, []))
        b = set(POOL_B.get(style, []))
        shared = a & b
        if shared:
            raise SystemExit(
                f"TEMPLATE LEAKAGE — style={style!r} pools share: {shared}"
            )


_verify_template_pools_disjoint()


# =====================================================================
# Chitchat seeds for the llm_chat positive bucket — TRAIN/TEST disjoint.
# =====================================================================
CHITCHAT_TRAIN = [
    "how are you doing today",
    "tell me a joke",
    "what do you think about that",
    "i'm feeling tired",
    "do you ever get bored",
    "what's your favorite color",
    "i had a long day",
    "any thoughts on what i should cook",
    "i don't know what to do tonight",
    "talk to me about something fun",
    "did you sleep well",
    "i'm bored give me an idea",
    "what's something interesting",
    "i'm just venting for a sec",
    "give me a pep talk",
    "i need motivation",
    "am i overthinking this",
    "help me unwind",
    "tell me something cool",
    "what would you do in my place",
]
CHITCHAT_TEST = [
    "share a thought worth thinking about",
    "what's on your mind today",
    "any wisdom to drop on me",
    "make me laugh real quick",
    "give me an unpopular opinion",
    "what's a fun fact you like",
    "tell me what you'd do if you were human",
    "any advice for a quiet evening",
    "what's the one thing worth remembering today",
]


# =====================================================================
# Typo injection (~12% of train rows; test stays clean for fair eval)
# =====================================================================
def _inject_typo(s: str, rng: random.Random) -> str:
    if len(s) < 6 or rng.random() > 0.12:
        return s
    chars = list(s)
    for _ in range(5):
        i = rng.randrange(1, len(chars) - 2)
        if chars[i] != " " and chars[i + 1] != " ":
            chars[i], chars[i + 1] = chars[i + 1], chars[i]
            return "".join(chars)
    return s


# =====================================================================
# Synth core
# =====================================================================
def _render(template: str, concept: str) -> str:
    out = template.format(concept=str(concept)).strip().lower()
    return re.sub(r"\s+", " ", out)


def _slice_hard_negs(hns: list[str], split: str) -> list[str]:
    """Deterministic 80/20 split — train gets the prefix, test the
    suffix. No overlap. For tools with very few negatives this can leave
    test with zero, which is fine — the bench-time hard-negative
    coverage comes from the disjoint train slice via generalization."""
    if not hns:
        return []
    cutoff = max(1, int(len(hns) * 0.8))
    return list(hns[:cutoff]) if split == "train" else list(hns[cutoff:])


def synth_split(
    pool: dict[str, list[str]],
    chitchat: list[str],
    registry: list[dict],
    *,
    split: str,
    target_per_tool: int,
    seed: int,
    apply_typos: bool,
) -> list[dict]:
    rng = random.Random(seed)
    rows: list[dict] = []

    for tool in registry:
        name = tool["name"]
        if name == "llm_chat":
            continue

        concepts = tool.get("concepts") or []
        if not concepts:
            continue

        # Positive rows — sample (concept, template) target_per_tool times.
        for _ in range(target_per_tool):
            concept = rng.choice(concepts)
            style = style_of(concept)
            templates = pool.get(style) or pool["query"]
            tmpl = rng.choice(templates)
            utterance = _render(tmpl, concept)
            if apply_typos:
                utterance = _inject_typo(utterance, rng)
            rows.append({
                "utterance": utterance,
                "expected_tool": name,
                "category": name,
                "source": f"synth/{style}",
            })

        # Hard negatives → llm_chat (deterministic 80/20 train/test).
        for hn in _slice_hard_negs(tool.get("hard_negatives") or [], split):
            rows.append({
                "utterance": hn.strip().lower(),
                "expected_tool": "llm_chat",
                "category": f"neg/{name}",
                "source": "registry/hard_negative",
            })

    # llm_chat positive bucket — chitchat seeds (already disjoint by list).
    for c in chitchat:
        rows.append({
            "utterance": c.strip().lower(),
            "expected_tool": "llm_chat",
            "category": "chitchat",
            "source": "chitchat/seed",
        })

    # Dedupe within-split on (utterance, expected_tool) — same utterance
    # with two different labels is a real bug, drop both isn't safe so we
    # keep the first occurrence (rng-shuffle later randomises which).
    seen: set[tuple[str, str]] = set()
    unique: list[dict] = []
    for row in rows:
        key = (row["utterance"], row["expected_tool"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)

    rng.shuffle(unique)
    return unique


# =====================================================================
# Disjoint check across the two finished files
# =====================================================================
def _utterance_hash(s: str) -> str:
    norm = re.sub(r"\s+", " ", s.strip().lower())
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def verify_disjoint(train_path: Path, test_path: Path) -> int:
    if not train_path.exists() or not test_path.exists():
        print(
            f"LEAKAGE CHECK SKIPPED — missing file(s):\n"
            f"  train: {train_path} ({'exists' if train_path.exists() else 'MISSING'})\n"
            f"  test : {test_path} ({'exists' if test_path.exists() else 'MISSING'})",
            file=sys.stderr,
        )
        return 1

    def _hashes(p: Path) -> set[str]:
        return {
            _utterance_hash(json.loads(line)["utterance"])
            for line in p.read_text(encoding="utf-8").splitlines()
            if line.strip()
        }

    train_hashes = _hashes(train_path)
    test_hashes = _hashes(test_path)
    overlap = train_hashes & test_hashes
    if overlap:
        print(
            f"LEAKAGE: {len(overlap)} utterance(s) appear in both files "
            f"(train={len(train_hashes)}, test={len(test_hashes)}).",
            file=sys.stderr,
        )
        return 1
    print(
        f"OK — train={len(train_hashes)}  test={len(test_hashes)}  overlap=0"
    )
    return 0


# =====================================================================
# I/O helpers
# =====================================================================
def _write_jsonl(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )


def _load_registry() -> list[dict]:
    return yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))["tools"]


def _print_distribution(rows: list[dict]) -> None:
    counts = Counter(r["expected_tool"] for r in rows)
    print(f"  total rows: {len(rows)}")
    print(f"  unique tools: {len(counts)}")
    for tool, n in counts.most_common():
        print(f"    {tool:<28} {n}")


# =====================================================================
# Main
# =====================================================================
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--split", choices=["train", "test"])
    ap.add_argument("--out", type=Path)
    ap.add_argument(
        "--verify-disjoint",
        action="store_true",
        help="Cross-check intent_train.jsonl vs intent_test.jsonl for "
             "utterance overlap. Exits 0 on clean, 1 on leakage.",
    )
    args = ap.parse_args()

    if args.verify_disjoint:
        return verify_disjoint(
            REPO / "tests/datasets/intent_train.jsonl",
            REPO / "tests/datasets/intent_test.jsonl",
        )

    if not args.split or not args.out:
        ap.error("--split and --out are required unless --verify-disjoint is set")

    registry = _load_registry()
    if args.split == "train":
        rows = synth_split(
            POOL_A, CHITCHAT_TRAIN, registry,
            split="train", target_per_tool=44, seed=42, apply_typos=True,
        )
    else:
        rows = synth_split(
            POOL_B, CHITCHAT_TEST, registry,
            split="test", target_per_tool=6, seed=99, apply_typos=False,
        )

    _write_jsonl(rows, args.out)
    print(f"wrote {len(rows)} rows to {args.out}")
    _print_distribution(rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
